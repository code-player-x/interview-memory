#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""总库全量语义去重（阈值 0.88，并查集连通分量版）。

适用对象：data/questions-bank.json（母库，现已并入 Claw Agent 题库，即「总库」）。

关键修正（相对初版）：
  1. 旧缓存存在 197 组/510 个 key 的「相同向量」损坏（不同题映射到同一向量），
     导致海量假合并。本版默认 --fresh 全量用 Ollama /api/embed 重新嵌入，
     抛弃损坏缓存（已备份为 .corrupted_bak）。已验证嵌入确定性：
     同文本重嵌余弦=1.0000。
  2. 聚类早期曾用「非传递最优近邻」（每题只挂到最完整的那个邻居），实测会漏检
     「双向互达但各自挂到更完整邻居」的桥对（某一轮漏了 11 对），已废弃。
     现改用 **并查集连通分量**：合并所有【直接余弦 >= thr】的边，
     同一连通分量内保留 comp_score（已补答案优先 + 答案长度）最高者。
     bge-m3 区分度高，不相关题之间不会连边，不存在连锁误并风险。
  ⚠️ 前提：仅当嵌入模型对短中文有区分度时并查集才安全。
     换模型前务必先跑 scripts/test_embed_discriminative.py 验证
     （nomic-embed-text 对中文短题面坍缩，禁用）。

流程：
  A. 全量重嵌（content 文本）-> 向量矩阵 M (N x D)，L2 归一化。
  B. 一致性校验：抽样重嵌与首次重嵌比对（应=1.0）。
  C. S = M@M.T 余弦矩阵；取上三角中 S>=thr 的边。
  D. 并查集合并 -> 连通分量；每组保留 comp_score 最高者，合并 sources。
  E. 生成 plan.json（不写库）；--apply 才写回（备份+一次性 save+更新 meta.total）。
     结果可幂等：复跑删除数应为 0。
