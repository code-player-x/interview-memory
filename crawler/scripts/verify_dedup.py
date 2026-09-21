#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用去重核验：对比去重前备份，列出删除项、保留项、是否降级、内容净变化。

用法：python scripts/verify_dedup.py --pre <去重前备份> [--plan <plan.json>]
"""
import argparse
import json
import re
from pathlib import Path

BANK = Path("G:/interview-memory/crawler/data/questions-bank.json")
PLAN = Path("G:/interview-memory/crawler/data/tmp/dedup_088_plan.json")


def ans(a):
    if isinstance(a, dict):
        return "\n".join(str(v) for v in a.values() if v)
    return str(a or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre", required=True)
    ap.add_argument("--plan", default=str(PLAN))
    args = ap.parse_args()

    cur = json.loads(BANK.read_text(encoding="utf-8"))
    pre = json.loads(Path(args.pre).read_text(encoding="utf-8"))
    by_old = {x["id"]: x for x in pre["items"]}
    by_new = {x["id"]: x for x in cur["items"]}

    print(f"[题数] {len(cur['items'])} (去重前 {len(pre['items'])}) "
          f"| 唯一 id {len({x['id'] for x in cur['items']})}")
    norms = [re.sub(r"[\s\W_]+", "", (x.get("content") or x.get("norm") or "").lower())
             for x in cur["items"]]
    print(f"[题面] 完全重复 {len({n for n in norms if n and norms.count(n) > 1})} 组 (应=0)")

    gone = [i for i in by_old if i not in by_new]
    print(f"\n[被删] {len(gone)} 条")

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    downs, covered_loss = [], 0
    for r in plan.get("removed", []):
        rid, kid = r.get("id"), r.get("kept_id")
        o, k = by_old.get(rid), by_new.get(kid)
        if not o or not k:
            continue
        ol, kl = len(ans(o.get("answer"))), len(ans(k.get("answer")))
        if kl < ol:
            downs.append((rid, kid, ol, kl))
        ga, ka = ans(o.get("answer")), ans(k.get("answer"))
        sents = [s.strip() for s in re.split(r"[\n。；]", ga) if len(s.strip()) > 12]
        miss = [s for s in sents if s[:14] not in ka]
        covered_loss += sum(len(s) for s in miss)
        if kl < ol:
            print(f"  ⚠️降级 {rid}({ol}字) -> 保留 {kid}({kl}字) | {o.get('content','')[:44]}")

    print(f"\n[降级检查] 保留项短于被删项的: {len(downs)} 组 (应=0)")
    print(f"[内容缺口] 被删答案中未被保留项覆盖的字数合计: {covered_loss:,}")

    t_old = sum(len(ans(x.get("answer"))) for x in pre["items"])
    t_new = sum(len(ans(x.get("answer"))) for x in cur["items"])
    print(f"[总量] 答案总字数 {t_old:,} -> {t_new:,} (差 {t_new - t_old:+,})")
    print(f"[meta] {cur['meta'].get('last_dedup')}")


if __name__ == "__main__":
    main()
