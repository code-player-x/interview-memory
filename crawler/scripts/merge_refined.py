#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨源合并去重：把各源 process_source 产出的 refined.jsonl 合并，做跨源 + 与题库的规则去重，
输出 data/tmp/all_platforms_refined.jsonl（唯一题，带来源标签）与报告。

用法：
  python merge_refined.py --sources juejin nowcoder
  python merge_refined.py --sources juejin nowcoder xiaohongshu zhihu maimai weixin
  # 追加语义去重：
  python merge_refined.py --sources juejin nowcoder --dedup rule+semantic
"""
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
BANK = BASE / "data" / "questions-bank.json"
OUT = BASE / "data" / "tmp" / "all_platforms_refined.jsonl"

sys.path.insert(0, str(HERE))
from dedup import resolve_spec, DedupRunner
from dedup.util import norm


def load_refined(source):
    p = BASE / "data" / "tmp" / source / "refined.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", nargs="+", required=True)
    ap.add_argument("--dedup", default="rule", help="rule | semantic | rule+semantic")
    ap.add_argument("--fuzzy", type=float, default=0.85)
    ap.add_argument("--threshold", type=float, default=0.9)
    ap.add_argument("--cache-only", action="store_true",
                    help="语义去重仅用本地 embedding 缓存，不联网 ollama（缺向量的题走规则去重）")
    args = ap.parse_args()

    recs = []
    per_src = {}
    for s in args.sources:
        items = load_refined(s)
        per_src[s] = len(items)
        for it in items:
            q = (it.get("question") or "").strip()
            if q:
                recs.append({"q": q, "category": it.get("category", "概念基础"),
                             "sources": [s], "src_count": it.get("src_count", 1)})
    print("各源 refined 题数: %s" % per_src)
    print("合并原始题数: %d" % len(recs))

    # 题库基线（避免重复入库已有题）
    bank = json.load(open(BANK, encoding="utf-8"))
    baseline = [norm((it.get("content") or it.get("question") or "").strip())
                for it in bank.get("items", []) if (it.get("content") or it.get("question") or "").strip()]

    strat = resolve_spec(args.dedup, fuzzy=args.fuzzy, threshold=args.threshold,
                         model="nomic-embed-text", cache_only=args.cache_only)
    runner = DedupRunner(strat, baseline=baseline)
    kept, dups = runner.process([(str(i), r["q"]) for i, r in enumerate(recs)])
    kept_ids = {k[0] for k in kept}

    # 汇总保留题（去重后），合并多源来源标签
    out = []
    seen_norm = {}
    for i, r in enumerate(recs):
        if str(i) not in kept_ids:
            continue
        n = norm(r["q"])
        if n in seen_norm:
            seen_norm[n]["sources"] = list(dict.fromkeys(seen_norm[n]["sources"] + r["sources"]))
            seen_norm[n]["src_count"] = max(seen_norm[n]["src_count"], r["src_count"])
            continue
        rec = {"question": r["q"], "category": r["category"],
               "sources": r["sources"], "src_count": r["src_count"]}
        seen_norm[n] = rec
        out.append(rec)
    # 排序：多源/高频优先
    out.sort(key=lambda r: (len(r["sources"]), r["src_count"]), reverse=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("跨源去重后唯一题数: %d（判重 %d）" % (len(out), len(dups)))
    print("已写 -> %s" % OUT)
    if dups:
        print("判重样例:")
        for d in dups[:10]:
            print("  [%.3f] %s ~ %s" % (d.get("score", 0), str(d.get("text", ""))[:36], str(d.get("matched", ""))[:36]))


if __name__ == "__main__":
    main()
