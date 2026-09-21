#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""只读体检（合并前置）：母库 vs Claw Agent 题库 的对照信息。"""
import json
import re
from pathlib import Path

MOTHER = "G:/interview-memory/crawler/data/questions-bank.json"
AGENT = "C:/Users/UserName/WorkBuddy/Claw/题库/agent_interview_bank.json"


def norm(s):
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


m = json.loads(Path(MOTHER).read_text(encoding="utf-8"))
a = json.loads(Path(AGENT).read_text(encoding="utf-8"))
mi, aq = m["items"], a["questions"]

print(f"母库 items      : {len(mi)}")
print(f"Agent 库 questions: {len(aq)}")

# 母库最大数字编号
nums = [int(x["id"][1:]) for x in mi if re.fullmatch(r"q\d+", x["id"])]
nonstd = [x["id"] for x in mi if not re.fullmatch(r"q\d+", x["id"])]
print(f"母库数字编号范围: q{min(nums):04d} ~ q{max(nums):04d} ；非标准编号 {len(nonstd)} 个 {nonstd[:5]}")
print(f"下一个可用起始编号: q{max(nums)+1:04d}\n")

print("---- Agent 库样例两条 ----")
for it in aq[:2]:
    print(json.dumps(it, ensure_ascii=False, indent=2)[:900])
    print("-" * 40)

# 精确 norm 交叉重复
mn = {}
for x in mi:
    n = norm(x.get("content") or x.get("norm"))
    if n:
        mn.setdefault(n, []).append(x["id"])
an = {}
for x in aq:
    n = norm(x.get("question"))
    if n:
        an.setdefault(n, []).append(x["id"])
exact = set(mn) & set(an)
print(f"【精确重复】两库题面完全一致的: {len(exact)} 条")
for k in list(exact)[:10]:
    print(f"   {mn[k]} <-> {an[k]} | {list(an.values())[0]} :: {aq[0].get('question','')[:0]}")
    mtxt = next(x["content"] for x in mi if x["id"] in mn[k])
    print(f"      {mtxt[:60]}")

# 库内自重复检查
mc = [k for k, v in mn.items() if len(v) > 1]
ac = [k for k, v in an.items() if len(v) > 1]
print(f"\n【库内自重复】母库 {len(mc)} 组 / Agent 库 {len(ac)} 组")

# 分类体系对照
print(f"\n母库分类({len(set(x.get('category','') for x in mi))}): "
      f"{sorted(set(x.get('category','') for x in mi))}")
print(f"Agent 库分类({len(a['categories'])}): {a['categories']}")

# 字段缺失情况
miss_ans = [x["id"] for x in aq if not (x.get("reference_answer") or "").strip()]
miss_kp = [x["id"] for x in aq if not (x.get("key_points") or [])]
print(f"\nAgent 库缺失: reference_answer 空 {len(miss_ans)} 条 / key_points 空 {len(miss_kp)} 条")
print(f"Agent 库 type 取值: {sorted(set(x.get('type','') for x in aq))}")
