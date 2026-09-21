#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""题目频率统计：读 all_platforms_refined.jsonl（跨源去重后的唯一题），产出
频率统计报告（Markdown + 终端摘要）。

统计维度：
  1. 总体唯一题数
  2. 跨平台共现直方图：每道题出现在几个平台（len(sources)=1/2/3/4）
  3. 分类分布（7 大类）
  4. 各源贡献的唯一题数
  5. 高频热点题 TopN（跨平台越多越热）
  6. 同平台内高频（src_count，单源被多次提及）

用法：
  python frequency_report.py
  python frequency_report.py --top 30
"""
import argparse, json, sys
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
IN = BASE / "data" / "tmp" / "all_platforms_refined.jsonl"
OUT = BASE / "data" / "tmp" / "frequency_report.md"


def load():
    if not IN.exists():
        return []
    return [json.loads(l) for l in open(IN, encoding="utf-8") if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--infile", default=str(IN))
    ap.add_argument("--outfile", default=str(OUT))
    args = ap.parse_args()

    recs = [json.loads(l) for l in open(args.infile, encoding="utf-8") if l.strip()] if args.infile else load()
    if not recs:
        print("无数据：%s" % args.infile)
        return

    total = len(recs)
    # 跨平台共现
    co = Counter(len(r.get("sources", [])) for r in recs)
    # 分类
    cat = Counter(r.get("category", "概念基础") for r in recs)
    # 各源贡献（唯一题归属到的源）
    src = Counter()
    for r in recs:
        for s in r.get("sources", []):
            src[s] += 1
    # 单源内高频
    inner = Counter(r.get("src_count", 1) for r in recs)

    # 高频热点题（按平台数降序，再按单源频次）
    hot = sorted(recs, key=lambda r: (len(r.get("sources", [])), r.get("src_count", 1)), reverse=True)

    lines = []
    lines.append("# 面经题目频率统计报告\n")
    lines.append("- 统计对象：`all_platforms_refined.jsonl`（跨源去重后唯一题）")
    lines.append("- 唯一题总数：**%d**\n" % total)

    lines.append("## 1. 跨平台共现（每道题出现在几个平台）\n")
    lines.append("| 出现平台数 | 题数 | 占比 |")
    lines.append("|---|---|---|")
    for n in sorted(co):
        lines.append("| %d | %d | %.1f%% |" % (n, co[n], 100.0 * co[n] / total))
    lines.append("")

    lines.append("## 2. 分类分布\n")
    lines.append("| 分类 | 题数 | 占比 |")
    lines.append("|---|---|---|")
    for c, n in cat.most_common():
        lines.append("| %s | %d | %.1f%% |" % (c, n, 100.0 * n / total))
    lines.append("")

    lines.append("## 3. 各平台贡献的唯一题数\n")
    lines.append("| 平台 | 唯一题数 |")
    lines.append("|---|---|")
    for s, n in src.most_common():
        lines.append("| %s | %d |" % (s, n))
    lines.append("")

    lines.append("## 4. 单源内被多次提及的分布（src_count）\n")
    lines.append("| 单源提及次数 | 题数 |")
    lines.append("|---|---|")
    for k in sorted(inner):
        lines.append("| %d | %d |" % (k, inner[k]))
    lines.append("")

    lines.append("## 5. 高频热点题 Top %d（跨平台优先）\n" % args.top)
    lines.append("| # | 平台数 | 单源频次 | 分类 | 题目（前 60 字） | 来源 |")
    lines.append("|---|---|---|---|---|---|")
    for i, r in enumerate(hot[:args.top], 1):
        q = (r.get("question") or "").strip().replace("|", "/")[:60]
        lines.append("| %d | %d | %d | %s | %s | %s |" % (
            i, len(r.get("sources", [])), r.get("src_count", 1),
            r.get("category", ""), q, ",".join(r.get("sources", []))))
    lines.append("")

    md = "\n".join(lines)
    Path(args.outfile).write_text(md, encoding="utf-8")

    # 终端摘要
    print("唯一题总数: %d" % total)
    print("跨平台共现: %s" % dict(sorted(co.items())))
    print("分类: %s" % dict(cat.most_common()))
    print("各源贡献: %s" % dict(src.most_common()))
    print("已写报告 -> %s" % args.outfile)


if __name__ == "__main__":
    main()
