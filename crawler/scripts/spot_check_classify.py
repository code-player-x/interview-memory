#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抽查分类结果，识别误判（尤其 `\bgo\b` 这类宽松规则）。"""
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_questions import classify, blob  # noqa: E402

BANK = Path(__file__).resolve().parent.parent / "data" / "questions-bank.json"

data = json.loads(BANK.read_text(encoding="utf-8"))
items = data["items"]

random.seed(42)
groups = {}
for it in items:
    k, name, fn = classify(it)
    groups.setdefault(k, []).append(it)

# 1) Go 域里，有多少只靠 \bgo\b 命中（即不含 golang/goroutine/channel 等强信号）
g = groups.get("go", [])
strong = re.compile(r"golang|goroutine|channel|\bgmp\b|defer|切片|协程|sync\.|"
                    r"rwmutex|逃逸分析|gin\b|gorm|\bmap\s*并发|go\s*的|结构体")
weak_only = [it for it in g if not strong.search(blob(it))]
print(f"[go] 共 {len(g)} 题；其中缺少强信号、可能只靠 \\bgo\\b 命中的: {len(weak_only)}")
for it in weak_only[:10]:
    print(f"   [{it['id']}] {it.get('content','')[:70]}")

print()
for key in ("puzzle", "llm_basics", "evaluation", "algorithm"):
    v = groups.get(key, [])
    print(f"[{key}] 共 {len(v)} 题，抽样 6 条:")
    for it in random.sample(v, min(6, len(v))):
        print(f"   [{it['id']}] ({it.get('category')}) {it.get('content','')[:68]}")
    print()
