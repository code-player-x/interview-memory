#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对候选题做清洗+去重(内部+与题库)，产出精选清单 shortlist.jsonl。"""
import json
import re
import sys
from pathlib import Path
from difflib import SequenceMatcher
from collections import defaultdict

HERE = Path(__file__).resolve().parent
CAND = HERE.parent / "data" / "tmp" / "nowcoder" / "candidates.jsonl"
BANK = HERE.parent / "data" / "questions-bank.json"
OUT = HERE.parent / "data" / "tmp" / "nowcoder" / "shortlist.jsonl"

SIM = 0.72  # 归一化后相似阈值

# 明显噪声/残缺/项目专属，剔除
DROP = re.compile(
    r"^(八股|项目[一二三四]|项目，|追问|然后|接着|最后|首先|其次|另外|以及|还有|"
    r"这个|那个|就是|比如|例如|包括)|"
    r"(简历|自我介绍|你的项目|我的项目|上文|下文|如上|如下|见上|楼主|楼上|评论区|"
    r"私信|求捞|求内推|详见|不展开|略|待补充|未完|tbc)"
)
# 残句：以连接词/介词结尾
TAIL_BAD = re.compile(r"(的|了|和|与|或|及|把|被|让|如果|因为|所以|但是|而且|还有|以及)$")


def norm(s):
    return re.sub(r"[\s\W]+", "", s.lower())


def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


def load_bank_keys():
    d = json.load(open(BANK, encoding="utf-8"))
    return [norm(it.get("question", "")) for it in d["items"]], d


def main():
    cands = [json.loads(l) for l in open(CAND, encoding="utf-8")]
    bank_keys, _ = load_bank_keys()

    kept = []
    kept_norms = []
    for c in cands:
        q = c["question"].strip()
        # 基础清洗
        if DROP.search(q) or TAIL_BAD.search(q):
            continue
        # 去掉句中残留的 "项目一，" "八股，" 等前缀噪声
        q = re.sub(r"^(项目[一二三四五]|八股|追问)[，,、\s]+", "", q).strip()
        if len(q) < 6 or len(q) > 60:
            continue
        # 含多题混杂（一个候选里塞了 "？7.xxx？" 之类）→ 只取第一句
        q = re.split(r"[？?]\s*\d+[\.、]", q)[0].strip().rstrip("？?")
        if len(q) < 6:
            continue
        nq = norm(q)
        # 与题库去重
        if any(similar(nq, bk) >= SIM for bk in bank_keys):
            continue
        # 候选内部去重
        dup = False
        for i, kn in enumerate(kept_norms):
            if similar(nq, kn) >= SIM:
                # 保留来源更多的
                if c["src_count"] > kept[i]["src_count"]:
                    kept[i] = {**c, "question": q}
                dup = True
                break
        if dup:
            continue
        kept.append({**c, "question": q})
        kept_norms.append(nq)

    # 按类别分组，类内按频次排序
    bycat = defaultdict(list)
    for k in kept:
        bycat[k["category"]].append(k)
    for cat in bycat:
        bycat[cat].sort(key=lambda r: r["src_count"], reverse=True)

    with open(OUT, "w", encoding="utf-8") as f:
        for cat in bycat:
            for r in bycat[cat]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"shortlist total: {len(kept)}")
    for cat, rows in sorted(bycat.items(), key=lambda x: -len(x[1])):
        print(f"\n### {cat} ({len(rows)})")
        for r in rows[:18]:
            print(f"  [{r['src_count']}] {r['question']}")


if __name__ == "__main__":
    main()
