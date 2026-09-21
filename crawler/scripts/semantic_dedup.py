#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立去重 CLI —— 把去重能力从 convert/import 流程里彻底解耦，可单独使用。

去重策略本身是插件（rule / semantic / none / all / rule+semantic），本 CLI 只是
它的一个「独立入口」，不依赖任何采集/导入逻辑。

示例：
  # 仅用语义去重（默认后端 ollama，需本地 Ollama + nomic-embed-text）
  python scripts/semantic_dedup.py data/tmp/interview_memory_import.json --dedup semantic

  # 规则 + 语义组合（并集）
  python scripts/semantic_dedup.py my_qs.json --dedup rule+semantic --threshold 0.9

  # 与已有库交叉去重（--baseline 指向练习系统导出的题面 JSON）
  python scripts/semantic_dedup.py new.json --dedup semantic --baseline existing.json

  # 输出清洗后的题列表 / 报告
  python scripts/semantic_dedup.py new.json --dedup rule --emit kept --out clean.json
  python scripts/semantic_dedup.py new.json --dedup semantic --report report.json

输入格式：{"questions":[{...}]} 或 [{"question":...}] 或 [{"content":...}] 或 [str]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dedup import resolve_spec, DedupRunner
from dedup.util import extract_text, record_id


def load_records(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    items = d if isinstance(d, list) else d.get("questions", [d])
    recs = []
    for i, it in enumerate(items):
        text = extract_text(it)
        if text:
            recs.append((record_id(it, i), text, it))
    return recs, items


def main():
    ap = argparse.ArgumentParser(description="独立去重 CLI（可插拔策略）")
    ap.add_argument("input", help="待去重题 JSON")
    ap.add_argument("--dedup", default="semantic",
                    help="策略: rule | semantic | none | all | rule+semantic")
    ap.add_argument("--backend", default="ollama", help="ollama | st（仅 semantic 用）")
    ap.add_argument("--model", default="nomic-embed-text")
    ap.add_argument("--threshold", type=float, default=0.9, help="语义相似度阈值")
    ap.add_argument("--fuzzy", type=float, default=0.85, help="规则模糊阈值")
    ap.add_argument("--baseline", default="", help="可选：已有题面 JSON，与其交叉去重")
    ap.add_argument("--report", default="", help="写去重报告 JSON 的路径")
    ap.add_argument("--emit", default="", choices=["", "kept", "all", "dups"],
                    help="输出清洗后题列表: kept(去重后) / dups(被判重的) / all")
    ap.add_argument("--out", default="", help="--emit 输出文件路径（不给则打印到终端）")
    ap.add_argument("--no-cache", action="store_true", help="禁用 embedding 缓存")
    args = ap.parse_args()

    recs, items = load_records(args.input)
    baseline = []
    if args.baseline:
        bitems = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        blist = bitems if isinstance(bitems, list) else bitems.get("questions", [])
        baseline = [t for t in (extract_text(b) for b in blist) if t]
        print(f"交叉基线题数: {len(baseline)}")

    strat = resolve_spec(args.dedup, backend_name=args.backend, model=args.model,
                         threshold=args.threshold, fuzzy=args.fuzzy,
                         use_cache=not args.no_cache)

    # 语义后端可用性探测：不可用则优雅退出（绝不静默产错结果）
    if args.dedup not in ("rule", "none"):
        try:
            ok = strat.available()
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"[warn] 后端探测异常: {e}", file=sys.stderr)
        if not ok:
            sys.exit(
                "[X] 语义去重后端不可用。请确认：\n"
                "    (1) Ollama 已启动且已拉取模型: ollama pull nomic-embed-text\n"
                "    (2) 或改用本地模型: --backend st（需 pip install sentence-transformers）\n"
                "    (3) 或暂用纯规则去重: --dedup rule")

    runner = DedupRunner(strat, baseline=baseline)
    kept, dups = runner.process([(r[0], r[1]) for r in recs])
    print(f"输入 {len(recs)} 题 | 保留 {len(kept)} | 判重 {len(dups)}")
    if dups:
        print("重复样例(新题 -> 命中已有):")
        for d in dups[:15]:
            print(f"  [{d['score']:.3f}] {d['text'][:40]}  ~  {str(d['matched'])[:40]}")

    if args.report:
        rep = {
            "stats": {"input": len(recs), "kept": len(kept), "duplicates": len(dups)},
            "kept_ids": [k[0] for k in kept],
            "duplicates": dups,
        }
        Path(args.report).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写 -> {args.report}")

    if args.emit:
        kept_ids = {k[0] for k in kept}
        dup_ids = {d["id"] for d in dups}
        if args.emit == "kept":
            out = [r[2] for r in recs if r[0] in kept_ids]
        elif args.emit == "dups":
            out = [r[2] for r in recs if r[0] in dup_ids]
        else:
            out = items
        txt = json.dumps(out, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(txt, encoding="utf-8")
            print(f"已写 -> {args.out}")
        else:
            print(txt)


if __name__ == "__main__":
    main()
