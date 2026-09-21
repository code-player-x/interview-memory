#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_by_category.py — 把题库按「分类」聚合，一个类别一个文档。
对比 export_ima.py（按主题/来源拆 43 份），本脚本严格遵循：
  「不要一个题目一个文档，一个类别一个文档」。
输出：data/export/by-category/<分类>.md + index.md
"""
import json
import os
import re
import collections

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(BASE, "data", "questions-bank.json")
OUT = os.path.join(BASE, "data", "export", "by-category")
os.makedirs(OUT, exist_ok=True)

# 分类展示顺序（其余按出现顺序追加）
ORDER = [
    "后端八股", "后端八股（Go）", "工程落地", "架构设计",
    "概念基础", "项目深挖", "行为与HR", "手撕算法",
]


def _clean(s):
    s = (s or "").strip()
    return re.sub(r"^[-•·*]\s*", "", s)


def fmt_answer(a):
    parts = []
    if a.get("简版"):
        parts.append(f"**简版**：{_clean(a['简版'])}")
    if a.get("展开"):
        parts.append(f"**展开**：{_clean(a['展开'])}")
    if a.get("加分点"):
        items = [s.strip(" ；") for s in re.split(r"[；;]", a["加分点"]) if s.strip()]
        if items:
            parts.append("**加分点**：\n" + "\n".join(f"- {s}" for s in items))
    if a.get("雷区"):
        items = [s.strip(" ；") for s in re.split(r"[；;]", a["雷区"]) if s.strip()]
        if items:
            parts.append("**雷区**：\n" + "\n".join(f"- {s}" for s in items))
    return "\n\n".join(parts)


def safe(name):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")


def main():
    d = json.load(open(BANK, encoding="utf-8"))
    g = collections.defaultdict(list)
    for it in d["items"]:
        g[it["category"]].append(it)

    # 排序：ORDER 在前，其余按出现
    cats = [c for c in ORDER if c in g] + [c for c in g if c not in ORDER]

    index_rows = []
    total = 0
    for cat in cats:
        items = g[cat]
        total += len(items)
        fname = safe(cat) + ".md"
        lines = [f"# {cat}", "", f"> 共 {len(items)} 题", ""]
        for i, it in enumerate(items, 1):
            a = it.get("answer", {})
            lines.append(f"## Q{i}. {it['content']}")
            lines.append(
                f"**来源**：{it.get('source','')} ｜ **难度**：{it.get('difficulty','')} ｜ "
                f"**标签**：{', '.join(it.get('tags', []))}"
            )
            lines.append("")
            lines.append("### 参考答案")
            lines.append(fmt_answer(a))
            if it.get("sources"):
                lines.append("")
                lines.append("**原始链接**：" + "；".join(it["sources"]))
            lines.append("")
            lines.append("---")
            lines.append("")
        with open(os.path.join(OUT, fname), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        index_rows.append((cat, len(items), fname))

    idx = ["# 面试题库（按分类整理 · 一个类别一个文档）", "",
           f"> 共 {total} 题，{len(index_rows)} 个分类文档。", "",
           "## 分类清单"]
    for cat, n, fname in index_rows:
        idx.append(f"- [{cat}（{n} 题）]({fname})")
    with open(os.path.join(OUT, "index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(idx))

    print(f"已导出 {total} 题 -> {len(index_rows)} 个分类文档 + index.md")
    print(f"目录：{OUT}")
    for cat, n, fname in index_rows:
        print(f"  {cat}: {n}")


if __name__ == "__main__":
    main()
