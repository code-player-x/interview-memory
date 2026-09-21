#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""排查去重那 2 组：谁被保留、是否发生答案降级。"""
import json
from pathlib import Path

BANK = Path("G:/interview-memory/crawler/data/questions-bank.json")
BACKUP = Path("G:/interview-memory/crawler/data/questions-bank.json.bak_20260919_004328")

PAIRS = [("q0012", "q4010"), ("q1142", "q4012")]


def ans_text(a):
    if isinstance(a, dict):
        return "\n".join(str(v) for v in a.values() if v)
    return str(a or "")


cur = json.loads(BANK.read_text(encoding="utf-8"))
old = json.loads(BACKUP.read_text(encoding="utf-8"))
new_by = {x["id"]: x for x in cur["items"]}
old_by = {x["id"]: x for x in old["items"]}

for gone_id, maybe_new in PAIRS:
    print("=" * 84)
    print(f"比对: 被删 {gone_id}  vs  疑似保留 {maybe_new}")
    g, k = old_by.get(gone_id), new_by.get(maybe_new)
    print(f"  被删者存在? {bool(g)}   疑似保留者还在库? {bool(k)}")
    if g:
        print(f"  [{gone_id}] ({g.get('category')}) {g.get('content','')[:60]}")
        print(f"        答案 {len(ans_text(g.get('answer')))} 字, sources={g.get('sources')}, tags={g.get('tags')}")
    if k:
        print(f"  [{maybe_new}] ({k.get('category')}) {k.get('content','')[:60]}")
        print(f"        答案 {len(ans_text(k.get('answer')))} 字, sources={k.get('sources')}, tags={k.get('tags')}")
        print(f"        是否吸收了对方的 sources: "
              f"{'是' if any(gone_id in str(s) for s in (k.get('sources') or [])) else '否'}")
        print(f"        是否有 _merged_from 溯源: {k.get('_merged_from') or k.get('merged_from')}")

    # 内容包含关系检查
    if g and k:
        ga, ka = ans_text(g.get("answer")), ans_text(k.get("answer"))
        print(f"\n  >> 字数: 被删 {len(ga)} vs 保留 {len(ka)}  "
              f"{'⚠️ 保留项更短，可能降级' if len(ka) < len(ga) else 'OK 保留项不短'}")
        # 被删答案里独有的句子
        import re
        gs = [s.strip() for s in re.split(r"[\n。；]", ga) if len(s.strip()) > 12]
        missing = [s for s in gs if s[:14] not in ka]
        print(f"  >> 被删者答案中未在保留项出现的句段: {len(missing)} / {len(gs)}")
        for s in missing[:6]:
            print(f"        - {s[:70]}")
    print()
