#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨平台来源补全：利用语义去重已缓存的 embedding，对 all_platforms_refined.jsonl 中
每道唯一题，回查四源 refined 里哪些平台存在近义题（余弦>=0.9），把 sources 标签补全为
多平台集合。这样频率统计的「跨平台共现」才有意义（同一题在几个平台被考）。

写入：data/tmp/all_platforms_refined.jsonl（sources 改为跨平台集合，src_count 保留单源内频次）
依赖：numpy（venv）
"""
import json, pickle, sys
from pathlib import Path
from collections import Counter

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
from dedup.util import sha256

SOURCES = ["juejin", "nowcoder", "xiaohongshu", "zhihu"]
CACHE = BASE / "data" / "tmp" / ".semantic_embed_cache.pkl"
ALL = BASE / "data" / "tmp" / "all_platforms_refined.jsonl"
TH = 0.9


def load_refined(source):
    p = BASE / "data" / "tmp" / source / "refined.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    cache = pickle.load(open(CACHE, "rb"))
    # 构建文档库 (向量, 源)
    docs = []
    for s in SOURCES:
        for rec in load_refined(s):
            q = (rec.get("question") or "").strip()
            if not q:
                continue
            v = cache.get(sha256(q))
            if v is not None:
                docs.append((np.array(v, dtype=float), s))
    DocM = np.stack([d[0] for d in docs])
    DocS = np.array([d[1] for d in docs])
    DocN = DocM / np.linalg.norm(DocM, axis=1, keepdims=True)

    records = [json.loads(l) for l in open(ALL, encoding="utf-8") if l.strip()]
    # 仅对「有缓存 embedding」的题做跨平台回查；缺向量的题（如微信新增）保留原来源标签
    Qidx, QM_list = [], []
    for i, r in enumerate(records):
        v = cache.get(sha256((r.get("question") or "").strip()))
        if v is not None:
            Qidx.append(i)
            QM_list.append(np.array(v, dtype=float))
    if not QM_list:
        print("[warn] 无可用 embedding，跳过跨平台补全（保留原 sources）")
        co = Counter(len(r.get("sources", [])) for r in records)
        print("跨平台共现分布(出现在N个平台): %s" % dict(sorted(co.items())))
        return
    QM = np.stack(QM_list)
    QN = QM / np.linalg.norm(QM, axis=1, keepdims=True)
    sim = QN @ DocN.T  # (Q_embedded, N)

    for k, i in enumerate(Qidx):
        r = records[i]
        js = np.where(sim[k] >= TH)[0]
        cross = sorted(set(DocS[js].tolist()))
        r["sources"] = cross  # 跨平台来源集合
        # 保留原 src_count（单源内频次）不动
    # 无 embedding 的题（如微信新增）保持 merge_refined 给的单源标签，不改动

    ALL.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    co = Counter(len(r["sources"]) for r in records)
    print("跨平台来源补全完成。唯一题 %d 道。" % len(records))
    print("跨平台共现分布(出现在N个平台): %s" % dict(sorted(co.items())))
    print("多平台(>=2)热门题数: %d" % sum(1 for r in records if len(r["sources"]) >= 2))
    # Top 高频跨平台题
    hot = sorted(records, key=lambda r: (len(r["sources"]), r.get("src_count", 1)), reverse=True)[:15]
    print("\n跨平台热点题 Top15:")
    for r in hot:
        print("  [%d平台/%dsrc] %s | %s" % (len(r["sources"]), r.get("src_count", 1),
                                             (r["question"])[:50], ",".join(r["sources"])))


if __name__ == "__main__":
    main()
