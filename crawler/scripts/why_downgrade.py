#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""打印两组被合并双方在去重时的实际打分，定位为何保留了更短答案。"""
import json
from pathlib import Path

BACKUP = Path("G:/interview-memory/crawler/data/questions-bank.json.bak_20260919_004328")
PAIRS = [("q0012", "q4010"), ("q1142", "q4012")]


def answer_score(it):
    a = it.get("answer") or {}
    if isinstance(a, dict):
        txt = " ".join(str(a.get(k, "")) for k in ("简版", "展开", "加分点", "雷区"))
    else:
        txt = str(a)
    base = 1000 if it.get("status") == "已补答案" else 0
    return base + len(txt), base, len(txt)


old = json.loads(BACKUP.read_text(encoding="utf-8"))
by = {x["id"]: x for x in old["items"]}

for a_id, b_id in PAIRS:
    print("=" * 80)
    for xid in (a_id, b_id):
        it = by.get(xid)
        if not it:
            print(f"{xid}: 不在备份中"); continue
        score, base, ln = answer_score(it)
        ans = it.get("answer") or {}
        keys = list(ans.keys()) if isinstance(ans, dict) else f"<{type(ans).__name__}>"
        lens = {k: len(str(v)) for k, v in ans.items()} if isinstance(ans, dict) else {}
        print(f"  [{xid}] status={it.get('status')!r}")
        print(f"       answer 键={keys}  各键长度={lens}")
        print(f"       answer_score = {score}  (base={base} + 文本长度={ln})")
    sa, _, _ = answer_score(by[a_id]) if a_id in by else (None, None, None)
    sb, _, _ = answer_score(by[b_id]) if b_id in by else (None, None, None)
    if sa is not None and sb is not None:
        print(f"  >> 胜出者应是: {a_id if sa > sb else b_id}  ({sa} vs {sb})")
    print()
