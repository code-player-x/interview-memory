#!/usr/bin/env python3
"""
apply_fine_results.py — 把细分类上传结果回写到 wiki-config.json

读 data/tmp/fine_category_results.tsv (category \t node_token \t url \t flag[new|existing])
更新 data/wiki-config.json 的 fine_categories 段。
"""

import json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_PATH = os.path.join(BASE, "data", "tmp", "fine_category_results.tsv")
CONFIG_PATH = os.path.join(BASE, "data", "wiki-config.json")


def main():
    with open(RESULTS_PATH, encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        print("无上传结果，跳过。")
        return

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    if "fine_categories" not in config:
        config["fine_categories"] = {}

    updated = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        cat, node_token, url, flag = parts[0], parts[1], parts[2], parts[3]

        config["fine_categories"][cat] = {
            "node_token": node_token,
            "url": url,
            "flag": flag,
        }
        updated += 1
        print(f"  {cat} -> {node_token} ({flag})")

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"\nwiki-config.json 已更新: {updated} 个细分类")


if __name__ == "__main__":
    main()
