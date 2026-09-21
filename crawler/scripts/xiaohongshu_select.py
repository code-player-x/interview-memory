#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书精选二次筛选：0.85 严格去重 + 噪声过滤，输出干净候选 refined.jsonl。"""
import json
import re
from pathlib import Path
from collections import defaultdict, Counter
from difflib import SequenceMatcher

HERE = Path(__file__).resolve().parent
SHORT = HERE.parent / "data" / "tmp" / "xiaohongshu" / "shortlist.jsonl"
REFINED = HERE.parent / "data" / "tmp" / "xiaohongshu" / "refined.jsonl"
BANK = HERE.parent / "data" / "questions-bank.json"

SIM_STRICT = 0.85  # 与题库严格去重

# 噪声：软文/非题/残缺
NOISE2 = re.compile(
    r"(分享一下|我面试|被问到|了解过吗|面试官|你面试|面经|八股|项目[一二三四五]|"
    r"追问|答：|答:|评论区|楼主|私信|求捞|求内推|详见|不展开|待补充|未完|"
    r"上文|下文|如上|如下|见上|这个题|那个题|就是|比如|例如|包括|以及|还有)"
)
TAIL2 = re.compile(r"(的|了|和|与|或|及|把|被|让|如果|因为|所以|但是|而且|还有|以及|吗|呢|吧|啊|呀)$")
QNUM = re.compile(r"^[Qq]\d+[\s：:、]|^[a-z][\.、]\s|^[（(]\d+[)）]\s")


def norm(s):
    return re.sub(r"[\s\W]+", "", s.lower())


def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


def bank_text(it):
    return (it.get("content") or it.get("question") or "").strip()


def main():
    rows = [json.loads(l) for l in open(SHORT, encoding="utf-8")]
    bank = json.load(open(BANK, encoding="utf-8"))
    bank_keys = [norm(bank_text(it)) for it in bank.get("items", []) if bank_text(it)]

    kept, kn = [], []
    for r in rows:
        q = r["question"].strip()
        q = re.sub(r"^[Qq]\d+[\s：:、]+", "", q)        # 去 Q编号
        q = QNUM.sub("", q).strip()                       # 去 a. ( ) 等残留
        if len(q) < 8 or len(q) > 55:
            continue
        if NOISE2.search(q) or TAIL2.search(q):
            continue
        if not re.search(r"(？|\?|如何|怎么|为什么|什么是|讲讲|讲一下|介绍|说说|区别|原理|设计|实现|对比|谈谈|解释|分析|手撕|算法|了解|聊聊|描述)", q):
            # 没有问号也没有引导词 → 大概率是陈述/名词，丢弃
            continue
        nq = norm(q)
        if any(similar(nq, bk) >= SIM_STRICT for bk in bank_keys):
            continue  # 严格去重
        dup = False
        for x in kn:
            if similar(nq, x) >= 0.85:
                dup = True
                break
        if dup:
            continue
        kept.append({**r, "question": q})
        kn.append(nq)

    bycat = defaultdict(list)
    for k in kept:
        bycat[k["category"]].append(k)
    with open(REFINED, "w", encoding="utf-8") as f:
        for cat in bycat:
            for r in bycat[cat]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[refined] total: {len(kept)}")
    for cat, rs in sorted(bycat.items(), key=lambda x: -len(x[1])):
        print(f"\n### {cat} ({len(rs)})")
        for r in rs:
            print(f"  {r['question']}")


if __name__ == "__main__":
    main()
