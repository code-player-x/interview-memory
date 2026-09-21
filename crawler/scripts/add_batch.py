#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量入库工具：读 batch JSON（entries 列表）→ 与题库 0.85 去重 → 一次性追加。

用法：
    python scripts/add_batch.py data/tmp/batches/batch_01.json [--dry-run]

batch JSON 格式： [{"category":..,"content":..,"difficulty":..,"tags":[..],
                   "answer":{"简版":..,"展开":..,"加分点":..,"雷区":..}}, ...]
"""
import json
import sys
from pathlib import Path
from difflib import SequenceMatcher

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bank  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
BANK_PATH = BASE / "data" / "questions-bank.json"
THR = 0.85
SOURCE = "小红书/知乎/稀土掘金 AI Agent 面经 (WorkBuddy 爬取 2026-08)"
CREATED = "2026-08-01"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        print("usage: add_batch.py <batch.json> [--dry-run]")
        return 1
    batch_path = Path(args[0])
    if not batch_path.is_absolute():
        batch_path = BASE / batch_path
    entries = json.loads(batch_path.read_text(encoding="utf-8"))

    data = bank.load(BANK_PATH)
    items = data["items"]
    bank_norms = [it.get("norm") or bank.normalize(it.get("content", "")) for it in items]

    added, skipped = [], []
    max_id = 0
    for it in items:
        qid = it.get("id", "")
        if qid.startswith("q") and qid[1:].isdigit():
            max_id = max(max_id, int(qid[1:]))

    for e in entries:
        content = e["content"].strip()
        nq = bank.normalize(content)
        hit = None
        for i, bn in enumerate(bank_norms):
            if SequenceMatcher(None, nq, bn).ratio() >= THR:
                hit = items[i]["id"]
                break
        if hit:
            skipped.append((content[:46], hit))
            continue
        max_id += 1
        item = {
            "id": f"q{max_id:04d}",
            "category": e["category"],
            "type": e.get("type", "essay"),
            "content": content,
            "source": e.get("source", SOURCE),
            "difficulty": e.get("difficulty", "★★☆"),
            "tags": e.get("tags", []),
            "status": "新增",
            "answer": e["answer"],
            "leetcode_url": e.get("leetcode_url", ""),
            "sources": e.get("sources", []),
            "norm": nq,
            "created_at": e.get("created_at", CREATED),
            "wiki_node_token": "",
            "wiki_url": "",
        }
        items.append(item)
        bank_norms.append(nq)
        added.append(item)

    print(f"batch={batch_path.name}  输入 {len(entries)}  新增 {len(added)}  跳过重复 {len(skipped)}")
    for c, h in skipped:
        print(f"  [SKIP] {c} ~ {h}")
    if dry:
        print("(dry-run，未写入)")
        return 0

    data["meta"]["total"] = len(items)
    bank.save(data, BANK_PATH)
    print(f"已写入，题库 total = {len(items)}（{added[0]['id'] if added else '-'} ~ "
          f"{added[-1]['id'] if added else '-'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
