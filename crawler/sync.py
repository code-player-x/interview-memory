#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键把母库净增题同步进 interview_memory.db（爬完即见）。

定位：crawler/ 下的桥接脚本。采集链路里**需要浏览器登录的爬取(harvest)仍为手动**，
sync 跑「爬完之后」的本地流水线：去重补答案(可选) -> 字段转换 -> 写练习库。

默认只做 convert + import（桥接），因为母库 questions-bank.json 此时应已含新题
（由 merge_5src_clean.py + add_refined_to_bank.py 写入）。

用法：
  python crawler/sync.py                 # 推净增题进练习库（自动跳过已存在的题）
  python crawler/sync.py --dry-run       # 只统计净增数，不写 DB
  python crawler/sync.py --with-fill     # 同步前先补答案（需 DEEPSEEK_API_KEY，8 并发）
  python crawler/sync.py --category 手撕算法   # 仅同步某分类
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # crawler/
SCRIPTS = HERE / "scripts"
PROJ_DATA = HERE / "data"
BANK = PROJ_DATA / "questions-bank.json"
OUT = PROJ_DATA / "tmp" / "interview_memory_import.json"
TARGET_DB = HERE.parent / "data" / "interview_memory.db"   # 仓库根/data（与 crawler 同级）
# 托管 Python（与 harvest/merge 等脚本一致）
VENV = Path(r"C:/Users/UserName/.workbuddy/binaries/python/envs/default/Scripts/python.exe")


def run(py: Path, *args):
    cmd = [str(VENV), str(py), *args]
    print("\n>> " + " ".join(cmd))
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        sys.exit(f"[X] 步骤失败 rc={rc}: {' '.join(cmd)}")
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只统计净增，不写 DB")
    ap.add_argument("--with-fill", action="store_true", help="同步前先补答案(需 DEEPSEEK_API_KEY)")
    ap.add_argument("--category", default="", help="仅同步分类含该子串的题")
    ap.add_argument("--no-cross", action="store_true", help="不做与练习库的交叉去重(仅源内去重)")
    args = ap.parse_args()

    if not BANK.exists():
        sys.exit(f"[X] 母库不存在: {BANK}\n   先跑 harvest + merge_5src_clean + add_refined_to_bank 生成它。")
    if not TARGET_DB.exists():
        sys.exit(f"[X] 练习库不存在: {TARGET_DB}\n   先启动 interview-memory（会自动建库）。")

    # 1) 可选：补答案
    if args.with_fill:
        run(SCRIPTS / "fill_answers_deepseek.py", "--workers", "8")

    # 2) 转换（读母库 + 与练习库交叉去重，产出 import JSON；对 DB 只读）
    conv = ["--bank", str(BANK), "--out", str(OUT)]
    if args.category:
        conv += ["--category", args.category]
    if args.no_cross:
        conv.append("--no-cross")
    run(SCRIPTS / "convert_to_interview_memory.py", *conv)

    # 3) 导入（写练习库；--dry-run 时只统计）
    imp = ["--json", str(OUT), "--db", str(TARGET_DB)]
    if args.dry_run:
        imp.append("--dry-run")
    run(SCRIPTS / "import_to_interview_memory.py", *imp)

    print("\n[done] 同步完成。" + ("（dry-run，未写入）" if args.dry_run else ""))


if __name__ == "__main__":
    main()
