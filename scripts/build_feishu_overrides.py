#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把飞书两个知识库的答案，按题目匹配后固化为 questions_v2 的答案覆盖表。

优先级（由高到低）：
    1. 计算机知识库（人工手写）—— 优先兜底 Questionnaire 的真实面经答案
    2. Agent 开发面试题库（AI 加工）—— 次优
    3. authored 里原有的 AI 生成答案

匹配策略：
    - 先在该题目所属分类的「对口文档」里找（例如 redis.jsonl 只先在 cs 的
      《Redis面试题整理》里找），阈值较松；找不到再到 cs 全库（阈值中），
      最后到 agent 全库（阈值最严）。
    - 一个飞书答案块只能分配给一道题（按分数从高到低贪心独占），避免多题共用。
    - 过滤过短正文（< 80 字），避免残片覆盖结构化答案。

产物：
    crawler/questions_v2/feishu_answers.json       固化后的答案覆盖表（由 curate_full_v2.py 加载）
    data/tmp/feishu_match_report.csv               逐题匹配明细，供人工抽查

用法：
    .venv/Scripts/python scripts/build_feishu_overrides.py --dry-run
    .venv/Scripts/python scripts/build_feishu_overrides.py
"""
from __future__ import annotations

import re
import csv
import json
import html
import difflib
import argparse
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTHORED = ROOT / "crawler" / "questions_v2" / "authored"
DUMP = ROOT / "data" / "feishu_dump"
OUT_JSON = ROOT / "crawler" / "questions_v2" / "feishu_answers.json"
OUT_CSV = ROOT / "data" / "tmp" / "feishu_match_report.csv"

MIN_BODY = 80          # 飞书答案正文最短长度（字），低于此值视为残片
HINT_THRESHOLD = 0.62  # 对口文档内的相似度阈值
CS_THRESHOLD = 0.74    # cs 全库相似度阈值
AGENT_THRESHOLD = 0.82  # agent 全库相似度阈值（AI 库文案改写较多，要求更严）
# 字符重合度门槛：只看 SequenceMatcher 会把「什么是CRI」和「什么是IP地址」
# 这类字面相近但语义不同的标题误判为同一题。低分区要求更实的字面覆盖。
JACCARD_FLOOR = 0.45
MID_SCORE = 0.78
MID_JACCARD_FLOOR = 0.60
# 只自动应用高置信匹配；中低分一律输出到清单由人工确认后通过 --accept-extra 放行，
# 避免把「为什么用 WebSocket」写成「为什么用 WebRTC 而不是 WebSocket」这类错配写进题库。
AUTO_APPLY = 0.85

# 分类 -> 对口文档的标题片段（按 cs 优先排序；文档名取自 data/feishu_dump）
DOMAIN_HINTS = {
    "redis": ["Redis面试题整理"],
    "mysql": ["Mysql面试题整理", "MongoDB面试题库"],
    "go": ["Golang面试题整理"],
    "os-network": ["操作系统面试题整理", "计算机网络面试题整理"],
    "mq": ["Kafka面试题整理"],
    "distributed": ["分布式面试题整理", "分布式ID", "分布式锁"],
    "design-pattern": ["设计模式知识库"],
    "puzzle": ["智力题题库"],
    "engineering": ["docker面试题整理", "K8s面试题整理", "k8s学习笔记"],
    "system-design": ["系统设计题库", "系统设计面试题题库", "架构设计题库",
                      "海量数据处理题库", "秒杀", "高并发限流", "聚合写优化",
                      "分库分表", "缓存"],
    "agent": ["Agent概念基础", "Agent架构设计", "Agent工程落地", "AsyncFlow"],
    "rag": ["RAG", "LangChain"],
    "prompt": ["Prompt提示词工程"],
    "llm-basics": ["人工智能面试题库"],
    "behavioral": ["HR面问题准备", "项目深挖", "社招面经"],
    "general": ["简历专项题库"],
    "algorithm": ["手撕算法", "数据结构与算法"],
    "evaluation": [],
    "java": [],
    "frontend": [],
    "multimodal": [],
    "safety": [],
    "llm-pretraining": [],
    "llm-posttraining": [],
    "ai-product": [],
}

SKIP_FILE_KEYWORDS = ("无答案版", "每日推送归档", "首页")
# 作者明确排除的内容：自己的项目资料属于项目文档，不是通用面试题，不混入题库。
EXCLUDE_FILE_KEYWORDS = ("AsyncFlow",)

DROP_LINE_RE = [
    re.compile(r"^\s*\*?\s*(?:来源|参考来源|参考资料)\s*[:：]"),
    re.compile(r"^\s*-\s*\[.{0,80}\]\(https?://"),
    re.compile(r"^\s*\*\s*来源\s*[:：]"),
]


def norm(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"^\s*[Qq]?\d+[\.、:：]\s*", "", s.strip())
    s = re.sub(r"^#+\s*", "", s)
    s = re.sub(r"^\*+|\*+$", "", s)
    return re.sub(r"[^\w]", "", s).lower()


def clean_body(body: str) -> str:
    lines = []
    for line in body.split("\n"):
        s = line.rstrip()
        if any(rx.search(s) for rx in DROP_LINE_RE):
            continue
        lines.append(s)
    text = "\n".join(lines)
    # 飞书导出物的常见噪声：分隔线、裸 URL、不可核验的外链（保留可读标题）
    text = re.sub(r"\[([^\]\n]{1,60})\]\(https?://[^)\n]+\)", r"\1", text)
    text = re.sub(r"(?m)^\s*-{3,}\s*$", "", text)
    text = re.sub(r"(?m)^\s*https?://\S+\s*$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_md(path: Path, space: str):
    """返回 [(title, chapter, file_label, body)]；h1 视为章节，h2/h3 视为题目。"""
    blocks = []
    chapter = ""
    cur: dict | None = None
    first_h1 = True
    for line in path.read_text(encoding="utf-8").split("\n"):
        m = re.match(r"^(#{1,3}) (.+)$", line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            if level == 1:
                if first_h1:
                    first_h1 = False
                    continue
                chapter = text.strip("*")
                continue
            if cur:
                blocks.append(cur)
            cur = {"title": text, "chapter": chapter, "file": path.stem, "space": space,
                   "body": []}
        elif cur is not None:
            cur["body"].append(line)
    if cur:
        blocks.append(cur)

    out = []
    for b in blocks:
        if any(k in b["file"] for k in SKIP_FILE_KEYWORDS + EXCLUDE_FILE_KEYWORDS):
            continue
        body = clean_body("\n".join(b["body"]))
        if len(body) < MIN_BODY:
            continue
        title = b["title"].strip().strip("*").strip()
        if not title:
            continue
        out.append({"title": title, "chapter": b["chapter"], "file": b["file"],
                    "space": b["space"], "body": body})
    return out


def load_blocks(space: str):
    blocks = []
    d = DUMP / space
    if not d.exists():
        return blocks
    for p in sorted(d.glob("*.md")):
        blocks.extend(parse_md(p, space))
    return blocks


def build_index(blocks):
    idx = collections.defaultdict(list)
    for i, b in enumerate(blocks):
        n = norm(b["title"])
        if n:
            idx[n[:3]].append(i)
    return idx


def char_jaccard(a: str, b: str) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0


def acceptable(ratio: float, jaccard: float) -> bool:
    """字面相似度足够，且字集合覆盖不是「同一批虚词撑起来的」。"""
    if jaccard < JACCARD_FLOOR:
        return False
    if ratio < MID_SCORE and jaccard < MID_JACCARD_FLOOR:
        return False
    return True


def best_match(key: str, blocks, idx) -> tuple[float, int] | None:
    cands = idx.get(key[:3], [])
    best, best_i = 0.0, -1
    for i in cands:
        n = norm(blocks[i]["title"])
        if abs(len(n) - len(key)) > max(len(n), len(key)) * 0.55:
            continue
        r = difflib.SequenceMatcher(None, key, n).ratio()
        if r <= best:
            continue
        if not acceptable(r, char_jaccard(key, n)):
            continue
        best, best_i = r, i
    return (best, best_i) if best_i >= 0 else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写 feishu_answers.json")
    ap.add_argument("--min-body", type=int, default=MIN_BODY)
    ap.add_argument("--accept-extra", default="",
                    help="人工确认可用的中低分 qid，逗号分隔（见 dry-run 输出的中低分清单）")
    args = ap.parse_args()
    extra_ids = {x.strip() for x in args.accept_extra.split(",") if x.strip()}

    cs_blocks = load_blocks("cs")
    agent_blocks = load_blocks("agent")
    cs_idx = build_index(cs_blocks)
    agent_idx = build_index(agent_blocks)
    print(f"可候选答案块：cs {len(cs_blocks)} / agent {len(agent_blocks)}")

    items = []
    for p in sorted(AUTHORED.glob("*.jsonl")):
        if p.name.startswith("_"):
            continue
        domain = p.stem
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                it = json.loads(line)
                it["_domain"] = domain
                items.append(it)
    print(f"authored 题目：{len(items)}")

    candidates = []
    for it in items:
        key = norm(it.get("title", ""))
        if len(key) < 4:
            continue
        hints = DOMAIN_HINTS.get(it["_domain"], [])
        for space, blocks, idx, default_th in (
            ("cs", cs_blocks, cs_idx, CS_THRESHOLD),
            ("agent", agent_blocks, agent_idx, AGENT_THRESHOLD),
        ):
            hint_ids = [i for i, b in enumerate(blocks)
                        if any(h in b["file"] for h in hints)] if hints else []
            m = None
            if hint_ids:
                sub_idx = collections.defaultdict(list)
                for i in hint_ids:
                    n = norm(blocks[i]["title"])
                    if n:
                        sub_idx[n[:3]].append(i)
                m = best_match(key, blocks, sub_idx)
                if m and m[0] >= HINT_THRESHOLD:
                    candidates.append((m[0], it["id"], (space, m[1])))
                    continue
            m = best_match(key, blocks, idx)
            if m and m[0] >= default_th:
                candidates.append((m[0], it["id"], (space, m[1])))

    # 贪心独占：一个飞书答案块只给一道题
    candidates.sort(key=lambda x: -x[0])
    used_blocks: set[tuple[str, int]] = set()
    assigned: dict[str, tuple[str, int, float]] = {}
    pending = []
    for score, qid, ref in candidates:
        if qid in assigned or ref in used_blocks:
            continue
        if score < AUTO_APPLY and qid not in extra_ids:
            pending.append((score, qid, ref))
            continue
        assigned[qid] = (ref[0], ref[1], score)
        used_blocks.add(ref)

    by_id = {it["id"]: it for it in items}
    out, rows = {}, []
    for qid, (space, bi, score) in sorted(assigned.items()):
        blocks = cs_blocks if space == "cs" else agent_blocks
        b = blocks[bi]
        it = by_id[qid]
        old_len = len(it.get("answer", ""))
        out[qid] = {
            "answer": b["body"],
            "source": f"{space}:{b['file']}",
            "chapter": b["chapter"],
            "matched_title": b["title"],
            "score": round(score, 3),
        }
        rows.append({
            "qid": qid, "domain": it["_domain"], "title": it.get("title", ""),
            "matched_title": b["title"], "space": space, "file": b["file"],
            "chapter": b["chapter"], "score": round(score, 3),
            "new_len": len(b["body"]), "old_len": old_len,
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    stat = collections.Counter(r["domain"] for r in rows)
    src_stat = collections.Counter(r["space"] for r in rows)
    print(f"\n匹配成功 {len(rows)} 道（cs {src_stat['cs']} / agent {src_stat['agent']}）")
    print(f"明细表：{OUT_CSV}")
    print("\n按分类：")
    total_dom = collections.Counter(it["_domain"] for it in items)
    for d, n in stat.most_common():
        print(f"  {d:<18}{n:>5}/{total_dom[d]:<5}（{n / total_dom[d] * 100:5.1f}%）")
    print("\n答案长度变化中位数：", sorted(r["new_len"] - r["old_len"] for r in rows)[len(rows) // 2])

    if pending:
        print(f"\n中低分待确认 {len(pending)} 条（<{AUTO_APPLY}，未自动应用；"
              f"人工确认后用 --accept-extra <qid> 放行）：")
        for score, qid, ref in pending[:40]:
            blocks = cs_blocks if ref[0] == "cs" else agent_blocks
            b = blocks[ref[1]]
            it = by_id[qid]
            print(f"  {qid} [{it['_domain']}] {it.get('title', '')[:30]}")
            print(f"      <=> {b['title'][:44]}  ({round(score, 3)}, {ref[0]})")

    for label, lo, hi in (("0.62-0.75", 0.0, 0.75), ("0.75-0.85", 0.75, 0.85),
                          ("0.85-1.00", 0.85, 1.01)):
        seg = [r for r in rows if lo <= r["score"] < hi]
        print(f"\n[{label}] {len(seg)} 条，抽样：")
        for r in seg[:6]:
            print(f"  {r['qid']} [{r['domain']}] {r['title'][:24]}")
            print(f"        <=> {r['matched_title'][:40]}  ({r['score']}, {r['space']})")

    if args.dry_run:
        print("\n[dry-run] 未写 feishu_answers.json")
        return
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n已写入 {OUT_JSON}（{len(out)} 条，{OUT_JSON.stat().st_size / 1024:.0f} KB）")


if __name__ == "__main__":
    main()
