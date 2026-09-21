#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把飞书《计算机知识库》里尚未进题库的专题内容收录为新题。

两类来源：
  A. 问答型文档（RAG / Prompt / LangChain）：h2 本身就是题目、正文就是答案，直接收录。
  B. 笔记型文档（限流 / 分布式锁 / 分布式 ID / 缓存模式 / 聚合写 / 秒杀 / 小文件存储 /
     分库分表）：原文是教程式小标题，不是问答题。这里按「章节切片」合成题干，
     答案保持原文（只去掉图片、表格残留等飞书导出噪声）。

收录原则：
  - 答案优先保留作者原文表述，不改写技术内容；
  - 与现有题库（authored/ 全量）题干高度重复的跳过；
  - 新题 id 使用 q5000 段，避免与历史 id 冲突；
  - 幂等：重复执行不会产生重复题。

用法：
  .venv/Scripts/python scripts/intake_feishu_topics.py --dry-run
  .venv/Scripts/python scripts/intake_feishu_topics.py
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
DUMP = ROOT / "data" / "feishu_dump" / "cs"
AUTHORED = ROOT / "crawler" / "questions_v2" / "authored"
REPORT = ROOT / "data" / "tmp" / "intake_report.csv"

FIRST_ID = 5001
DUPLICATE_THRESHOLD = 0.72

QQA = "人工智能面试题库__"
F_BACKEND = "后端优化集合__"


# ---------------------------------------------------------------- 文档解析
def load_blocks(filename: str) -> list[dict]:
    path = DUMP / filename
    blocks, cur, chapter = [], None, ""
    for line in path.read_text(encoding="utf-8").split("\n"):
        m = re.match(r"^(#{1,4}) (.+)$", line)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            if level == 1:
                chapter = title.strip("*")
                continue
            if cur:
                blocks.append(cur)
            cur = {"lv": level, "title": title.strip("*").strip(), "chapter": chapter, "body": []}
        elif cur is not None:
            cur["body"].append(line)
    if cur:
        blocks.append(cur)
    for i, b in enumerate(blocks):
        b["idx"] = i
        b["body"] = clean_body("\n".join(b["body"]))
        b["len"] = len(b["body"])
    return blocks


IMG_RE = re.compile(r"^\s*!\[.*\]\(\s*https?://[^)]*\)\s*$")
IMG_INLINE_RE = re.compile(r"!\[.*?\]\(\s*https?://[^)]*\)")
TAG_RE = re.compile(r"</?(?:sheet|table|readonly-block|callout|bitable|img|title)[^>]*>")


def clean_body(text: str) -> str:
    """清掉飞书导出的噪声：图片语法、内嵌表格/画板残留标签。

    注意图片的 alt 文本里可能出现转义的方括号（如 ``KEYS\\[1\\]``），
    用 ``[^\\]]*`` 匹配 alt 会提前截断，因此这里按「整行是图片」来删。
    """
    lines = []
    for line in text.split("\n"):
        if IMG_RE.match(line):
            continue
        line = IMG_INLINE_RE.sub("", line)
        line = TAG_RE.sub("", line)
        line = re.sub(r"^\s*<colgroup>.*", "", line)
        lines.append(line.rstrip())
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_title(t: str) -> str:
    t = re.sub(r"\[([^\]\n]+)\]\([^)\n]+\)", r"\1", t)
    t = re.sub(r"^\*+|\*+$", "", t.strip())
    return re.sub(r"\s+", " ", t).strip()


def _match(block: dict, key: str) -> bool:
    """章节名（h1）或块标题（h2/h3）命中即可，笔记型文档两种层级混用。"""
    return key in block["chapter"] or key in block["title"]


def _find(blocks: list[dict], key: str, occurrence: int = 1) -> int | None:
    n = 0
    for b in blocks:
        if _match(b, key):
            n += 1
            if n == occurrence:
                return b["idx"]
    return None


def slice_by(blocks: list[dict], start: str | None = None, end: str | None = None,
             start_occ: int = 1, end_occ: int = 1, include_end: bool = False) -> list[dict]:
    """按「章节名/块标题」切出连续区间；occurrence 用于消歧同名小标题。

    起点必须命中，否则直接报错，避免静默退化成「取全篇」。
    """
    lo = 0
    if start:
        idx = _find(blocks, start, start_occ)
        if idx is None:
            raise ValueError(f"切片起点未匹配：{start}")
        lo = idx
    hi = len(blocks)
    if end:
        idx = _find(blocks, end, end_occ)
        if idx is not None:
            hi = idx + (1 if include_end else 0)
    return [b for b in blocks if lo <= b["idx"] < hi and b["len"] >= 20]