"""
import json
import pickle
import hashlib
import math
import os
import sys
import time
import shutil
import urllib.request
import argparse
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(HERE, "..", "data", "questions-bank.json")
PLAN = os.path.join(HERE, "..", "data", "tmp", "dedup_088_plan.json")
THRESH = 0.88
MODEL = "bge-m3"  # 默认用对中文短文本有区分度的多语言嵌入模型
EMBED_URL = "http://localhost:11434/api/embed"
CACHE = os.path.join(HERE, "..", "data", "tmp", f".semantic_embed_cache_{MODEL}.pkl")


def h(s):
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:16]


def load_cache():
    try:
        return pickle.load(open(CACHE, "rb"))
    except Exception:
        return {}


def save_cache(c):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    pickle.dump(c, open(CACHE, "wb"))


def embed_batch(texts):
    payload = json.dumps({"model": MODEL, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        EMBED_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    embs = data.get("embeddings")
    if not embs or len(embs) != len(texts):
        raise RuntimeError(f"embed 返回异常: 期望 {len(texts)} 条, 实得 {len(embs) if embs else 0}")
    return embs


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) or 1.0))


def answer_score(it):
    """答案完整度评分：按**实际内容**打分，不以 status 标签为准。

    ⚠️ 历史坑（2026-09-19，勿恢复）：
      曾写成 base = 1000 if status == "已补答案"，把 status 当作"答案已补全"的代理指标。
      实测反例：q0012 status='新增' 但四段俱全共 351 字（含加分点/雷区）；
               而新导入题带着 status='已补答案' 却只有 209 字且缺两段。
      结果保留了劣答案、删掉了优答案，净丢 700+ 字内容。
      **status 与答案质量无可靠对应关系**，只能按实际内容打分。

    评分公式：答案总字数 + 非空段落数×20（段数作为次级信号，鼓励结构完整）。
    """
    a = it.get("answer") or {}
    if isinstance(a, dict):
        secs = ("简版", "展开", "加分点", "雷区", "评分要点")
        vals = [(str(a.get(k, "") or "")).strip() for k in secs]
        txt_len = sum(len(v) for v in vals)
        nonempty = sum(1 for v in vals if v)
    else:
        txt_len = len(str(a))
        nonempty = 1
    return txt_len + 20 * nonempty


def main():
    global MODEL
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写回母库")
    ap.add_argument("--fresh", action="store_true", help="忽略旧缓存全量重嵌")
    ap.add_argument("--thresh", type=float, default=THRESH, help="相似度阈值")
    ap.add_argument("--model", default=MODEL, help="Ollama 嵌入模型名")
    args = ap.parse_args()
    thr = args.thresh
    MODEL = args.model

    t0 = time.time()
    d = json.load(open(BANK, encoding="utf-8"))
    items = d["items"]
    N = len(items)
    print(f"[load] 母库题量={N}")

    cache = {} if args.fresh else load_cache()
    print(f"[cache] 使用{'全新重嵌' if args.fresh else f'缓存({len(cache)}条)'}")
    # 全量重嵌（始终用 content 文本；即使有缓存也重嵌以保证无损坏）
    texts = [it.get("content", "") or it.get("norm", "") for it in items]
    vecs = []
    B = 32
    t1 = time.time()
    for s in range(0, N, B):
        chunk = texts[s : s + B]
        eb = embed_batch(chunk)
        for v in eb:
            vecs.append(np.asarray(v, dtype=np.float64))
        if (s + B) % 256 == 0 or s + B >= N:
            print(f"  embed {min(s+B,N)}/{N}")
    print(f"[embed] 全量重嵌 {N} 条, 用时 {time.time()-t1:.1f}s")
    # 写回干净缓存（content+norm 双 key）
    new_cache = {}
    for it, v in zip(items, vecs):
        new_cache[h(it.get("content", ""))] = v.tolist()
        nk = h(it.get("norm", ""))
        if nk:
            new_cache[nk] = v.tolist()
    save_cache(new_cache)
    print(f"[cache] 干净缓存已写 {len(new_cache)} 条")

    # B. 一致性校验：再嵌一次抽样比对
    rng = np.random.default_rng(7)
    samp = rng.choice(N, size=min(40, N), replace=False).tolist()
    samp_texts = [texts[i] for i in samp]
    fresh2 = embed_batch(samp_texts)
    cos = [cosine(np.asarray(f, dtype=np.float64), vecs[i]) for f, i in zip(fresh2, samp)]
    min_c, mean_c = min(cos), float(np.mean(cos))
    print(f"[consistency] 重嵌抽样 {len(samp)} 条 余弦 min={min_c:.4f} mean={mean_c:.4f}")
    if min_c < 0.999:
        print("!! 一致性不达标，终止。")
        sys.exit(2)

    # C. 归一化 + 余弦矩阵
    M = np.stack([v / (np.linalg.norm(v) or 1.0) for v in vecs])  # N x 768
    S = M @ M.T
    comp = np.array([answer_score(it) for it in items], dtype=np.float64)

    # D. 并查集连通分量（bge-m3 区分度高，不相关题间无 >=thr 边，不会连锁误并）
    # 合并所有直接 >=thr 的边；每组保留 comp_score 最高者。
    parent = list(range(N))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    iu, ju = np.triu_indices(N, 1)
    mask = S[iu, ju] >= thr
    pairs = list(zip(iu[mask].tolist(), ju[mask].tolist()))
    for a, b in pairs:
        union(a, b)
    comp_map = {}
    for i in range(N):
        r = find(i)
        comp_map.setdefault(r, []).append(i)
    # ⚠️ 关键：并查集只用来「分组」，真正合并前必须再看一次【直接】相似度。
    # 纯并查集会把 A~B、B~C 的边并成一组，让 A 被合并进 C，
    # 即便 A 与 C 直接余弦远低于阈值（实测最低 0.767）——即"被搭桥的传递合并"，
    # 违反阈值语义。2026-09-19 并入基础八股文 126 题时就出现了 5 组。
    # 做法：组内按 comp_score 从高到低，每轮取当前最优为代表，
    #       只把【与该代表直接 >=thr】的成员并入；未达阈值的留到下一轮自成代表。
    assign = np.arange(N)
    bridged_kept_apart = 0
    for members in comp_map.values():
        if len(members) <= 1:
            continue
        remaining = sorted(members, key=lambda i: -comp[i])
        while len(remaining) > 1:
            rep = remaining[0]          # 本轮代表：组内 comp_score 最高
            rest = []
            for i in remaining[1:]:
                if S[i, rep] >= thr:    # 只有与代表【直接】达标才并入
                    assign[i] = rep
                else:                   # 未达标 -> 留到下一轮，可能自成代表
                    rest.append(i)
                    bridged_kept_apart += 1
            remaining = rest            # rep 已出列，循环必然收敛
    if bridged_kept_apart:
        print(f"[cluster] 其中 {bridged_kept_apart} 条因与代表直接相似度 <{thr} "
              f"而保持独立（避免传递桥接误并）")
    # 统计
    kept_set = set(assign.tolist())
    removed = []
    for i in range(N):
        if assign[i] != i:
            removed.append(
                {
                    "id": items[i]["id"],
                    "kept_id": items[assign[i]]["id"],
                    "max_cos": round(float(S[i, assign[i]]), 4),
                    "kept_answer_status": items[assign[i]].get("status"),
                    "removed_answer_status": items[i].get("status"),
                }
            )
    kept_ids = [items[i]["id"] for i in kept_set]
    print(f"[cluster] 并查集连通分量: 保留={len(kept_set)}, 删除={len(removed)}")

    plan = {
        "threshold": thr,
        "total_before": N,
        "total_after": len(kept_ids),
        "removed_count": len(removed),
        "consistency": {"min": min_c, "mean": mean_c, "sample": len(samp)},
        "kept_ids": kept_ids,
        "removed": removed,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "method": "fresh-reembed + union-find connected components (>=%.2f)" % thr,
    }
    json.dump(plan, open(PLAN, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[plan] {N} -> {len(kept_ids)} (删 {len(removed)})")
    print(f"[plan] 已写 {PLAN}")

    if args.apply:
        apply_plan(d, items, plan)
    else:
        print("[info] 未加 --apply，母库未改动。")


def apply_plan(d, items, plan):
    bak = BANK + ".bak_" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(BANK, bak)
    print(f"[backup] {bak}")
    kept_set = set(plan["kept_ids"])
    id2item = {it["id"]: it for it in items}
    by_kept = {}
    for r in plan["removed"]:
        by_kept.setdefault(r["kept_id"], []).append(r["id"])
    new_items = []
    for it in items:
        if it["id"] in kept_set:
            extra = by_kept.get(it["id"], [])
            merged = list(it.get("sources") or [])
            for oid in extra:
                o = id2item.get(oid)
                if o:
                    for s in (o.get("sources") or []):
                        if isinstance(s, str) and s not in merged:
                            merged.append(s)
            if extra:
                it["sources"] = merged
                it["_merged_from"] = extra
            new_items.append(it)
    d["items"] = new_items
    d["meta"] = d.get("meta", {})
    d["meta"]["total"] = len(new_items)
    d["meta"]["last_dedup"] = {
        "threshold": plan["threshold"],
        "method": plan.get("method"),
        "before": plan["total_before"],
        "after": plan["total_after"],
        "at": plan["generated_at"],
    }
    json.dump(d, open(BANK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[apply] 写回完成: {len(new_items)} 题 (原 {plan['total_before']})")


if __name__ == "__main__":
    main()
