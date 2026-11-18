#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 B+ 树综合大题同步到练习库 interview_memory.db。

母库已把 q0489/q0490(锚点)/q0491/q0492/q0499/q0500 整合为一道综合题 q0490。
练习库中对应的 6 行是 id 609/610/611/614/618/619（均无学习进度），
这里保留 609 作为综合题行，删除其余 5 行。

同时把「分点设问」写进母库 q0490 的 content，使 content 自包含，
保证后续任何 convert/import 流程都不会丢设问。

用法：python scripts/sync_bplustree_practice.py [--apply]
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.sqlite_target import backup_sqlite, sqlite_target

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ / "scripts"))

BANK = PROJ / "data" / "questions-bank.json"
ANCHOR = "q0490"
PRAC_ANCHOR = 609          # 保留并改写的练习库行
PRAC_DELETE = [610, 611, 614, 618, 619]
# 合并前的六道题面，来自历史分类导出。ID 只在当时的练习库中有效。
OLD_TITLES = {
    "B+树的特性是什么", "B+ 和 B 树有什么区别", "MySQL 为什么使用 B+ 树",
    "为什么索引用 B+ 树？而不用红黑树", "insert 操作对 B+ 树结构的改变是怎么样的",
    "假如一张表有两千万的数据，B+树的高度是多少？怎么算的",
}

try:
    from convert_to_interview_memory import build_reference, star_to_int
except Exception:
    def build_reference(a: dict) -> str:
        parts = []
        for k in ("简版", "展开", "加分点", "雷区"):
            v = (a or {}).get(k)
            if isinstance(v, list):
                v = "\n".join(str(x).strip() for x in v if str(x).strip())
            v = (v or "").strip()
            if v:
                parts.append(f"【{k}】\n{v}")
        return "\n\n".join(parts)

    def star_to_int(d: str) -> int:
        full = (d or "").count("★")
        return max(1, min(5, full + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--db", help="显式覆盖 DATABASE_URL 的 SQLite 文件路径")
    args = ap.parse_args()
    try:
        database = Path(sqlite_target(args.db))
    except ValueError as error:
        ap.error(str(error))

    with open(BANK, encoding="utf-8") as f:
        data = json.load(f)
    it = next((x for x in data["items"] if x["id"] == ANCHOR), None)
    if it is None:
        print(f"[error] 母库找不到 {ANCHOR}")
        return

    subq = it.get("sub_questions") or ""
    if subq and "分点设问" not in it.get("content", ""):
        it["content"] = it["content"].rstrip() + "\n\n【分点设问】\n" + subq
        print("[bank] 已把分点设问写进 content（自包含）")
    else:
        print("[bank] content 已含设问，跳过")

    question_text = it["content"].strip()
    reference = build_reference(it.get("answer"))
    category = it.get("category", "") or ""
    tags = ",".join(str(t).strip() for t in (it.get("tags") or []) if str(t).strip())
    difficulty = star_to_int(it.get("difficulty", ""))
    platform = (it.get("source", "") or "WorkBuddy爬取")[:48]

    mode = "rw" if args.apply else "ro"
    con = sqlite3.connect(database.as_uri() + "?mode=" + mode, uri=True)
    con.execute("PRAGMA foreign_keys=ON")
    if args.apply:
        con.execute("BEGIN IMMEDIATE")
    cur = con.cursor()
    old_len = {}
    anchor_titles = OLD_TITLES | {question_text, question_text.split("【分点设问】")[0].strip()}
    for pid in [PRAC_ANCHOR] + PRAC_DELETE:
        r = cur.execute("SELECT question_text,LENGTH(reference_answer) FROM questions WHERE id=?", (pid,)).fetchone()
        if r:
            allowed = anchor_titles if pid == PRAC_ANCHOR else OLD_TITLES
            if r[0].strip() not in allowed:
                con.close()
                ap.error(f"题目 {pid} 与历史合并题面不符，已停止")
            old_len[pid] = r[1] or 0
    if PRAC_ANCHOR not in old_len:
        con.close()
        ap.error(f"缺少保留题目 {PRAC_ANCHOR}，已停止")
    sum_old = sum(old_len.values())

    # 目标行是否挂在进度表上
    attached = 0
    for t in ("review_schedule", "submissions", "wrong_book", "question_notes"):
        attached += cur.execute(
            f"SELECT COUNT(*) FROM {t} WHERE question_id IN ({','.join('?' * len(PRAC_DELETE))})",
            PRAC_DELETE).fetchone()[0]

    print(f"[plan] 保留练习库 id={PRAC_ANCHOR} 改写为综合大题")
    print(f"[plan] 删除练习库 {PRAC_DELETE}")
    print(f"[plan] 原有 6 行答案合计 {sum_old} 字 -> 合并后 1 行 {len(reference)} 字")
    print(f"[plan] 待删行挂在进度表上的记录数: {attached} (应为 0)")

    if attached:
        print("[warn] 存在进度记录，按不丢进度原则需先重定向；已停止，请确认后再跑。")
        con.close()
        ap.error("请先重定向学习记录")

    if not args.apply:
        print("[info] dry-run，未改动。确认后加 --apply")
        con.close()
        return

    bak = str(database) + ".bak_" + str(time.time_ns())
    backup_sqlite(database, bak)
    print(f"[backup] {bak}")

    cur.execute(
        """UPDATE questions SET question_text=?, category=?, tags=?, difficulty=?,
               reference_answer=?, platform=?, keywords=? WHERE id=?""",
        (question_text, category, tags, difficulty, reference, platform, tags, PRAC_ANCHOR))
    print(f"[write] 改写 id={PRAC_ANCHOR}")

    cur.execute(f"DELETE FROM questions WHERE id IN ({','.join('?' * len(PRAC_DELETE))})", PRAC_DELETE)
    print(f"[write] 删除 {len(PRAC_DELETE)} 行")

    # 落盘母库 content 变更
    with open(BANK, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("[write] 母库已落盘")

    con.commit()

    # 校验
    n = cur.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    gone = cur.execute(
        f"SELECT COUNT(*) FROM questions WHERE id IN ({','.join('?' * len(PRAC_DELETE))})", PRAC_DELETE).fetchone()[0]
    orphan = 0
    for t in ("review_schedule", "submissions", "wrong_book"):
        orphan += cur.execute(
            f"SELECT COUNT(*) FROM {t} WHERE question_id NOT IN (SELECT id FROM questions)").fetchone()[0]
    r = cur.execute("SELECT LENGTH(reference_answer) FROM questions WHERE id=?", (PRAC_ANCHOR,)).fetchone()
    print(f"[verify] 练习库题数 {n} | 已删残留 {gone} (应0) | 进度孤儿 {orphan} (应0)")
    print(f"[verify] 综合大题 id={PRAC_ANCHOR} 答案长度 {r[0]}")
    con.close()
    print(f"[done] 备份 {bak}")


if __name__ == "__main__":
    main()