def join_blocks(picked: list[dict]) -> str:
    parts = []
    for b in picked:
        body = b["body"].strip()
        if not body:
            continue
        title = clean_title(b["title"])
        if title:
            parts.append(f"**{title}**\n\n{body}")
        else:
            parts.append(body)
    return "\n\n".join(parts)


# ---------------------------------------------------------------- 收录清单
QA_SPECS = [
    {"file": QQA + "RAG 检索增强生成面试题.md", "domain": "rag", "freq": 4},
    {"file": QQA + "Prompt提示词工程面试题.md", "domain": "prompt", "freq": 4},
    {"file": QQA + "LangChain面试题.md", "domain": "agent", "freq": 4},
]

SYNTH_SPECS = [
    # ---- 限流 ----
    {"file": F_BACKEND + "高并发限流解决方案.md", "domain": "system-design", "freq": 4,
     "title": "为什么要限流？限流能解决哪些问题？",
     "chapters": [{"start": "为什么要限流", "end": "限流基本算法"}]},
    {"file": F_BACKEND + "高并发限流解决方案.md", "domain": "system-design", "freq": 5,
     "title": "固定窗口、滑动窗口、漏斗、令牌桶四种限流算法的原理、优缺点与适用场景分别是什么？",
     "chapters": [{"start": "限流基本算法", "end": "分布式限流"}]},
    {"file": F_BACKEND + "高并发限流解决方案.md", "domain": "system-design", "freq": 4,
     "title": "分布式限流有哪些实现方案？中心化限流与负载均衡方案各有什么问题？",
     "chapters": [{"start": "分布式限流", "end": "Java版本demo代码"}]},
    # ---- 缓存模式 ----
    {"file": F_BACKEND + "缓存优化__缓存相关内容整理.md", "domain": "system-design", "freq": 4,
     "title": "常见的缓存使用模式有哪些？旁路缓存、读穿透、写穿透、写回分别适合什么场景？",
     "chapters": [{}]},
    # ---- 聚合写 ----
    {"file": F_BACKEND + "聚合写优化.md", "domain": "system-design", "freq": 4,
     "title": "聚合写是什么？它如何把写入性能提升数十倍？",
     "chapters": [{"start": "开篇-聚合写是什么", "end": "实战-实现点赞计数接口"}]},
    {"file": F_BACKEND + "聚合写优化.md", "domain": "system-design", "freq": 3,
     "title": "聚合写会带来哪些可靠性和一致性问题？落地时应该如何取舍？",
     "chapters": [{"start": "扩展-聚合写对可靠性的影响"}]},
    # ---- 分布式锁 ----
    {"file": F_BACKEND + "分布式锁.md", "domain": "distributed", "freq": 4,
     "title": "什么是分布式锁？它应该具备哪些性质？为什么需要分布式锁？",
     "chapters": [{"start": "分布式锁是什么？——What", "end": "1. 实现分类"}]},
    {"file": F_BACKEND + "分布式锁.md", "domain": "distributed", "freq": 5,
     "title": "主动轮询型分布式锁的实现思路是什么？MySQL 和 Redis 分别怎么实现？",
     "chapters": [{"start": "1. 实现分类", "end": "对称性：谁加锁谁释放", "include_end": True}]},
    {"file": F_BACKEND + "分布式锁.md", "domain": "distributed", "freq": 4,
     "title": "监听回调型分布式锁是怎么实现的？Etcd 的 Watch 机制在其中起什么作用？",
     "chapters": [{"start": "2.1 实现思路", "start_occ": 2, "end": "2.3 Zookeeper分布式锁"}]},
    {"file": F_BACKEND + "分布式锁.md", "domain": "distributed", "freq": 4,
     "title": "ZooKeeper 分布式锁的实现原理是什么？和 Redis 锁有什么差异？",
     "chapters": [{"start": "2.3 Zookeeper分布式锁", "end": "四、分布式锁如何选择"}]},
    {"file": F_BACKEND + "分布式锁.md", "domain": "distributed", "freq": 4,
     "title": "Redis、Etcd、ZooKeeper 分布式锁应该如何选型？红锁到底该不该用？",
     "chapters": [{"start": "四、分布式锁如何选择"}]},
    # ---- 分布式 ID ----
    {"file": F_BACKEND + "分布式ID.md", "domain": "distributed", "freq": 4,
     "title": "分布式 ID 需要满足哪些特性？主流实现方案有哪些？",
     "chapters": [{"start": "一、分布式ID是什么", "end": "1. UUID"}]},
    {"file": F_BACKEND + "分布式ID.md", "domain": "distributed", "freq": 5,
     "title": "雪花算法（Snowflake）的原理是什么？时钟回拨会带来什么问题？",
     "chapters": [{"start": "1. UUID", "end": "3. MySQL"}]},
    {"file": F_BACKEND + "分布式ID.md", "domain": "distributed", "freq": 3,
     "title": "用 MySQL 自增主键或 Redis INCR 生成分布式 ID 各有什么优缺点？",
     "chapters": [{"start": "3. MySQL"}]},
    # ---- 秒杀 ----
    {"file": "场景题内容整理__秒杀场景设计__秒杀设计整体流程.md", "domain": "system-design", "freq": 5,
     "title": "如何设计一个秒杀系统？需求对齐和难点分析阶段分别要确认什么？",
     "chapters": [{"start": "沟通对齐", "end": "请求量对齐"}, {"start": "难点分析", "end": "思路"}]},
    {"file": "场景题内容整理__秒杀场景设计__秒杀设计整体流程.md", "domain": "system-design", "freq": 5,
     "title": "不同请求量级（5k / 1w / 10w / 10w 以上）的秒杀方案分别应该怎么设计？",
     "chapters": [{"start": "请求量对齐", "end": "是否允许小概率超卖"}]},
    {"file": "场景题内容整理__秒杀场景设计__秒杀设计整体流程.md", "domain": "system-design", "freq": 4,
     "title": "秒杀系统如何防止超卖和少卖？黄牛又该怎么打击？",
     "chapters": [{"start": "是否允许小概率超卖", "end": "思路"},
                  {"start": "打击黄牛", "end": "套路"}]},
    {"file": "场景题内容整理__秒杀场景设计__秒杀设计整体流程.md", "domain": "system-design", "freq": 5,
     "title": "秒杀系统的服务拆分、存储设计与预扣库存应该怎么落地？",
     "chapters": [{"start": "服务设计", "end": "生成订单、扣减库存"}]},
    {"file": "场景题内容整理__秒杀场景设计__秒杀设计整体流程.md", "domain": "system-design", "freq": 4,
     "title": "秒杀系统的订单生成、库存回补与超时处理如何设计？",
     "chapters": [{"start": "生成订单、扣减库存", "end": "打击黄牛"}]},
    {"file": "场景题内容整理__秒杀场景设计__秒杀设计整体流程.md", "domain": "system-design", "freq": 4,
     "title": "微信支付优惠券秒杀实战：异步化发券、库存批量消费是怎么做的？",
     "chapters": [{"start": "实战案例"}]},
    # ---- 小文件存储 ----
    {"file": "场景题内容整理__小文件存储系统设计.md", "domain": "system-design", "freq": 4,
     "title": "为什么通用文件系统不适合海量小文件？应该怎么设计小文件存储系统？",
     "chapters": [{}]},
    # ---- 分库分表 ----
    {"file": "分库分表问题收集.md", "domain": "system-design", "freq": 5,
     "title": "分库分表会遇到哪些问题？应该怎么解决？",
     "chapters": [{}]},
]


