#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将转换后的题库 JSON 安全导入 interview_memory.db。

安全特性（满足「处理失败可回滚」）：
1. 导入前自动复制 DB 文件为 .bak_<时间戳>（硬回滚点，独立于事务）。
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
import shutil
import sqlite3
import sys
import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_JSON = HERE.parent / "data" / "tmp" / "interview_memory_import.json"
DEFAULT_DB = HERE.parent.parent / "data" / "interview_memory.db"  # 仓库根/data（与 crawler 同级）


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=DEFAULT_JSON)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.json):
        sys.exit(f"[X] JSON 不存在: {args.json}")
    if not os.path.exists(args.db):
        sys.exit(f"[X] DB 不存在: {args.db}")

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)
    questions = data.get("questions", [])
    print(f"[1] 待导入题数: {len(questions)}")

    # —— 步骤2：文件级硬备份（仅正式写入前做；dry-run 不备份）——
    bak = None
    if not args.dry_run:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = f"{args.db}.bak_{ts}"
        shutil.copy2(args.db, bak)
        print(f"[2] 已备份 DB -> {bak}")

    conn = sqlite3.connect(args.db)
    try:
        cur = conn.cursor()
        pre = cur.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        print(f"[3] 导入前 questions 表行数: {pre}")

        if args.dry_run:
            existing = set(r[0] for r in cur.execute("SELECT question_text FROM questions").fetchall())
            skip = sum(1 for q in questions if q.get("question", "").strip() in existing)
            print(f"[DRY-RUN] 将新增: {len(questions) - skip}, 将跳过(已存在): {skip}; 不写入。")
            conn.close()
            return

        inserted = 0
        skipped = 0
        cur.execute("BEGIN")
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
        print(f"    如需回滚: 用备份 {bak} 覆盖 {args.db} 即可。")
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
