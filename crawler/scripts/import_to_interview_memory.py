#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将转换后的题库 JSON 安全导入 interview_memory.db。

安全特性（满足「处理失败可回滚」）：
1. 导入前通过 SQLite backup API 生成 .bak_<时间戳>（包含已提交的 WAL 数据）。
2. 单事务：全部写入在一个 BEGIN/COMMIT 内；任何异常 -> ROLLBACK。
3. 导入前按 question_text 精确去重，已存在则跳过（幂等、可安全重跑）。
4. 写入后校验：post == pre + inserted，不符则 ROLLBACK 并报错退出。
5. 仅 INSERT questions 表（与 app import-batch 行为一致，不触碰 review_schedule）。

用法：
  python import_to_interview_memory.py                 # 正式导入
  python import_to_interview_memory.py --dry-run       # 只统计，不写入
  python import_to_interview_memory.py --json X --db Y # 自定义路径
"""
import argparse
import json
import os
import sqlite3
import sys
import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_JSON = HERE.parent / "data" / "tmp" / "interview_memory_import.json"
sys.path.insert(0, str(HERE.parent.parent))
from scripts.sqlite_target import backup_sqlite, sqlite_target


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=DEFAULT_JSON)
    ap.add_argument("--db", help="显式覆盖 DATABASE_URL 的 SQLite 文件路径")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        args.db = sqlite_target(args.db)
    except ValueError as exc:
        ap.error(str(exc))

    if not os.path.exists(args.json):
        sys.exit(f"[X] JSON 不存在: {args.json}")
    if not os.path.exists(args.db):
        sys.exit(f"[X] DB 不存在: {args.db}")

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)
    questions = data.get("questions", [])
    print(f"[1] 待导入题数: {len(questions)}")

    # —— 步骤2：一致性快照（仅正式写入前做；dry-run 不备份）——
    bak = None
    mode = "ro" if args.dry_run else "rw"
    conn = sqlite3.connect(Path(args.db).as_uri() + "?mode=" + mode, uri=True)
    try:
        cur = conn.cursor()
        cur.execute("BEGIN" if args.dry_run else "BEGIN IMMEDIATE")
        if not args.dry_run:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            bak = f"{args.db}.bak_{ts}"
            # 不能仅复制 .db：WAL 模式下最新提交可能仍在 -wal 文件中。
            backup_sqlite(args.db, bak)
            print(f"[2] 已备份 DB -> {bak}")

        pre = cur.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        print(f"[3] 导入前 questions 表行数: {pre}")

        if args.dry_run:
            existing = set(r[0] for r in cur.execute("SELECT question_text FROM questions").fetchall())
            incoming = {(q.get("question") or "").strip() for q in questions}
            skip = len(questions) - len(incoming - existing - {""})
            print(f"[DRY-RUN] 将新增: {len(questions) - skip}, 将跳过(已存在): {skip}; 不写入。")
            return

        inserted = 0
        skipped = 0
        for q in questions:
            text = (q.get("question") or "").strip()
            if not text:
                skipped += 1
                continue
            if cur.execute("SELECT 1 FROM questions WHERE question_text=?", (text,)).fetchone():
                skipped += 1
                continue
            cat = (q.get("category") or "").strip()
            kps = q.get("key_points") or []
            if isinstance(kps, str):
                kps = [kps]
            tag_parts = [cat] + [str(k).strip() for k in kps]
            tags = ",".join(sorted({t for t in tag_parts if t}))
            ref = q.get("reference_answer") or ""
            diff = int(q.get("difficulty") or 2)
            plat = (q.get("platform") or "")[:50]
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                "INSERT INTO questions "
                "(platform,category,tags,difficulty,question_text,reference_answer,created_at,images,keywords) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (plat, cat, tags, diff, text, ref, now, "", ""),
            )
            inserted += 1

        post = cur.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        expected = pre + inserted
        print(f"[4] 插入 {inserted}, 跳过 {skipped}; 校验 pre({pre}) + inserted({inserted}) = {expected}, post = {post}")
        if post != expected:
            raise RuntimeError(f"行数校验失败: 期望 {expected}, 实际 {post}，触发回滚！")

        conn.commit()
        print(f"[5] COMMIT 成功。新增 {inserted} 题，题库总量 {post}。")
        print(f"    如需回滚: 停止应用后，通过 SQLite backup API 将 {bak} 恢复到 {args.db}。")
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"[!] 异常，已 ROLLBACK: {e}")
        print(f"    原库未改动，可恢复备份: {bak}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
