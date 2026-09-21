#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_category_results.py — 把分类上传结果 category_results.tsv
（category \t node_token \t url \t flag[new|existing]）合并回 data/wiki-config.json：
  - 总是写入 categories[cat]["summary_node_token"] / ["summary_url"]（分类汇总文档节点）
  - 若该分类是新建（flag=new），同时写入 categories[cat]["node_token"]（供后续重跑定位）
不修改 questions-bank.json（逐题 wiki_node_token 留作来源/历史标记，清理旧单题节点时单独处理）。
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(BASE, "data", "wiki-config.json")
RESULTS = os.path.join(BASE, "data", "tmp", "category_results.tsv")


def main():
    if not os.path.exists(RESULTS):
        print("没有 category_results.tsv，跳过")
        return
    with open(RESULTS, encoding="utf-8") as f:
        rows = [ln.rstrip("\n").split("\t") for ln in f if ln.strip()]

    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)

    n = 0
    for r in rows:
        if len(r) < 3:
            continue
        cat, node, url = r[0], r[1], r[2]
        flag = r[3] if len(r) > 3 else "existing"
        c = cfg["categories"].setdefault(cat, {})
        c["summary_node_token"] = node
        c["summary_url"] = url
        if flag == "new":
            c["node_token"] = node  # 新建的分类文档，记录其 node_token
        n += 1

    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"已回写 {n} 个分类的 summary_node_token / summary_url 到 wiki-config.json")


if __name__ == "__main__":
    sys.exit(main())
