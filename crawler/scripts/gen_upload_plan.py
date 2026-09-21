#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_upload_plan.py（按分类版 · 直接改写分类文档）— 为 upload_feishu.sh 生成
「一个类别一个文档」的上传计划。

策略：每个面试题分类 = 飞书里 1 个文档节点。直接把该分类文档的正文 overwrite 为
该分类全部题目的汇总（不再在其下建一堆单题子文档）。
  - 已有分类（wiki-config 里有 node_token）：直接用 docs +update overwrite 改写该文档。
  - 缺父节点的分类（如「后端八股」）：标记 needs_create，upload 时先在 root 下建文档再改写。

输出：
  1) data/tmp/cat_<分类>.xml —— 该分类汇总文档正文（飞书 block XML，含 <title>）
  2) data/tmp/category_plan.tsv —— 计划：
     category \t doc_token \t title \t xmlpath \t needs_create(0/1)
     - doc_token 为空且 needs_create=1 → 需先 wiki +node-create 建文档
真正的 lark-cli 调用由 upload_feishu.sh 执行。

用法：
  python scripts/gen_upload_plan.py                # 全部面试题分类
  python scripts/gen_upload_plan.py --only 手撕算法    # 单分类（验证链路）
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(BASE, "data", "questions-bank.json")
CONFIG = os.path.join(BASE, "data", "wiki-config.json")
TMP = os.path.join(BASE, "data", "tmp")
os.makedirs(TMP, exist_ok=True)

# 「每日推送归档」是每日邮件历史，不是面试题分类，不建汇总文档
EXCLUDE_CATS = {"每日推送归档"}


def sanitize(name: str) -> str:
    return re.sub(r'[:*?"<>|/\\]', "_", name)


def esc(t: str) -> str:
    if t is None:
        return ""
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_category_xml(cat: str, items: list) -> str:
    p = []
    p.append(f'<title>{esc(cat)}（共 {len(items)} 题）</title>')
    p.append(f"<h1>{esc(cat)} 面试题汇总（共 {len(items)} 题）</h1>")
    p.append(
        "<blockquote>本文件由 Agent 面经收割机自动汇总，按分类归档。"
        "每题含「简版 / 展开 / 加分点 / 雷区」四段式答案。</blockquote>"
    )
    p.append("<hr/>")
    for idx, it in enumerate(items, 1):
        a = it.get("answer", {}) or {}
        p.append(f'<h2>Q{idx}. {esc(it["content"])}</h2>')
        meta = (
            f'<b>来源</b>：{esc(it.get("source", ""))} ｜ '
            f'<b>难度</b>：{esc(it.get("difficulty", ""))} ｜ '
            f'<b>标签</b>：{esc("，".join(it.get("tags", [])))}'
        )
        p.append(f"<p>{meta}</p>")
        if a.get("简版"):
            p.append("<h3>简版</h3>")
            p.append(f'<p>{esc(a["简版"])}</p>')
        if a.get("展开"):
            p.append("<h3>展开</h3>")
            p.append(f'<p>{esc(a["展开"])}</p>')
        if a.get("加分点"):
            p.append("<h3>加分点</h3><ul>")
            for s in a["加分点"].split("；"):
                if s.strip():
                    p.append(f"<li>{esc(s.strip())}</li>")
            p.append("</ul>")
        if a.get("雷区"):
            p.append("<h3>雷区 / 易错</h3><ul>")
            for s in a["雷区"].split("；"):
                if s.strip():
                    p.append(f"<li>{esc(s.strip())}</li>")
            p.append("</ul>")
        urls = it.get("sources", []) or []
        if urls:
            p.append("<h3>来源</h3><ul>")
            for u in urls:
                p.append(f'<li><a href="{esc(u)}">{esc(u)}</a></li>')
            p.append("</ul>")
        if it.get("leetcode_url"):
            u = it["leetcode_url"]
            p.append(f'<p><b>力扣</b>：<a href="{esc(u)}">{esc(u)}</a></p>')
        p.append("<hr/>")
    return "\n".join(p)


def main():
    only = None
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--only" and i + 1 < len(args):
            only = args[i + 1]

    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cats = cfg["categories"]
    root = cfg.get("root_parent_node_token", "")

    with open(BANK, encoding="utf-8") as f:
        bank = json.load(f)

    grouped = {}
    for it in bank["items"]:
        c = it["category"]
        if c in EXCLUDE_CATS:
            continue
        if only and c != only:
            continue
        grouped.setdefault(c, []).append(it)

    plan_path = os.path.join(TMP, "category_plan.tsv")
    n = 0
    with open(plan_path, "w", encoding="utf-8") as pf:
        for cat, items in grouped.items():
            existing = cats.get(cat, {}).get("node_token", "")
            doc_token = existing if existing else "NEW"
            needs_create = "1" if not existing else "0"
            xml = build_category_xml(cat, items)
            xmlpath = os.path.join(TMP, f"cat_{sanitize(cat)}.xml")
            with open(xmlpath, "w", encoding="utf-8") as xf:
                xf.write(xml)
            title = f"{cat}（共 {len(items)} 题）"
            pf.write("\t".join([cat, doc_token, title, xmlpath, needs_create]) + "\n")
            n += 1
            print(
                f"  [分类] {cat}: {len(items)} 题 | XML {len(xml)} 字符 | "
                f"{'需新建文档' if needs_create == '1' else '改写现有文档 ' + doc_token}"
            )
    print(f"已生成 {n} 个分类上传计划 -> {plan_path}  (root_parent={root})")


if __name__ == "__main__":
    main()
