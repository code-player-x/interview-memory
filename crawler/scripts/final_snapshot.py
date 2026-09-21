#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""总库最终快照核验。"""
import json
import re
from pathlib import Path
from collections import Counter

BANK = Path("G:/interview-memory/crawler/data/questions-bank.json")
AGENT = Path("C:/Users/UserName/WorkBuddy/Claw/题库/agent_interview_bank.json")


def ans(a):
    if isinstance(a, dict):
        return "\n".join(str(v) for v in a.values() if v)
    return str(a or "")


d = json.loads(BANK.read_text(encoding="utf-8"))
items = d["items"]
print(f"总库题数 : {len(items)} | meta.total={d['meta'].get('total')}")
print(f"唯一 id  : {len(set(x['id'] for x in items))}")

norms = [re.sub(r"[\s\W_]+", "", (x.get("content") or x.get("norm") or "").lower()) for x in items]
print(f"题面完全重复: {len({n for n in norms if n and norms.count(n) > 1})} 组 (应=0)")

# 来自 Agent 库的新增题（含被合并掉的）
imported = [x for x in items if any("Claw题库" in str(s) or "Claw题库" in str(x.get("source", ""))
                                   for s in (x.get("sources") or []))]
print(f"\n含 Claw Agent 库来源标记的题: {len(imported)}")

new_survived = [x for x in items if x["id"] >= "q4007"]
print(f"本次新编号(q4007+)且存活的题: {len(new_survived)}")
for x in new_survived:
    print(f"   [{x['id']}] ({x.get('category')}) {x.get('content','')[:54]}")

cross = [x for x in items if any("cross-validated" in str(s) for s in (x.get("sources") or []))]
print(f"被交叉验证回填过 key_points 的重叠题: {len(cross)}")

rec = [x for x in items if any("recovered-from" in str(s) for s in (x.get("sources") or []))]
print(f"吸收了被合并题互补内容的题: {len(rec)}")
for x in rec:
    print(f"   [{x['id']}] {x.get('content','')[:50]}")

print("\n分类分布:", dict(Counter(x.get("category", "") for x in items).most_common()))
print(f"答案总字数: {sum(len(ans(x.get('answer'))) for x in items):,}")
print(f"空答案题数: {sum(1 for x in items if not ans(x.get('answer')).strip())}")
print(f"\nmeta.last_dedup : {d['meta'].get('last_dedup')}")
print(f"meta.last_merged_source: {d['meta'].get('last_merged_source')}")
