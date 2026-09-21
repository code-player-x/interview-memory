#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""只读：查看新增 8 题在总库中的最近邻居相似度，判断 0.88 阈值是否漏merge（read-only）。"""
import json
import os
import pickle
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
BANK = PROJ / "data" / "questions-bank.json"
CACHE = PROJ / "data" / "tmp" / ".semantic_embed_cache_bge-m3.pkl"
MODEL = "bge-m3"
EMBED_URL = "http://localhost:11434/api/embed"
NEW_IDS = [f"q{n:04d}" for n in range(4007, 4015)]

_cache = {}
if CACHE.exists():
    with open(CACHE, "rb") as f:
        _cache = pickle.load(f)


def embed_texts(texts):
    todo = [t for t in texts if t not in _cache]
    for i in range(0, len(todo), 32):
        batch = todo[i:i + 32]
        req = urllib.request.Request(
            EMBED_URL,
            data=json.dumps({"model": MODEL, "input": batch}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read().decode())
        for t, v in zip(batch, d["embeddings"]):
            _cache[t] = np.array(v, dtype=np.float32)
    return [np.asarray(_cache[t], dtype=np.float32) for t in texts]


def main():
    data = json.loads(BANK.read_text(encoding="utf-8"))
    items = data["items"]
    by_id = {x["id"]: x for x in items}
    texts = [(x.get("content") or "").strip() for x in items]
    vecs = embed_texts(texts)
    M = np.stack([v / (np.linalg.norm(v) or 1.0) for v in vecs])

    print(f"总库 {len(items)} 题 | 阈值 0.88\n")
    print("新增 8 题的最近邻居（排除自身）：")
    print("-" * 96)
    flag = 0
    for nid in NEW_IDS:
        if nid not in by_id:
            print(f"{nid}: 不在库中")
            continue
        i = items.index(by_id[nid])
        sim = M @ M[i]
        sim[i] = -1
        order = np.argsort(-sim)[:3]
        top = [(items[j]["id"], float(sim[j]), (items[j].get("content") or "")[:46]) for j in order]
        mark = "⚠️≥0.88" if top[0][1] >= 0.88 else ("🟡0.80-0.88" if top[0][1] >= 0.80 else "✅<0.80")
        if top[0][1] >= 0.80:
            flag += 1
        print(f"[{nid}] {mark}  {by_id[nid].get('content','')[:52]}")
        for tid, s, t in top:
            print(f"        -> {tid}  cos={s:.4f}  {t}")
        print()
    print(f"小结：8 道新题中，有 {flag} 道的最近邻居相似度 ≥0.80")


if __name__ == "__main__":
    main()
