#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""修复 dedup_sync_practice.py 富化阶段的"答案降级"问题。

背景：富化阶段用母库数据整体覆写练习库匹配行，
      reference_answer 被替换成母库版本。当母库答案比练习库
      原有答案更简略时造成内容丢失（实测 411 行，丢失 14.4 万字）。

策略（enrich but never downgrade）：
      对复用了原 id 的富化行，若"备份中的原答案"比"当前答案"更长，
      则恢复原答案；否则保留母库（更长/更丰富）答案。
      分类/标签/难度/来源等富化结果保持不变，只修 reference_answer。

用法：
    python scripts/repair_answer_downgrade.py --backup <备份db> [--apply]
"""
import argparse
import os
import shutil
import sqlite3
import sys
import time

DB = "G:/interview-memory/data/interview_memory.db"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backup", required=True, help="同步前的备份 db（还原来源）")
    ap.add_argument("--db", default=DB)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.backup):
        print(f"[error] 备份不存在: {args.backup}")
        sys.exit(1)

    con = sqlite3.connect(args.db)
    bak = sqlite3.connect(args.backup)

    old = {r[0]: (r[1] or "") for r in bak.execute(
        "SELECT id, reference_answer FROM questions")}
    cur_rows = {r[0]: (r[1] or "") for r in con.execute(
        "SELECT id, reference_answer FROM questions")}

    common = set(old) & set(cur_rows)
    restore = [i for i in common if len(old[i]) > len(cur_rows[i])]

    lost = sum(len(old[i]) - len(cur_rows[i]) for i in restore)
    print(f"[scan] 共同 {len(common)} 行 | 需要恢复（原答案更长） {len(restore)} 行 "
          f"| 可挽回 {lost} 字")

    top = sorted(restore, key=lambda i: len(old[i]) - len(cur_rows[i]), reverse=True)[:8]
    print("[scan] 恢复幅度 Top8:")
    for i in top:
        print(f"  +{len(old[i])-len(cur_rows[i]):5d}  {len(cur_rows[i])}->{len(old[i])}  (id={i})")

    if not args.apply:
        print("[info] dry-run，未改动。确认后加 --apply")
        con.close(); bak.close()
        return

    bak2 = args.db + ".bak_repair_" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(args.db, bak2)
    print(f"[backup] {bak2}")

    cur = con.cursor()
    for i in restore:
        cur.execute("UPDATE questions SET reference_answer=? WHERE id=?", (old[i], i))
    con.commit()
    print(f"[write] 已恢复 {len(restore)} 行答案")

    # 校验
    after = {r[0]: (r[1] or "") for r in con.execute(
        "SELECT id, reference_answer FROM questions")}
    still = sum(1 for i in common if len(after[i]) < len(old[i]))
    empty = sum(1 for v in after.values() if not v.strip())
    print(f"[verify] 仍短于原答案的行: {still} (应=0) | 空答案: {empty}")
    print(f"[verify] 总题数 {len(after)}")

    # 进度孤儿校验
    for t in ("review_schedule", "submissions", "wrong_book"):
        try:
            o = cur.execute(
                f"SELECT COUNT(*) FROM {t} WHERE question_id NOT IN (SELECT id FROM questions)"
            ).fetchone()[0]
            print(f"[verify] {t} 孤儿外键 {o} (应=0)")
        except sqlite3.OperationalError:
            pass

    print(f"[done] 备份 {bak2}")
    con.close(); bak.close()


if __name__ == "__main__":
    main()
