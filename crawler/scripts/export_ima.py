#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_ima.py — 把题库按「主题」聚合导出为 Markdown，供导入 ima 知识库。
分组逻辑：
  - 飞书来源：按来源文档名（去掉「飞书知识库·」前缀）聚合
  - 其他来源：按 分类 + 平台（牛客/小红书/掘金/微信-面经哥/其他）聚合
输出：data/export/ima/<主题>.md + index.md
注意：ima 无程序化写 API，本脚本只生成可一键导入的文件。
"""
import json
import os
import collections
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(BASE, "data", "questions-bank.json")
OUT = os.path.join(BASE, "data", "export", "ima")
os.makedirs(OUT, exist_ok=True)


def topic_of(it):
    src = it.get("source", "") or ""
    cat = it["category"]
    if src.startswith("飞书知识库·"):
        return (cat, src[len("飞书知识库·"):])
    if "牛客" in src:
        plat = "牛客面经"
    elif "小红书" in src:
        plat = "小红书面经"
    elif "掘金" in src:
        plat = "掘金面经"
    elif "微信" in src or "面经哥" in src:
        plat = "微信-面经哥"
    else:
        plat = "其他来源"
    return (cat, plat)


def safe(name):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")


def _clean(s):
    s = (s or "").strip()
    # 去掉原答案字段自带的项目符号，避免「简版：- xxx」这类怪异格式
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


def main():
    d = json.load(open(BANK, encoding="utf-8"))
    g = collections.defaultdict(list)
    for it in d["items"]:
        g[topic_of(it)].append(it)

    index_rows = []
    total = 0
    for (cat, name) in sorted(g.keys()):
        items = g[(cat, name)]
        total += len(items)
        fname = safe(f"{cat}__{name}") + ".md"
        lines = [f"# {cat} · {name}", "", f"> 共 {len(items)} 题", ""]
        for i, it in enumerate(items, 1):
            a = it.get("answer", {})
            lines.append(f"## Q{i}. {it['content']}")
            meta = f"**来源**：{it.get('source','')} ｜ **难度**：{it.get('difficulty','')} ｜ **标签**：{', '.join(it.get('tags', []))}"
            lines.append(meta)
            lines.append("")
            lines.append("### 参考答案")
            lines.append(fmt_answer(a))
            if it.get("sources"):
                lines.append("")
                lines.append("**原始链接**：" + "；".join(it["sources"]))
            lines.append("")
            lines.append("---")
            lines.append("")
        path = os.path.join(OUT, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        index_rows.append((cat, name, len(items), fname))

    # index.md
    idx = ["# 面试题库（ima 导入索引）", "",
           f"> 共 {total} 题，{len(index_rows)} 个主题文件。在 ima 知识库中选择本目录下所有 .md 一键导入即可。", ""]
    by_cat = collections.defaultdict(list)
    for cat, name, n, fname in index_rows:
        by_cat[cat].append((name, n, fname))
    for cat in sorted(by_cat):
        idx.append(f"## {cat}")
        for name, n, fname in by_cat[cat]:
            idx.append(f"- [{name}（{n} 题）]({fname})")
        idx.append("")
    with open(os.path.join(OUT, "index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(idx))

    print(f"已导出 {total} 题 -> {len(index_rows)} 个主题文件 + index.md")
    print(f"目录：{OUT}")


if __name__ == "__main__":
    main()
