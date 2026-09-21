#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查去重合并对之间的【直接】余弦，识别"被搭桥的传递合并"。

并查集会把 A~B、B~C 的边合并成同一组，即使 A 与 C 直接相似度 < 阈值。
本脚本列出每对「被删 -> 保留」的直接余弦，凡 < 阈值者即为传递桥接合并，需人工确认。

用法：python scripts/check_transitive.py --plan <plan.json> --thresh 0.88
"""
import argparse
import json
from pathlib import Path

PLAN = Path("G:/interview-memory/crawler/data/tmp/dedup_088_plan.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(PLAN))
    ap.add_argument("--thresh", type=float, default=0.88)
    args = ap.parse_args()

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    rows = []
    for r in plan.get("removed", []):
        rows.append((r.get("id"), r.get("kept_id"), r.get("max_cos")))
    rows.sort(key=lambda x: (x[2] is None, x[2]))

    thr = args.thresh
    bridged = [r for r in rows if r[2] is not None and r[2] < thr]
    print(f"合并对共 {len(rows)} 组；其中【直接余弦 < {thr}】的传递桥接: {len(bridged)} 组\n")

    print("== 直接余弦最低的 12 组 ==")
    for rid, kid, c in rows[:12]:
        flag = "⚠️传递桥接" if (c is not None and c < thr) else ""
        print(f"  {rid} -> {kid}  cos={c}  {flag}")

    if bridged:
        print(f"\n== 全部传递桥接（直接相似度未达阈值，靠第三方连边合并）==")
        for rid, kid, c in bridged:
            print(f"  {rid} -> {kid}  cos={c}")

    n_direct = len(rows) - len(bridged)
    print(f"\n小结：{n_direct} 组为直接近重（≥{thr}），{len(bridged)} 组为传递桥接。")


if __name__ == "__main__":
    main()
