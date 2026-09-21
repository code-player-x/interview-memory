#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_results.py — 把上传结果 results.tsv（id \\t node_token \\t url）合并回
data/questions-bank.json，写入每道题的 wiki_node_token / wiki_url。
按 id 匹配，已存在的只更新，不重复。
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(BASE, "data", "questions-bank.json")
RESULTS = os.path.join(BASE, "data", "tmp", "results.tsv")


def main():
    if not os.path.exists(RESULTS):
        print("没有 results.tsv，跳过")
        return
    with open(RESULTS, encoding="utf-8") as f:
        rows = [ln.rstrip("\n").split("\t") for ln in f if ln.strip()]
    token_map = {r[0]: (r[1], r[2]) for r in rows if len(r) >= 3}

    with open(BANK, encoding="utf-8") as f:
        bank = json.load(f)
    n = 0
    for it in bank["items"]:
        if it["id"] in token_map:
            node, url = token_map[it["id"]]
            it["wiki_node_token"] = node
            it["wiki_url"] = url
            n += 1
    bank["meta"]["total"] = len(bank["items"])
    with open(BANK, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)
    print(f"已回写 {n} 道题的 wiki_node_token / wiki_url")


if __name__ == "__main__":
    sys.exit(main())
