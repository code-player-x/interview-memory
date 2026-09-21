#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""交叉验证：母库 vs Claw Agent 库 重叠题的答案差异比对（只读）。

输出：
  - 重叠题数量、双方答案长度对比
  - 母库答案更丰富 / Agent 库答案更丰富 的分布
  - Agent 库独有的新题
  - 需要人工判定的答案冲突（同一题面但答案长度差 > 3 倍且无明显包含关系）
"""
import argparse
import json
import re
from pathlib import Path

MOTHER = "G:/interview-memory/crawler/data/questions-bank.json"
AGENT = "C:/Users/UserName/WorkBuddy/Claw/题库/agent_interview_bank.json"
BASIC = "C:/Users/UserName/WorkBuddy/Claw/题库/basic_interview_bank.json"


def norm(s):
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


def ans_text(a):
    if isinstance(a, dict):
        parts = []
        for k in ("简版", "展开", "加分点", "雷区", "评分要点"):
            v = a.get(k)
            if isinstance(v, list):
                v = "\n".join(map(str, v))
            if v:
                parts.append(str(v))
        return "\n".join(parts)
    return str(a or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=AGENT, help="外部来源库路径")
    args = ap.parse_args()

    m = json.loads(Path(MOTHER).read_text(encoding="utf-8"))
    a = json.loads(Path(args.src).read_text(encoding="utf-8"))
    mi, aq = m["items"], a["questions"]
    print(f"来源库: {args.src}")
    print(f"来源库名: {a.get('bank_name')} v{a.get('version')}\n")

    mmap = {}
    for x in mi:
        k = norm(x.get("content") or x.get("norm"))
        if k:
            mmap.setdefault(k, x)

    matched = []      # (mother_item, agent_item)
    only_agent = []
    for x in aq:
        k = norm(x.get("question"))
        if k and k in mmap:
            matched.append((mmap[k], x))
        else:
            only_agent.append(x)

    print(f"母库 {len(mi)} 题 | Agent 库 {len(aq)} 题")
    print(f"【重叠】{len(matched)} 条 | 【仅 Agent 库有】{len(only_agent)} 条\n")

    print("=" * 70)
    print("一、重叠题答案长度对比")
    print("=" * 70)
    rows = []
    for mit, ait in matched:
        ml = len(ans_text(mit.get("answer")))
        al = len(ans_text(ait.get("reference_answer")) + "".join(ait.get("key_points") or []))
        rows.append((ait["id"], mit["id"], al, ml, max(al, ml) / max(1, min(al, ml)),
                     ait.get("category", ""), (mit.get("content") or "")[:44]))
    rows.sort(key=lambda r: -r[2])
    mom_better = [r for r in rows if r[3] > r[2] * 1.3]
    agt_better = [r for r in rows if r[2] > r[3] * 1.3]
    similar = [r for r in rows if r not in mom_better and r not in agt_better]
    print(f"  母库答案明显更丰富 : {len(mom_better)} 条")
    print(f"  Agent 库答案更丰富 : {len(agt_better)} 条")
    print(f"  两者接近          : {len(similar)} 条")

    print("\n  Agent 库答案更丰富（若>0，合并时需把其要点并入母库，否则会丢内容）:")
    for aid, mid, al, ml, ratio, cat, txt in agt_better[:15]:
        print(f"    [{aid}] {al}字 vs 母库[{mid}] {ml}字  x{ratio:.1f} | {cat} | {txt}")

    print("\n  差距最大 Top8（无论方向）:")
    for aid, mid, al, ml, ratio, cat, txt in sorted(rows, key=lambda r: -r[4])[:8]:
        who = "Agent库更长" if al > ml else "母库更长"
        print(f"    x{ratio:.1f} {who} | [{aid}]{al} vs [{mid}]{ml} | {txt}")

    print("\n" + "=" * 70)
    print("二、Agent 库独有题（合并需新增）：" + str(len(only_agent)) + " 条")
    print("=" * 70)
    for x in only_agent:
        print(f"  [{x['id']}] ({x.get('category')}) {x.get('question','')[:70]}")
        print(f"        答案 {len(ans_text(x.get('reference_answer')))} 字, "
              f"key_points {len(x.get('key_points') or [])} 个")

    print("\n" + "=" * 70)
    print("三、两侧 key_points / tags 覆盖情况")
    print("=" * 70)
    have_kp = sum(1 for _, ait in matched if ait.get("key_points"))
    print(f"  重叠题中 Agent 侧有 key_points: {have_kp} / {len(matched)}")
    n_conflict = 0
    for mit, ait in matched:
        mt, at = (mit.get("answer") or {}).get("展开", ""), str(ait.get("reference_answer") or "")
        ml, al = len(str(mt)), len(at)
        # 长度差 >3 倍即视为需要人工看一眼的潜在冲突
        if max(ml, al) / max(1, min(ml, al)) > 3:
            n_conflict += 1
    print(f"  展开答案长度差 >3 倍（潜在冲突，需人工判定）: {n_conflict} 条")


if __name__ == "__main__":
    main()
