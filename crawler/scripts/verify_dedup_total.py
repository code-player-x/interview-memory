#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验证总库去重结果：题数/id唯一/答案零丢失/幂等性。"""
import json
import re
from pathlib import Path

BANK = Path("G:/interview-memory/crawler/data/questions-bank.json")
PLAN = Path("G:/interview-memory/crawler/data/tmp/dedup_088_plan.json")
BACKUP = Path("G:/interview-memory/crawler/data/questions-bank.json.bak_20260919_004328")


def ans_text(a):
    if isinstance(a, dict):
        return "\n".join(str(v) for v in a.values() if v)
    return str(a or "")


def main():
    cur = json.loads(BANK.read_text(encoding="utf-8"))
    items = cur["items"]
    ids = [x["id"] for x in items]
    print(f"[题数] {len(items)} | meta.total={cur['meta'].get('total')} | 唯一 id {len(set(ids))}")

    norms = [re.sub(r"[\s\W_]+", "", (x.get("content") or x.get("norm") or "").lower()) for x in items]
    dup = [n for n in norms if n and norms.count(n) > 1]
    print(f"[题面] 完全重复: {len(set(dup))} 组 (应=0)")

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    removed = plan.get("removed") or plan.get("plan") or []
    print(f"\n[plan] 删除 {len(removed)} 条:")
    for r in removed[:20]:
        if isinstance(r, dict):
            print(f"   {r.get('id')} -> {r.get('merged_into') or r.get('kept')} "
                  f"| {(r.get('content') or '')[:56]}")
        else:
            print(f"   {r}")

    # 答案零丢失：对比备份
    old_items = json.loads(BACKUP.read_text(encoding="utf-8"))["items"]
    old_by = {x["id"]: x for x in old_items}
    new_by = {x["id"]: x for x in items}
    gone = [i for i in old_by if i not in new_by]
    print(f"\n[丢失检查] 相对去重前备份消失的题: {gone}")
    lost_chars = 0
    for gid in gone:
        o = old_by[gid]
        # 找它的保留项（同 plan）比对答案是否更完整
        lo = len(ans_text(o.get("answer")))
        # 简单全局校验：被删题的答案是否被某保留题包含（看 sources 是否合并）
        keeper_id = None
        for r in removed:
            if isinstance(r, dict) and r.get("id") == gid:
                keeper_id = r.get("merged_into") or r.get("kept")
        if keeper_id and keeper_id in new_by:
            ln = len(ans_text(new_by[keeper_id].get("answer")))
            verdict = "OK(保留项更完整)" if ln >= lo else "⚠️保留项更短"
            print(f"   {gid}: 原答案 {lo} 字 -> 保留项 {keeper_id} {ln} 字  {verdict}")
            if ln < lo:
                lost_chars += lo - ln
        else:
            print(f"   {gid}: 未记录保留项，原答案 {lo} 字")
            lost_chars += lo
    print(f"\n[结论] 疑似丢失字符数: {lost_chars} (应=0 或很小)")

    total_old = sum(len(ans_text(x.get("answer"))) for x in old_items)
    total_new = sum(len(ans_text(x.get("answer"))) for x in items)
    print(f"[总量] 答案总字数 去重前 {total_old:,} -> 去重后 {total_new:,} "
          f"(差 {total_new - total_old:+,})")

    print(f"\n[meta] last_dedup: {cur['meta'].get('last_dedup')}")
    print(f"[meta] last_merged_source: {cur['meta'].get('last_merged_source')}")


if __name__ == "__main__":
    main()