# ---------------------------------------------------------------- 去重
def norm(s: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s or "")
    s = re.sub(r"^\s*[Qq]?\d+[\.、:：]\s*", "", s.strip())
    return re.sub(r"[^\w]", "", s).lower()


def load_existing():
    items = []
    for f in sorted(AUTHORED.glob("*.jsonl")):
        if f.name.startswith("_"):
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append((f.stem, json.loads(line)))
    return items


def build_index(items):
    idx = collections.defaultdict(list)
    for _, it in items:
        k = norm(it.get("title", ""))
        if k:
            idx[k[:3]].append(k)
    return idx


def is_duplicate(title: str, index) -> tuple[bool, str]:
    k = norm(title)
    if not k:
        return False, ""
    for cand in index.get(k[:3], []):
        if abs(len(cand) - len(k)) > max(len(cand), len(k)) * 0.4:
            continue
        if difflib.SequenceMatcher(None, k, cand).ratio() >= DUPLICATE_THRESHOLD:
            return True, cand
    return False, ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="先移除上一批收录（id >= q5001），用于重跑修正后的收录规则")
    args = ap.parse_args()

    if args.reset:
        removed = 0
        for f in sorted(AUTHORED.glob("*.jsonl")):
            if f.name.startswith("_"):
                continue
            kept = []
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                it = json.loads(line)
                if re.fullmatch(r"q\d+", it["id"]) and int(it["id"][1:]) >= FIRST_ID:
                    removed += 1
                    continue
                kept.append(line)
            text = "".join(line + "\n" for line in kept)
            f.write_bytes(text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
        print(f"[reset] 移除上一批收录 {removed} 题\n")

    existing = load_existing()
    index = build_index(existing)
    print(f"现有题库 {len(existing)} 题")

    collected: list[dict] = []
    next_id = FIRST_ID

    def add(domain: str, title: str, answer: str, freq: int, source: str):
        nonlocal next_id
        dup, hit = is_duplicate(title, index)
        if dup:
            print(f"  [跳过重复] {title[:40]}  ~  {hit[:40]}")
            return
        qid = f"q{next_id}"
        next_id += 1
        collected.append({
            "id": qid, "title": title, "answer": answer,
            "kaodian": "", "framework": "", "followup": "",
            "freq": freq, "source_file": source, "_domain": domain,
        })
        k = norm(title)
        index[k[:3]].append(k)

    # A 类：问答型
    for spec in QA_SPECS:
        blocks = load_blocks(spec["file"])
        usable = [b for b in blocks if b["len"] >= 80]
        print(f"\n{spec['file'].split('__')[-1][:-3]}：候选 {len(usable)}")
        for b in usable:
            add(spec["domain"], clean_title(b["title"]), b["body"], spec["freq"], spec["file"])

    # B 类：笔记型 → 合成题干
    print("\n合成题：")
    for spec in SYNTH_SPECS:
        blocks = load_blocks(spec["file"])
        picked = []
        for seg in spec["chapters"]:
            picked.extend(slice_by(blocks, **seg))
        seen, uniq = set(), []
        for b in picked:
            if b["idx"] in seen:
                continue
            seen.add(b["idx"])
            uniq.append(b)
        answer = join_blocks(uniq)
        print(f"  {spec['title'][:46]:<48} 块 {len(uniq):>3}  字数 {len(answer):>5}"
              f"  <- {spec['file'].split('__')[-1][:-3]}")
        if len(answer) < 150:
            print("     [跳过] 内容过短")
            continue
        add(spec["domain"], spec["title"], answer, spec["freq"], spec["file"])

    print(f"\n合计可新增 {len(collected)} 题")
    stat = collections.Counter(it["_domain"] for it in collected)
    for d, n in stat.most_common():
        print(f"  {d:<16}{n}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with REPORT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "domain", "title", "freq", "source_file",
                                          "answer_len"])
        w.writeheader()
        for it in collected:
            w.writerow({"id": it["id"], "domain": it["_domain"], "title": it["title"],
                        "freq": it["freq"], "source_file": it["source_file"],
                        "answer_len": len(it["answer"])})
    print(f"清单：{REPORT}")

    if args.dry_run:
        print("\n[dry-run] 未写入 authored/*.jsonl")
        return

    by_domain = collections.defaultdict(list)
    for it in collected:
        by_domain[it["_domain"]].append(it)
    for domain, items in by_domain.items():
        path = AUTHORED / f"{domain}.jsonl"
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        lines = [json.dumps({k: v for k, v in it.items() if k != "_domain"},
                            ensure_ascii=False) for it in items]
        body = old + "".join(line + "\n" for line in lines)
        path.write_bytes(body.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
        print(f"追加 {len(items)} 题 -> {path.name}")
    print(f"\n完成：新增 {len(collected)} 题。接下来跑 curate_full_v2.py 再 --replace 导入。")


if __name__ == "__main__":
    main()
