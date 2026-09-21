#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""练习库同步后核验：题数 / 进度零丢失 / 答案零降级。"""
import sqlite3
from pathlib import Path

DB = "G:/interview-memory/data/interview_memory.db"
BAK = "G:/interview-memory/data/interview_memory.db.bak_20260919_065838"


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    bak = sqlite3.connect(BAK)

    n = cur.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    n0 = bak.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    print(f"[题数] {n0} -> {n}")
    print(f"[唯一 id] {cur.execute('SELECT COUNT(DISTINCT id) FROM questions').fetchone()[0]}")

    total_orphan = 0
    for t in ("review_schedule", "submissions", "wrong_book"):
        try:
            c = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            o = cur.execute(
                f"SELECT COUNT(*) FROM {t} WHERE question_id NOT IN (SELECT id FROM questions)"
            ).fetchone()[0]
            total_orphan += o
            print(f"[{t}] {c} 行, 孤儿 {o}")
        except sqlite3.OperationalError:
            print(f"[{t}] 表不存在")
    print(f"[进度] 孤儿合计 {total_orphan} (应=0)")

    old = {r[0]: (r[1] or "") for r in bak.execute("SELECT id, reference_answer FROM questions")}
    new = {r[0]: (r[1] or "") for r in cur.execute("SELECT id, reference_answer FROM questions")}
    common = set(old) & set(new)
    down = [i for i in common if len(new[i]) < len(old[i])]
    up = [i for i in common if len(new[i]) > len(old[i])]
    print(f"\n[降级检查] 共同行 {len(common)} | 答案变短 {len(down)} (应=0) | 变长 {len(up)}")
    if down:
        worst = sorted(down, key=lambda i: len(old[i]) - len(new[i]), reverse=True)[:5]
        for i in worst:
            q = cur.execute("SELECT question_text FROM questions WHERE id=?", (i,)).fetchone()
            print(f"   ⚠️ id={i} {len(old[i])}->{len(new[i])} | {(q[0] if q else '')[:46]}")

    t_old = sum(len(v) for v in old.values())
    t_new = sum(len(v) for v in new.values())
    print(f"[总量] 答案总字数 {t_old:,} -> {t_new:,} (差 {t_new - t_old:+,})")
    empty = cur.execute(
        "SELECT COUNT(*) FROM questions "
        "WHERE reference_answer IS NULL OR TRIM(reference_answer) = ''"
    ).fetchone()[0]
    print(f"[空答案] {empty}")
    con.close(); bak.close()


if __name__ == "__main__":
    main()
