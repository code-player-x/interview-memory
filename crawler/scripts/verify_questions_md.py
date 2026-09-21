#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""校验 questions/*.md：题数守恒、ID 不重不漏、原题面一字未改。"""
import json
import re
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
BANK = PROJ / "data" / "questions-bank.json"
OUT = PROJ / "questions"


def main():
    data = json.loads(BANK.read_text(encoding="utf-8"))
    items = data["items"]
    expect = {}
    for it in items:
        expect[it["id"]] = (it.get("content") or "").strip()

    found_ids = []
    file_counts = {}
    stem_map = {}

    for f in sorted(OUT.glob("*.md")):
        if f.name == "README.md":
            continue
        txt = f.read_text(encoding="utf-8")
        # 每道题以 "> 原题 ID：`qXXXX`" 标记
        ids = re.findall(r"> 原题 ID：`([^`]+)`", txt)
        heads = len(re.findall(r"^## \d+\. ", txt, flags=re.M))
        file_counts[f.name] = (len(ids), heads)
        found_ids.extend(ids)
        # 题干抽取：### 题干 之后到下一个 ###
        blocks = re.findall(r"### 题干\n\n(.*?)\n\n### 选项", txt, flags=re.S)
        for i, bid in enumerate(ids):
            if i < len(blocks):
                stem_map[bid] = blocks[i].strip()

    print(f"原始题库题数 : {len(items)}")
    print(f"Markdown 收录: {len(found_ids)}")
    print(f"唯一 ID      : {len(set(found_ids))}")

    dup = [i for i in set(found_ids) if found_ids.count(i) > 1]
    missing = [i for i in expect if i not in found_ids]
    extra = [i for i in found_ids if i not in expect]
    print(f"重复出现     : {len(dup)} {dup[:5]}")
    print(f"遗漏         : {len(missing)} {missing[:5]}")
    print(f"多余         : {len(extra)} {extra[:5]}")

    # 题干一致性（不改写题意）
    diff = []
    for qid, stem in stem_map.items():
        orig = expect.get(qid, "")
        a = re.sub(r"\s+", "", stem)
        b = re.sub(r"\s+", "", orig)
        if a != b and a.replace("（空）", "") != b:
            diff.append((qid, orig[:40], stem[:40]))
    print(f"\n题干被改写的题数: {len(diff)} (应=0)")
    for d in diff[:5]:
        print(f"   [{d[0]}] 原: {d[1]}")
        print(f"        现: {d[2]}")

    print("\n各文件题数（ID 计数 / 小节标题计数）:")
    tot = 0
    for k, (a, b) in sorted(file_counts.items(), key=lambda x: -x[1][0]):
        tot += a
        flag = "" if a == b else "  ⚠️不一致"
        print(f"   {k:<24} {a:>5} / {b:>5}{flag}")
    print(f"   {'合计':<24} {tot:>5}")

    print(f"\n[结论] 守恒: {'是' if tot == len(items) and not missing and not dup else '否'}")


if __name__ == "__main__":
    main()
