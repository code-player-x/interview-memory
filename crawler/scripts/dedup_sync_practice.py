#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""练习库 interview_memory.db 同口径去重 + 从母库同步（bge-m3, 阈值 0.88）。

两阶段：
  A. 练习库内部去重：1578 题用 bge-m3 嵌入，并查集连通分量(>=0.88)，每组保留
     进度最多(复习/提交/错题)或答案最完整者；被删题的进度外键重定向到保留题。
  B. 与母库(3820)交叉同步：每道练习保留题找母库最佳匹配(norm 精确 或 余弦>=0.88)。
     - 命中：复用该练习题 id（进度外键不变），用母库答案/分类/tags 富化该行。
     - 一道母库题命中多道练习题：选进度最多者为 rep，其余进度重定向到 rep 后删除。
     - 练习独有(无母库匹配)：保留。
     - 母库独有(无练习匹配)：插入新行（新 id）。
结果：练习库 = 母库清洁集 + 练习自定义题，学习进度完整保留。

用法：python dedup_sync_practice.py [--apply]  （默认仅出方案，不动库）
"""
import json
import pickle
import hashlib
import os
import re
import sys
import time
import shutil
import sqlite3
import urllib.request
import argparse
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
BANK = os.path.join(PROJ, "data", "questions-bank.json")
DB = os.path.join(PROJ, "parent", "data", "interview_memory.db") if False else os.path.join(
    os.path.dirname(PROJ), "data", "interview_memory.db"
)
CACHE = os.path.join(PROJ, "data", "tmp", ".semantic_embed_cache_bge-m3.pkl")
THRESH = 0.88
MODEL = "bge-m3"
EMBED_URL = "http://localhost:11434/api/embed"


def h(s):
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:16]


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^\w\u4e00-\u9fff]", "", s)
    return s


def embed_batch(texts):
    payload = json.dumps({"model": MODEL, "input": texts}).encode("utf-8")
    req = urllib.request.Request(EMBED_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    embs = data.get("embeddings")
    if not embs or len(embs) != len(texts):
        raise RuntimeError(f"embed 返回异常: 期望 {len(texts)} 实得 {len(embs) if embs else 0}")
    return embs


def load_cache():
    try:
        return pickle.load(open(CACHE, "rb"))
    except Exception:
        return {}


def save_cache(c):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    pickle.dump(c, open(CACHE, "wb"))


def embed_texts(texts, cache):
    out = []
    need, need_idx = [], []
    for i, t in enumerate(texts):
        n = norm(t)
        if h(t) in cache:
            out.append(np.asarray(cache[h(t)], dtype=np.float64))
        elif n and h(n) in cache:
            out.append(np.asarray(cache[h(n)], dtype=np.float64))
        else:
            out.append(None)
            need.append(t)
            need_idx.append(i)
    if need:
        eb = embed_batch(need)
        for k, t in enumerate(need):
            v = np.asarray(eb[k], dtype=np.float64)
            cache[h(t)] = v.tolist()
            if norm(t):
                cache[h(norm(t))] = v.tolist()
            out[need_idx[k]] = v
    return out


def star_to_int(d):
    return max(1, min(5, (d or "").count("★") + 1))


def build_reference(a):
    parts = []
    for k in ("简版", "展开", "加分点", "雷区"):
        v = (a or {}).get(k)
        if isinstance(v, list):
            v = "\n".join(str(x).strip() for x in v if str(x).strip())
        v = (v or "").strip()
        if v:
            parts.append(f"【{k}】\n{v}")
    return "\n\n".join(parts)


def progress_count(con, pid):
    n = 0
    for t in ("review_schedule", "submissions", "wrong_book"):
        try:
            n += con.execute(f'SELECT COUNT(*) FROM "{t}" WHERE question_id=?', (pid,)).fetchone()[0]
        except Exception:
            pass
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--thresh", type=float, default=THRESH)
    args = ap.parse_args()
    thr = args.thresh
    t0 = time.time()

    # 加载母库
    bank = json.load(open(BANK, encoding="utf-8"))["items"]
    B = len(bank)
    bank_texts = [it.get("content", "") or it.get("norm", "") for it in bank]
    bank_norms = [norm(t) for t in bank_texts]
    print(f"[load] 母库 {B} 题")

    # 连接练习库
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=0")
    qs = con.execute(
        "SELECT id, platform, category, tags, difficulty, question_text, reference_answer, created_at, images, keywords FROM questions"
    ).fetchall()
    P = len(qs)
    print(f"[load] 练习库 {P} 题")

    cache = load_cache()
    # 嵌入母库 + 练习
    bank_vecs = embed_texts(bank_texts, cache)
    prac_texts = [r[5] for r in qs]
    prac_vecs = embed_texts(prac_texts, cache)
    save_cache(cache)
    print(f"[embed] 母库+练习库向量就绪, 用时 {time.time()-t0:.1f}s")

    M_b = np.stack([v / (np.linalg.norm(v) or 1.0) for v in bank_vecs])  # B x 768
    M_p = np.stack([v / (np.linalg.norm(v) or 1.0) for v in prac_vecs])  # P x 768

    # ---- 阶段 A：练习库内部去重 ----
    parent = list(range(P))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    Sp = M_p @ M_p.T
    iu, ju = np.triu_indices(P, 1)
    mask = Sp[iu, ju] >= thr
    for a, b in zip(iu[mask].tolist(), ju[mask].tolist()):
        union(a, b)
    comp_map = {}
    for i in range(P):
        comp_map.setdefault(find(i), []).append(i)
    # 每组保留：进度最多 -> 答案最长
    pcount = {r[0]: progress_count(con, r[0]) for r in qs}
    internal_kept = []
    internal_removed = []  # (removed_idx, kept_idx)
    for members in comp_map.values():
        if len(members) == 1:
            internal_kept.append(members[0])
            continue
        best = max(members, key=lambda i: (pcount[qs[i][0]], len(qs[i][6] or "")))
        internal_kept.append(best)
        for i in members:
            if i != best:
                internal_removed.append((i, best))
    print(f"[A 内部去重] 删 {len(internal_removed)} (簇 {len(comp_map)-len(internal_kept)}) -> 保留 {len(internal_kept)}")

    # ---- 阶段 B：与母库交叉同步 ----
    Mk = M_p[internal_kept]  # K x 768 (K=len(internal_kept))
    Sim = Mk @ M_b.T  # K x B
    matches = {}  # bank_idx -> list of kept_idx
    unmatched_kept = []
    for ki, kidx in enumerate(internal_kept):
        row = Sim[ki]
        b = int(np.argmax(row))
        best_sim = float(row[b])
        # norm 精确优先
        pn = norm(prac_texts[kidx])
        exact_b = None
        if pn:
            for bi, bn in enumerate(bank_norms):
                if bn == pn:
                    exact_b = bi
                    break
        if exact_b is not None:
            matches.setdefault(exact_b, []).append(kidx)
        elif best_sim >= thr:
            matches.setdefault(b, []).append(kidx)
        else:
            unmatched_kept.append(kidx)

    # 一道母库题命中多道练习题：选进度最多者为 rep
    rep_map = {}  # bank_idx -> rep_practice_id (kept idx)
    redundant = []  # (removed_kept_idx, rep_kept_idx)
    for b, kids in matches.items():
        if len(kids) == 1:
            rep_map[b] = kids[0]
        else:
            rep = max(kids, key=lambda i: (pcount[qs[i][0]], len(qs[i][6] or "")))
            rep_map[b] = rep
            for i in kids:
                if i != rep:
                    redundant.append((i, rep))

    matched_bank = set(rep_map.keys())
    unmatched_bank = [b for b in range(B) if b not in matched_bank]
    print(f"[B 交叉] 母库命中 {len(matched_bank)} / 练习匹配 {len(internal_kept)-len(unmatched_kept)} / "
          f"练习独有 {len(unmatched_kept)} / 母库独有待插 {len(unmatched_bank)} / 冗余练习删 {len(redundant)}")

    # 进度外键重定向（内部删除 + 冗余删除 都指向保留者）
    reassign = {}  # from_pid -> to_pid
    for ri, ki in internal_removed:
        reassign[qs[ri][0]] = qs[ki][0]
    for ri, ki in redundant:
        reassign[qs[ri][0]] = qs[ki][0]

    plan = {
        "threshold": thr,
        "practice_before": P,
        "bank_total": B,
        "internal_removed": len(internal_removed),
        "redundant_removed": len(redundant),
        "matched_bank": len(matched_bank),
        "unmatched_bank_insert": len(unmatched_bank),
        "practice_custom_kept": len(unmatched_kept),
        "progress_rows_remapped": len(reassign),
        "practice_after_estimate": len(matched_bank) + len(unmatched_kept) + len(unmatched_bank),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    print(f"[plan] 练习库预计 {P} -> {plan['practice_after_estimate']} "
          f"(内部删 {len(internal_removed)} + 冗余删 {len(redundant)} + 插母库独有 {len(unmatched_bank)} + 自定义留 {len(unmatched_kept)})")
    print(f"[plan] 进度外键重定向 {len(reassign)} 条（学习进度零丢失）")

    if not args.apply:
        print("[info] 未加 --apply，练习库未改动。确认后运行 --apply。")
        con.close()
        return

    # ---- 写回 ----
    bak = DB + ".bak_" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(DB, bak)
    print(f"[backup] {bak}")

    cur = con.cursor()
    # 1) 重定向进度外键
    for frm, to in reassign.items():
        for t in ("review_schedule", "submissions", "wrong_book", "question_notes"):
            cur.execute(f'UPDATE "{t}" SET question_id=? WHERE question_id=?', (to, frm))
    # 2) 删除被合并的练习题（内部删除 + 冗余删除）
    del_ids = set()
    for ri, ki in internal_removed:
        del_ids.add(qs[ri][0])
    for ri, ki in redundant:
        del_ids.add(qs[ri][0])
    if del_ids:
        cur.execute(f"DELETE FROM questions WHERE id IN ({','.join('?'*len(del_ids))})", list(del_ids))
    print(f"[write] 删除被合并练习题 {len(del_ids)}")

    # 3) 富化匹配行（复用其 id）
    max_id = cur.execute("SELECT MAX(id) FROM questions").fetchone()[0] or 0
    enriched = 0

    def no_downgrade(new_ans, old_ans):
        """富化但不降级：母库答案比练习库原有答案更简略时保留原答案。

        背景：整体覆写曾导致 411 行答案被母库简版替换，丢失 14.4 万字。
        """
        return new_ans if len(new_ans) >= len(old_ans) else old_ans

    for b, kidx in rep_map.items():
        it = bank[b]
        pid = qs[kidx][0]
        cur.execute(
            """UPDATE questions SET
                 question_text=?, category=?, tags=?, difficulty=?, reference_answer=?, platform=?, keywords=?
               WHERE id=?""",
            (
                it.get("content", "").strip(),
                it.get("category", "") or "",
                ",".join(str(t).strip() for t in it.get("tags", []) if str(t).strip()),
                star_to_int(it.get("difficulty", "")),
                no_downgrade(build_reference(it.get("answer")) or it.get("content", ""),
                             qs[kidx][6] or ""),
                (it.get("source", "") or "WorkBuddy爬取")[:48],
                ",".join(str(t).strip() for t in it.get("tags", []) if str(t).strip()),
                pid,
            ),
        )
        enriched += 1
    print(f"[write] 富化匹配行 {enriched}")

    # 4) 插入母库独有题（新 id）
    inserted = 0
    for b in unmatched_bank:
        it = bank[b]
        max_id += 1
        cur.execute(
            """INSERT INTO questions (id, platform, category, tags, difficulty, question_text, reference_answer, created_at, images, keywords)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                max_id,
                (it.get("source", "") or "WorkBuddy爬取")[:48],
                it.get("category", "") or "",
                ",".join(str(t).strip() for t in it.get("tags", []) if str(t).strip()),
                star_to_int(it.get("difficulty", "")),
                it.get("content", "").strip(),
                build_reference(it.get("answer")) or it.get("content", ""),
                it.get("created_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
                "",
                ",".join(str(t).strip() for t in it.get("tags", []) if str(t).strip()),
            ),
        )
        inserted += 1
    print(f"[write] 插入母库独有题 {inserted}")
    # 5) 练习自定义题保留（不删不改）

    con.commit()
    # 校验：进度外键均有效
    cur.execute(
        "SELECT COUNT(*) FROM (SELECT question_id FROM review_schedule UNION SELECT question_id FROM submissions UNION SELECT question_id FROM wrong_book) sq "
        "WHERE question_id NOT IN (SELECT id FROM questions)"
    )
    orphan = cur.fetchone()[0]
    final_n = cur.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    print(f"[verify] 最终题数 {final_n} | 进度孤儿外键 {orphan} (应=0)")
    con.close()
    print(f"[apply] 完成。备份 {bak}")


if __name__ == "__main__":
    main()
