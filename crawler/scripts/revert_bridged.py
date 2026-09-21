#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""还原「被搭桥的传递合并」。

并查集会把 A~B、B~C 的边并成一组，导致 A 被合并进 C，
即便 A 与 C 的【直接】余弦并未达到阈值。这类合并不符合"阈值=0.88"的口径，
属于边界模糊，应还原为两条独立题目。

本脚本按 plan.json 中 max_cos < thresh 挑出这些对，把被删项插回总库，
并从保留项的 _merged_from / sources 中摘掉对应记录。

用法：python scripts/revert_bridged.py --pre <去重前备份> [--thresh 0.88] [--apply]
"""
import argparse
import json
import shutil
import time
from pathlib import Path

BANK = Path("G:/interview-memory/crawler/data/questions-bank.json")
PLAN = Path("G:/interview-memory/crawler/data/tmp/dedup_088_plan.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre", required=True, help="去重前备份（被删项原文来源）")
    ap.add_argument("--plan", default=str(PLAN))
    ap.add_argument("--thresh", type=float, default=0.88)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    cur = json.loads(BANK.read_text(encoding="utf-8"))
    pre = json.loads(Path(args.pre).read_text(encoding="utf-8"))
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))

    by_old = {x["id"]: x for x in pre["items"]}
    by_cur = {x["id"]: x for x in cur["items"]}

    bridged = []
    for r in plan.get("removed", []):
        c = r.get("max_cos")
        if c is not None and c < args.thresh:
            bridged.append((r.get("id"), r.get("kept_id"), c, r.get("content", "")))

    print(f"[识别] 传递桥接（直接余弦 < {args.thresh}）: {len(bridged)} 组")
    for rid, kid, c, _ in bridged:
        src = by_old.get(rid)
        ln = sum(len(str(v)) for v in (src.get("answer") or {}).values()) if src else 0
        print(f"   {rid}({ln}字) -> 曾并入 {kid}  cos={c}")

    if not bridged:
        print("[info] 无需要还原的对")
        return

    if not args.apply:
        print("[info] dry-run，未改动。确认后加 --apply")
        return

    bak = str(BANK) + ".bak_" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(BANK, bak)
    print(f"[backup] {bak}")

    restored = 0
    for rid, kid, c, _ in bridged:
        src = by_old.get(rid)
        if not src:
            print(f"   [warn] {rid} 不在备份中，跳过")
            continue
        if rid in by_cur:
            print(f"   [skip] {rid} 已存在")
            continue
        cur["items"].append(src)
        by_cur[rid] = src
        restored += 1
        # 从保留项摘掉溯源
        k = by_cur.get(kid)
        if k:
            mf = [x for x in (k.get("_merged_from") or []) if x != rid]
            if mf:
                k["_merged_from"] = mf
            else:
                k.pop("_merged_from", None)
            srcs = [s for s in (k.get("sources") or [])
                    if str(s) != f"recovered-from:{rid}"]
            k["sources"] = srcs

    cur["meta"]["total"] = len(cur["items"])
    cur["meta"]["last_bridge_revert"] = {
        "threshold": args.thresh,
        "reverted_pairs": [{"id": r, "was_merged_into": k, "direct_cos": c} for r, k, c, _ in bridged],
        "restored": restored,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    BANK.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[write] 已还原 {restored} 条，总库 {len(cur['items'])} 题")
    print(f"[done] 备份 {bak}")


if __name__ == "__main__":
    main()
