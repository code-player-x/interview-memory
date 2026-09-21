#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5 源跨源 + 语义去重合并（缓存优先，纯本地、不联网）。

与 merge_refined.py 等价，但用 numpy 向量化做语义聚类，避免 O(n^2) 纯 Python 余弦
在 ~3800 题上超时。流程：
  1. 读 5 源 refined.jsonl（掘金/牛客/小红书/知乎/微信）；
  2. 精确归一化(norm)跨源去重 —— 同题面不同平台合并来源标签；
  3. 语义聚类（缓存 embedding 余弦 >= 0.9）合并近义题，来源标签取并集；
  4. 与题库 baseline 去重（norm 命中即跳过，保证只产出净新增）；
  5. 输出 data/tmp/all_platforms_refined.jsonl（question/category/sources/src_count），
     并回写 sources 为多平台集合（跨平台共现有意义）。

缺 embedding 的题（当前仅微信 80 题，缓存未覆盖）：不参与语义聚类，仅走精确归一化，
保留为单源候选（带备份回写时由 B 阶段决定如何处理）。
"""
import json
import pickle
import sys
from pathlib import Path
from collections import Counter

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
from dedup.util import norm, sha256

SOURCES = ["juejin", "nowcoder", "xiaohongshu", "zhihu", "weixin"]
BANK = BASE / "data" / "questions-bank.json"
CACHE = BASE / "data" / "tmp" / ".semantic_embed_cache.pkl"
OUT = BASE / "data" / "tmp" / "all_platforms_refined.jsonl"
TH = 0.9


def load_refined(source):
    p = BASE / "data" / "tmp" / source / "refined.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    # 1. 载入
    recs = []
    per_src = {}
    for s in SOURCES:
        n0 = len(recs)
        for it in load_refined(s):
            q = (it.get("question") or "").strip()
            if q:
                recs.append((s, q, it.get("category", "概念基础"), it.get("src_count", 1)))
        per_src[s] = len(recs) - n0
    print("各源 refined 题数: %s" % per_src)
    print("合并原始题数: %d" % len(recs))

    # 2. 题库 baseline（norm 集合）
    bank = json.load(open(BANK, encoding="utf-8"))
    bank_norm = {norm((it.get("content") or it.get("question") or "").strip())
                 for it in bank.get("items", []) if (it.get("content") or it.get("question") or "").strip()}
    print("题库 baseline norm 数: %d" % len(bank_norm))

    # 3. 缓存
    cache = pickle.load(open(CACHE, "rb"))
    print("embedding 缓存: %d 条" % len(cache))

    # 阶段一：精确归一化跨源合并
    groups = []
    seen_norm = {}
    for s, q, cat, sc in recs:
        n = norm(q)
        if n in seen_norm:
            g = seen_norm[n]
            g["sources"].add(s)
            g["src_count"] = max(g["src_count"], sc)
            continue
        emb = cache.get(sha256(q))  # 可能 None（微信）
        g = {"norm": n, "sources": {s}, "category": cat, "src_count": sc,
             "q": q, "emb": emb}
        seen_norm[n] = g
        groups.append(g)
    print("精确归一化后唯一题: %d" % len(groups))

    # 阶段二：语义聚类（仅对带 embedding 的组，向量化余弦）
    have = [i for i, g in enumerate(groups) if g["emb"] is not None]
    rep_local, rep_global = [], []
    if have:
        M = np.stack([np.array(groups[i]["emb"], dtype=float) for i in have])
        Mn = M / np.linalg.norm(M, axis=1, keepdims=True)
        for li, gi in enumerate(have):
            v = Mn[li]
            if rep_global:
                R = Mn[rep_local]            # (num_reps, d)
                sims = R @ v
                j = int(np.argmax(sims))
                if sims[j] >= TH:
                    rg = rep_global[j]
                    groups[rg]["sources"] |= groups[gi]["sources"]
                    groups[rg]["src_count"] = max(groups[rg]["src_count"], groups[gi]["src_count"])
                    groups[gi]["_drop"] = True
                    continue
            rep_local.append(li)
            rep_global.append(gi)
        print("语义聚类：带向量 %d 题 -> 簇代表 %d（合并 %d）" %
              (len(have), len(rep_global), len(have) - len(rep_global)))

    # 4. 输出（跳过：被语义合并的 + 命中题库 baseline 的）
    out = []
    dropped_bank = 0
    for idx, g in enumerate(groups):
        if g.get("_drop"):
            continue
        if g["norm"] in bank_norm:
            dropped_bank += 1
            continue
        out.append({
            "question": g["q"],
            "category": g["category"],
            "sources": sorted(g["sources"]),
            "src_count": g["src_count"],
        })
    out.sort(key=lambda r: (len(r["sources"]), r["src_count"]), reverse=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("跨源去重后唯一题数: %d（题库命中跳过 %d）" % (len(out), dropped_bank))

    co = Counter(len(r["sources"]) for r in out)
    print("跨平台共现分布(出现在N个平台): %s" % dict(sorted(co.items())))
    print("已写 -> %s" % OUT)


if __name__ == "__main__":
    main()
