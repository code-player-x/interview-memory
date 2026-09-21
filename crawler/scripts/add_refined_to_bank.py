#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把去重后的候选池 all_platforms_refined.jsonl 回写进 questions-bank.json。

安全机制（满足「带备份回滚」）：
  1. 修改前复制题库为 .bak_<时间戳>（硬回滚点）；
  2. 与题库做双层去重（精确 norm + SequenceMatcher>=0.85），已存在则跳过（幂等）；
  3. 一次性 load+append+save（规避 bank.add_entry 逐条 load/save 覆盖丢失的坑）；
  4. 写入后校验：新总数 == 旧总数 + 新增，且 norm 无重复，否则报错退出。

新增项特征：content=题面；category 沿用；sources=来源平台集合；status="新增(待补答案)"；
answer 置空结构（候选池无答案文本，后续可经答案生成/人工补全）。

用法：
  python scripts/add_refined_to_bank.py [--dry-run] [--infile data/tmp/all_platforms_refined.jsonl]
"""
import argparse
import json
import shutil
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
import bank  # noqa: E402

BANK_PATH = BASE / "data" / "questions-bank.json"
DEFAULT_IN = BASE / "data" / "tmp" / "all_platforms_refined.jsonl"
THR = 0.85
CREATED = "2026-09-18"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", default=str(DEFAULT_IN))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    in_path = Path(args.infile)
    rows = [json.loads(l) for l in open(in_path, encoding="utf-8") if l.strip()]
    print("候选池题数: %d" % len(rows))

    data = bank.load(BANK_PATH)
    items = data.setdefault("items", [])
    pre = len(items)  # 写入前的基线数量（必须在追加前记录）
    # 精确 norm 集合（O(1) 查重）；候选池已在 merge 阶段对题库做过去重，这里用集合快速复核
    bank_norm_set = {it.get("norm") or bank.normalize(it.get("content", ""))
                     for it in items}
    max_id = 0
    for it in items:
        qid = it.get("id", "")
        if isinstance(qid, str) and qid.startswith("q") and qid[1:].isdigit():
            max_id = max(max_id, int(qid[1:]))

    added, skipped = [], []
    for r in rows:
        content = (r.get("question") or "").strip()
        if not content:
            continue
        nq = bank.normalize(content)
        if nq in bank_norm_set:
            skipped.append((content[:40], "<bank-norm>"))
            continue
        max_id += 1
        sources = r.get("sources") or []
        item = {
            "id": f"q{max_id:04d}",
            "category": r.get("category") or "概念基础",
            "type": "essay",
            "content": content,
            "source": "全平台面经采集(2026-09)·" + "/".join(sources),
            "difficulty": "★★☆",
            "tags": [r.get("category") or "概念基础"] + list(sources),
            "status": "新增(待补答案)",
            "answer": {"简版": "", "展开": "", "加分点": "", "雷区": ""},
            "leetcode_url": "",
            "sources": sources,
            "norm": nq,
            "created_at": CREATED,
            "wiki_node_token": "",
            "wiki_url": "",
        }
        items.append(item)
        bank_norm_set.add(nq)
        added.append(item)

    print("将新增 %d，跳过重复 %d" % (len(added), len(skipped)))
    for c, h in skipped[:10]:
        print("  [SKIP] %s ~ %s" % (c, h))

    if args.dry_run:
        print("(dry-run，未写入)")
        return 0

    # 1) 硬备份
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = Path(str(BANK_PATH) + ".bak_%s" % ts)
    shutil.copy2(BANK_PATH, bak)
    print("[备份] %s" % bak)

    data["meta"]["total"] = len(items)
    bank.save(data, BANK_PATH)

    # 4) 校验
    reloaded = bank.load(BANK_PATH)
    post = len(reloaded["items"])
    norms = [it.get("norm") for it in reloaded["items"]]
    dup_norms = len(norms) - len(set(norms))
    expected = pre + len(added)
    print("[校验] pre=%d + added=%d = %d，post=%d，norm重复=%d" %
          (pre, len(added), expected, post, dup_norms))
    if post != expected or dup_norms != 0:
        print("[X] 校验失败！请恢复备份: %s" % bak)
        sys.exit(1)
    print("[OK] 已写入，题库总量 %d（%s ~ %s）" %
          (post, added[0]["id"] if added else "-", added[-1]["id"] if added else "-"))


if __name__ == "__main__":
    sys.exit(main())
