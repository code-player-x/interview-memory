#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 Claw 题库（agent / basic）合并进母库，形成「总库」。

用法：
  python scripts/merge_total_bank.py --src <外部库.json> [--apply]

已验证的两次实绩：
  - agent_interview_bank.json(116)：108 条已存在于母库（答案 ~1:1 零冲突），真新增 8 条
  - basic_interview_bank.json(127)：仅 1 条重叠，真新增 126 条

合并策略（不丢内容）：
  - 重叠题：把外部库的 key_points / 原分类 **回填进母库 item 的 tags**（纯增量，不覆盖）
  - 独有题：按母库 schema 新增，编号从当前最大 q 号 +1 起
  - 原分类一律保留进 tags，映射后的母库分类只用于 category 字段
"""
import argparse
import json
import re
import shutil
import time
from collections import Counter
from pathlib import Path

MOTHER = Path("G:/interview-memory/crawler/data/questions-bank.json")
AGENT = Path("C:/Users/UserName/WorkBuddy/Claw/题库/agent_interview_bank.json")
BASIC = Path("C:/Users/UserName/WorkBuddy/Claw/题库/basic_interview_bank.json")

# Agent 库（QXXX）分类 -> 母库 8 类
AGENT_CAT_MAP = {
    "Agent架构": "概念基础",
    "记忆与上下文": "概念基础",
    "RAG与知识": "概念基础",
    "推理框架": "概念基础",
    "主流框架": "概念基础",
    "提示工程": "概念基础",
    "多模态与向量检索": "概念基础",
    "多模态与前沿架构": "概念基础",
    "评估与观测": "工程落地",
    "安全与对齐": "工程落地",
    "Agent 沙盒与安全执行": "工程落地",
    "模型微调与对齐": "工程落地",
    "工程与并发": "工程落地",
    "多智能体": "架构设计",
    "算法手撕": "手撕算法",
}

# 基础八股文库（BXXX）分类 -> 母库 8 类
BASIC_CAT_MAP = {
    "JVM": "后端八股",
    "并发编程": "后端八股",
    "ConcurrentHashMap": "后端八股",
    "MySQL": "后端八股",
    "Redis": "后端八股",
    "Kafka": "后端八股",
    "计算机网络": "后端八股",
    "操作系统": "后端八股",
    "分布式": "架构设计",
    "场景题": "工程落地",
    "智力题": "概念基础",
    "算法手撕": "手撕算法",
}


def norm(s):
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--src", default=str(AGENT), help="外部来源库路径")
    args = ap.parse_args()

    src_path = Path(args.src)
    is_basic = "basic" in src_path.name.lower()
    CAT_MAP = BASIC_CAT_MAP if is_basic else AGENT_CAT_MAP

    m = json.loads(MOTHER.read_text(encoding="utf-8"))
    a = json.loads(src_path.read_text(encoding="utf-8"))
    mi, aq = m["items"], a["questions"]
    SRC_NAME = f"Claw题库·{a.get('bank_name', '')} v{a.get('version', '')}".strip()

    print(f"[来源] {src_path.name}")
    print(f"[来源] {SRC_NAME} | 分类映射表: {'基础八股(BXXX)' if is_basic else 'Agent(QXXX)'}")

    # 沿用母库主流 type / status，保证格式统一
    type_common = Counter(x.get("type", "") for x in mi).most_common(1)[0][0]
    status_common = Counter(x.get("status", "") for x in mi).most_common(1)[0][0]
    print(f"[格式] 沿用母库 type={type_common!r} status={status_common!r}")

    mmap = {}
    for x in mi:
        k = norm(x.get("content") or x.get("norm"))
        if k:
            mmap.setdefault(k, x)

    matched, only_new = [], []
    for x in aq:
        k = norm(x.get("question"))
        (matched.append((mmap[k], x)) if k and k in mmap else only_new.append(x))

    print(f"[交叉验证] 重叠 {len(matched)} 条 / 本库独有的 {len(only_new)} 条")

    # ---- A. 重叠题：key_points 回填 tags（纯增量） ----
    tag_added = 0
    for mit, ait in matched:
        kps = [str(k).strip() for k in (ait.get("key_points") or []) if str(k).strip()]
        tags = list(mit.get("tags") or [])
        cat = ait.get("category", "")
        extra = ([cat] if cat else []) + kps
        before = len(tags)
        for t in extra:
            if t not in tags:
                tags.append(t)
        if len(tags) != before:
            mit["tags"] = tags
            tag_added += len(tags) - before
        srcs = list(mit.get("sources") or [])
        marker = f"cross-validated:{SRC_NAME}"
        if marker not in srcs:
            srcs.append(marker)
            mit["sources"] = srcs
    print(f"[A] 重叠题回填 key_points/分类 到 tags，共新增 {tag_added} 个标签（未覆盖原有内容）")

    # ---- B. 独有题：新增为母库 item ----
    nums = [int(x["id"][1:]) for x in mi if re.fullmatch(r"q\d+", x["id"])]
    next_id = max(nums) + 1
    print(f"[B] 新增 {len(only_new)} 题，编号自 q{next_id:04d} 起")

    today = time.strftime("%Y-%m-%d")
    new_items = []
    for x in only_new:
        qid = f"q{next_id:04d}"
        next_id += 1
        cat_raw = x.get("category", "")
        ans = str(x.get("reference_answer") or "").strip()
        kps = [str(k).strip() for k in (x.get("key_points") or []) if str(k).strip()]
        item = {
            "id": qid,
            "category": CAT_MAP.get(cat_raw, "概念基础"),
            "type": type_common,
            "content": str(x.get("question") or "").strip(),
            "source": SRC_NAME,
            "difficulty": "★★☆",
            "tags": ([cat_raw] if cat_raw else []) + kps,
            "status": status_common,
            "answer": {
                "简版": "、".join(kps) if kps else ans[:60],
                "展开": ans,
                "加分点": "",
                "雷区": "",
            },
            "sources": [f"imported-from:{SRC_NAME}", f"origin-id:{x.get('id','')}"],
            "norm": norm(x.get("question")),
            "created_at": today,
            "wiki_node_token": "",
            "wiki_url": "",
        }
        new_items.append((x.get("id"), qid, item))

    print(f"[plan] 总库 {len(mi)} -> {len(mi) + len(new_items)} 题")

    if not args.apply:
        print("[info] dry-run，未写库。确认后加 --apply")
        return

    bak = str(MOTHER) + ".bak_" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(MOTHER, bak)
    print(f"[backup] {bak}")

    mi.extend([it for _, _, it in new_items])
    m["items"] = mi
    m["meta"]["total"] = len(mi)
    m["meta"]["last_merged_source"] = {
        "merged_from": str(src_path),
        "bank_name": a.get("bank_name"),
        "version": a.get("version"),
        "src_total": len(aq),
        "overlap": len(matched),
        "newly_added": len(new_items),
        "date": today,
    }
    MOTHER.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[write] 已写回 {len(mi)} 题")
    print(f"\n[清单] 新增题目 (前 20 / 共 {len(new_items)}):")
    for old_id, new_id, it in new_items[:20]:
        print(f"   {old_id} -> {new_id} ({it['category']}) {it['content'][:50]}")
    if len(new_items) > 20:
        print(f"   ... 其余 {len(new_items) - 20} 条略")
    print(f"[done] 备份 {bak}")


if __name__ == "__main__":
    main()
