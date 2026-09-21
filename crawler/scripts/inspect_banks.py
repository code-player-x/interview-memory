#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""只读体检：列出候选题库文件的规模、schema、编号格式与字段差异。"""
import json
import os
from pathlib import Path

CANDS = [
    "G:/interview-memory/crawler/data/questions-bank.json",
    "C:/Users/UserName/WorkBuddy/Claw/题库/agent_interview_bank.json",
    "C:/Users/UserName/WorkBuddy/Claw/题库/basic_interview_bank.json",
    "G:/interview-memory/crawler/interview_memory.db",
]


def describe(p):
    path = Path(p)
    print("=" * 78)
    print(f"路径: {p}")
    if not path.exists():
        print("  [不存在]")
        return
    print(f"  大小: {path.stat().st_size:,} bytes | mtime: {path.stat().st_mtime:.0f}")
    if p.endswith(".db"):
        import sqlite3
        con = sqlite3.connect(p)
        cur = con.cursor()
        for t in ("questions", "review_schedule", "submissions", "wrong_book"):
            try:
                print(f"  表 {t}: {cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} 行")
            except Exception:
                pass
        cols = [r[1] for r in cur.execute("PRAGMA table_info(questions)")]
        print(f"  questions 列: {cols}")
        row = cur.execute("SELECT * FROM questions LIMIT 1").fetchone()
        print(f"  样例 id: {row[0] if row else None}")
        con.close()
        return

    d = json.loads(path.read_text(encoding="utf-8"))
    print(f"  顶层键: {list(d.keys())[:12]}")
    if "items" in d:
        items = d["items"]
        print(f"  格式: items[] | 数量 {len(items)} | meta: {d.get('meta', {})}")
    elif "questions" in d:
        items = d["questions"]
        meta = {k: v for k, v in d.items() if k != "questions"}
        print(f"  格式: questions[] | 数量 {len(items)} | 元数据: {meta}")
        cats = d.get("categories")
        if cats:
            print(f"  categories: {cats}")
    else:
        print("  未知格式")
        return

    # 编号与字段
    def qid(it):
        for k in ("id", "qid"):
            if k in it:
                return str(it[k])
        return "?"
    ids = [qid(it) for it in items]
    print(f"  编号样例: {ids[:6]}")
    keys = {}
    for it in items:
        for k in it:
            keys[k] = keys.get(k, 0) + 1
    print(f"  字段(出现次数): {sorted(keys.items(), key=lambda x: -x[1])[:14]}")
    print(f"  答案字段形态: { {k: type(items[0].get(k)).__name__ for k in ('answer','reference_answer','reference') if k in items[0]} }")
    # 分类分布
    cat = {}
    for it in items:
        c = it.get("category") or it.get("categories") or "?"
        if isinstance(c, list):
            c = ",".join(map(str, c))
        cat[str(c)] = cat.get(str(c), 0) + 1
    top = sorted(cat.items(), key=lambda x: -x[1])[:10]
    print(f"  分类 Top: {top}")


for c in CANDS:
    try:
        describe(c)
    except Exception as e:
        print(f"  [读取失败] {type(e).__name__}: {e}")
