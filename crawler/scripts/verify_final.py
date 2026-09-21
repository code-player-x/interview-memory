#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""最终验证：修复后的去重是否零内容丢失 + 幂等。"""
import json
import re
from pathlib import Path

BANK = Path("G:/interview-memory/crawler/data/questions-bank.json")
PRE = Path("G:/interview-memory/crawler/data/questions-bank.json.bak_20260919_005226")
PLAN = Path("G:/interview-memory/crawler/data/tmp/dedup_088_plan.json")
BAD = Path("G:/interview-memory/crawler/data/questions-bank.json.bad_dedup_audit_20260919")


def ans(a):
    if isinstance(a, dict):
        return "\n".join(str(v) for v in a.values() if v)
    return str(a or "")


def main():
    cur = json.loads(BANK.read_text(encoding="utf-8"))
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    items, old_items = cur["items"], pre["items"]
    by_old = {x["id"]: x for x in old_items}
    by_new = {x["id"]: x for x in items}

    print(f"[题数] {len(items)} | meta.total={cur['meta'].get('total')} | 唯一 id {len({x['id'] for x in items})}")
    norms = [re.sub(r"[\s\W_]+", "", (x.get("content") or x.get("norm") or "").lower()) for x in items]
    print(f"[题面] 完全重复: {len({n for n in norms if n and norms.count(n) > 1})} 组 (应=0)")

    gone = [i for i in by_old if i not in by_new]
    print(f"\n[被删除] {gone}")

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    print("\n[合并明细]")
    for r in plan.get("removed", []):
        rid, kid = r.get("id"), r.get("kept_id")
        gc = by_old.get(rid, {}).get("content", "")
        kc = by_new.get(kid, {}).get("content", "")
        gl = len(ans(by_old.get(rid, {}).get("answer")))
        kl = len(ans(by_new.get(kid, {}).get("answer")))
        verdict = "OK 保留项更完整" if kl >= gl else "⚠️ 降级"
        print(f"  {rid} -> {kid}  cos={r.get('max_cos')}  {verdict}")
        print(f"     删: [{rid}] {gl}字 | {gc[:52]}")
        print(f"     留: [{kid}] {kl}字 | {kc[:52]}")
        # 被删答案内容是否已被保留项覆盖
        import difflib
        ga, ka = ans(by_old.get(rid, {}).get("answer")), ans(by_new.get(kid, {}).get("answer"))
        sents = [s.strip() for s in re.split(r"[\n。；]", ga) if len(s.strip()) > 12]
        miss = [s for s in sents if s[:14] not in ka]
        print(f"     删除答案中未被覆盖的句段: {len(miss)} / {len(sents)}")
        for s in miss[:4]:
            print(f"        - {s[:64]}")

    t_old = sum(len(ans(x.get("answer"))) for x in old_items)
    t_new = sum(len(ans(x.get("answer"))) for x in items)
    print(f"\n[总量] 答案总字数 {t_old:,} -> {t_new:,} (差 {t_new - t_old:+,})")

    if BAD.exists():
        bad = json.loads(BAD.read_text(encoding="utf-8"))["items"]
        t_bad = sum(len(ans(x.get("answer"))) for x in bad)
        print(f"[对照] 修复前有降级的结果: {t_bad:,} 字；修复后 {t_new:,} 字 "
              f"-> 挽回 {t_new - t_bad:+,} 字")

    print(f"\n[meta] method={cur['meta'].get('last_dedup')}")


if __name__ == "__main__":
    main()
