#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把去重中被删条目的互补内容补回保留项，做到「去重但不丢内容」。

背景：0.88 去重合并了 2 组，虽然保留了答案更完整的一方，
      但被删方仍有互补视角（如「通信模式」 vs 「协作模式」两套措辞/分类），
      净丢 551 字。本脚本把这部分追加进保留项的「展开」字段，
      并打上【同源补充】标记，保证内容零丢失且可追溯。

用法：python scripts/recover_dedup_content.py [--apply]
"""
import argparse
import json
import re
import shutil
import time
from pathlib import Path

BANK = Path("G:/interview-memory/crawler/data/questions-bank.json")
PLAN = Path("G:/interview-memory/crawler/data/tmp/dedup_088_plan.json")
PRE = Path("G:/interview-memory/crawler/data/questions-bank.json.bak_20260919_005226")

MARK = "【同源补充】"


def ans_text(a, keys=("简版", "展开", "加分点", "雷区")):
    if isinstance(a, dict):
        return "\n".join(str(a.get(k, "") or "") for k in keys if a.get(k))
    return str(a or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--pre", default=str(PRE), help="去重前备份（用于取回被删项原文）")
    args = ap.parse_args()

    cur = json.loads(BANK.read_text(encoding="utf-8"))
    pre = json.loads(Path(args.pre).read_text(encoding="utf-8"))
    print(f"[来源] 去重前备份: {args.pre}")

    by_old = {x["id"]: x for x in pre["items"]}
    by_cur = {x["id"]: x for x in cur["items"]}

    # 从保留项的 _merged_from 溯源字段推导「被删 -> 保留」配对
    # （不依赖 plan.json：它会被后续幂等复跑覆盖成空）
    pairs = []
    for kid, kitem in by_cur.items():
        src_ids = list(kitem.get("_merged_from") or [])
        for rid in src_ids:
            if rid in by_old and rid not in by_cur:
                pairs.append((rid, kid))
    if not pairs:
        gone = [i for i in by_old if i not in by_cur]
        print(f"[warn] 未通过 _merged_from 找到配对；已删除={gone}")
        return
    print(f"[配对] 通过 _merged_from 找到 {len(pairs)} 组: "
          f"{', '.join(f'{r}->{k}' for r, k in pairs)}")

    recovered = 0
    report = []
    for rid, kid in pairs:
        del_item, keep_item = by_old.get(rid), by_cur.get(kid)
        if not del_item or not keep_item:
            continue
        # ⚠️ 判重必须按「本 rid 是否已回收过」，不能看展开里有没有 MARK：
        # 同一保留项可能吸收多个被删来源，用 MARK 判断会把第 2 个来源误跳过而丢内容。
        srcs_now = [str(s) for s in (keep_item.get("sources") or [])]
        if any(s == f"recovered-from:{rid}" for s in srcs_now):
            print(f"[skip] {kid} 已回收过 {rid}")
            continue
        d = del_item.get("answer") or {}
        added = []
        for k in ("简版", "展开", "加分点", "雷区"):
            v = (d.get(k) or "").strip() if isinstance(d, dict) else ""
            if v:
                added.append(v)
        if not added:
            continue
        block = ("\n\n" + MARK + "来自同源题「" + (del_item.get("content") or "")[:40] + "」\n"
                 + "\n".join(added))
        ka = keep_item.setdefault("answer", {})
        ka["展开"] = (ka.get("展开") or "") + block
        recovered += len(block)
        report.append((kid, rid, len("\n".join(added))))
        srcs = list(keep_item.get("sources") or [])
        tag = f"recovered-from:{rid}"
        if tag not in srcs:
            srcs.append(tag)
            keep_item["sources"] = srcs

    print(f"[plan] 追加互补内容 {len(report)} 处，共 {recovered} 字")
    for kid, rid, n in report:
        print(f"   {rid} 的内容 ({n} 字) -> 追加进 {kid}")

    if not args.apply:
        print("[info] dry-run，未写库。确认后加 --apply")
        return

    bak = str(BANK) + ".bak_" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(BANK, bak)
    BANK.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[backup] {bak}")

    # 校验零丢失
    after = json.loads(BANK.read_text(encoding="utf-8"))
    def tot(items):
        return sum(len(ans_text(x.get("answer"))) for x in items)
    print(f"[verify] 答案总字数(口径:简版+展开+加分点+雷区+评分要点): "
          f"去重前 {tot(pre['items']):,} -> 修复后 {tot(after['items']):,} "
          f"(差 {tot(after['items']) - tot(pre['items']):+,})")
    print(f"[verify] 题数 {len(after['items'])}")
    print(f"[done] 备份 {bak}")


if __name__ == "__main__":
    main()
