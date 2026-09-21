#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""体检：定位题库文件，说明存放位置、格式、字段层级与命名方式。"""
import json
import re
from collections import Counter
from pathlib import Path

CANDS = [
    "G:/interview-memory/crawler/data/questions-bank.json",
    "D:/UserName/Documents/爬面经_整理面经+手撕题目_获取面经答案_格式化答案/agent-mianshi-harvester/data/questions-bank.json",
    "C:/Users/UserName/WorkBuddy/Claw/题库/agent_interview_bank.json",
    "C:/Users/UserName/WorkBuddy/Claw/题库/basic_interview_bank.json",
]


def probe(p):
    path = Path(p)
    print("=" * 80)
    print(f"路径: {p}")
    if not path.exists():
        print("  [不存在]")
        return
    print(f"  大小 {path.stat().st_size:,} bytes")
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [非 JSON 或解析失败] {e}")
        return

    print(f"  顶层键: {list(d.keys())}")
    key = "items" if "items" in d else ("questions" if "questions" in d else None)
    if not key:
        print("  未识别的题目数组键")
        return
    items = d[key]
    print(f"  题目数组键: '{key}' | 数量 {len(items)}")

    # meta
    if "meta" in d:
        print(f"  meta 键: {list(d['meta'].keys())}")
    else:
        print(f"  同级元数据: {[k for k in d if k != key]}")

    # 字段层级与命名
    keys = Counter()
    types = {}
    for it in items:
        for k, v in it.items():
            keys[k] += 1
            types.setdefault(k, type(v).__name__)
    print("\n  -- 字段（出现次数 / 类型 / 命名方式）--")
    for k, c in keys.most_common():
        print(f"     {k:<18} {c:>5} 次   {types[k]}")

    # answer 嵌套层级
    ans = items[0].get("answer")
    print(f"\n  -- answer 嵌套结构 --")
    if isinstance(ans, dict):
        print(f"     answer 为 dict，子键: {list(ans.keys())}")
        for k, v in ans.items():
            print(f"       - {k}: {type(v).__name__} ({len(str(v))} 字)")
    else:
        print(f"     answer 为 {type(ans).__name__}")

    # 是否有选项类字段
    opt_like = [k for k in keys if re.search(r"option|choice|选项|备选|A[.、]", k)]
    print(f"\n  -- 是否存在「选项」类字段: {opt_like or '无（本题库为问答题）'}")

    # 枚举值分布
    print("\n  -- 关键枚举值 --")
    for f in ("category", "type", "status", "difficulty"):
        if f in keys:
            c = Counter(str(it.get(f, "")) for it in items)
            print(f"     {f}: {dict(c.most_common(10))}")

    # id 命名
    ids = [str(it.get("id", "")) for it in items]
    pats = Counter()
    for i in ids:
        pats[re.sub(r"\d+", "N", i)] += 1
    print(f"\n  -- id 命名模式: {dict(pats)}")


for c in CANDS:
    probe(c)
    print()
