#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建待入库清单：对三站 posts 抽取题目 -> 跨源 + 题库 0.85 去重 -> 日期过滤(近35天) -> 输出 _to_add.jsonl。

输出字段：content/category/type/difficulty/tags/sources/platform/date/date_in_range
- 小红书：解析 date 字段，超出 35 天的标记 date_in_range=False（仍保留，供人工决定）
- 知乎/掘金：无 date，标记 date_in_range='unknown'

用法：python build_add_list.py
依赖：process_source（抽取+题库去重）、bank（读取题库 norms）
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from difflib import SequenceMatcher

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
import process_source as PS
import bank

TODAY = datetime(2026, 8, 1)
CUTOFF_DAYS = 35          # 近 1 个月（略宽松）
SOURCES = ["xiaohongshu", "zhihu", "juejin"]
PLAT_NAME = {"xiaohongshu": "小红书", "zhihu": "知乎", "juejin": "掘金"}

# ---------- 日期解析 ----------
def parse_xhs_date(s):
    if not s:
        return None
    t = s.replace("编辑于", "").strip()
    # 相对时间
    m = re.search(r"(\d+)\s*分钟前", t)
    if m:
        return TODAY - timedelta(minutes=int(m.group(1)))
    m = re.search(r"(\d+)\s*小时前", t)
    if m:
        return TODAY - timedelta(hours=int(m.group(1)))
    m = re.search(r"(\d+)\s*天前", t)
    if m:
        return TODAY - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s*周前", t)
    if m:
        return TODAY - timedelta(weeks=int(m.group(1)))
    if "昨天" in t:
        return TODAY - timedelta(days=1)
    if "前天" in t:
        return TODAY - timedelta(days=2)
    if "今天" in t:
        return TODAY
    # 绝对：MM-DD 或 YYYY-MM-DD
    m = re.search(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})", t)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{1,2})[-/月.](\d{1,2})", t)
    if m:
        return datetime(TODAY.year, int(m.group(1)), int(m.group(2)))
    return None


def date_in_range(d):
    if d is None:
        return "unknown"
    return (TODAY - d).days <= CUTOFF_DAYS


# ---------- 难度 / 标签 ----------
def guess_difficulty(cat, q):
    ql = q.lower()
    hard = re.search(r"原理|为什么|如何设计|如何优化|架构|分布式|底层|源码|实现|对比|区别|调优|排查|内存|并发|一致性", ql)
    easy = re.search(r"什么是|讲讲|介绍|说说|了解|概念|区别.*\??$|定义", ql)
    if cat in ("架构设计", "工程落地"):
        return "★★★" if hard else "★★☆"
    if cat == "手撕算法":
        return "★★★" if re.search(r"困难|动态规划|回溯|hard", ql) else "★★☆"
    if cat in ("概念基础", "行为与HR"):
        return "★☆☆" if easy else "★★☆"
    if cat == "后端八股（Go）":
        return "★★☆"
    if cat == "项目深挖":
        return "★★☆"
    return "★★☆"


KW = {
    "RAG": r"\brag\b|检索增强|召回|重排|向量库|embedding",
    "Agent": r"agent|智能体|工具调用|规划|反思|记忆|多agent|multi.?agent",
    "LLM": r"大模型|llm|transformer|注意力|微调|预训练|推理|部署|量化",
    "Go": r"\bgo\b|goroutine|channel|gmp|协程|gc\b|context|切片",
    "分布式": r"分布式|一致性|共识|分片|副本",
    "高并发": r"高并发|限流|熔断|降级|缓存|线程|锁",
    "Prompt": r"prompt|提示词|few.?shot|cot|思维链|上下文",
    "MCP": r"\bmcp\b|a2a|协议|工具",
    "评测": r"评测|评估|指标|faithfulness|对齐",
    "可观测": r"可观测|trace|日志|监控|debug",
}
def guess_tags(cat, q):
    tags = []
    ql = q.lower()
    for tag, pat in KW.items():
        if re.search(pat, ql):
            tags.append(tag)
    tags.append(cat)
    seen = set()
    out = []
    for t in tags:
        if t not in seen:
            seen.add(t); out.append(t)
    return out[:5]


# ---------- 质量闸门 ----------
# 噪声：碎片、列表标记残留、陈述句、口水话
NOISE_PAT = [
    r"^[a-zA-Z]\s*[.、)]",              # "a. xxx" 残留编号
    r"^[①②③④⑤⑥⑦⑧⑨⑩▫️◾•·\-—*>》\d]+[\s.、)]*$",
    r"^(核心总结|总结|小结|以上|最后|另外|其他|ps|PS)[:：]?",
    r"别只背|加油|冲鸭|求好运|许愿|码住|收藏|关注我|评论区|私信|接好运|上岸",
    r"^\d{1,2}[-/]\d{1,2}",             # 日期开头
    r"^(第[一二三四五六七八九十]+[面轮])",
    r"备战方向|时间轴|面经合集|经验分享|如下|如上",
]
NOISE_RE = [re.compile(p, re.I) for p in NOISE_PAT]

# AI / Agent / 大模型 相关性（用户本次只要 AI Agent 方向）
AI_RE = re.compile(
    r"agent|智能体|大模型|\bllm\b|\brag\b|langchain|langgraph|\bmcp\b|\ba2a\b|"
    r"prompt|提示词|思维链|\bcot\b|react|微调|\bsft\b|\blora\b|\bdpo\b|\bppo\b|\brlhf\b|"
    r"embedding|向量|检索|召回|重排|rerank|知识库|多模态|token|上下文窗口|context\s*window|"
    r"transformer|注意力|attention|\bkv\s*cache\b|\bmoe\b|\bgqa\b|\bmha\b|\bmla\b|\brope\b|rmsnorm|"
    r"推理加速|量化|蒸馏|幻觉|对齐|工具调用|function\s*call|tool\s*call|工作流|workflow|"
    r"记忆|memory|规划|planning|反思|reflection|多智能体|multi.?agent|评测|llm\s*as\s*judge|"
    r"vllm|sglang|ollama|deepseek|qwen|gpt|claude|bert|扩散|diffusion|强化学习|奖励模型|reward",
    re.I,
)

# 纯后端/传统八股（本次不作为 AI 主线，但单独留一桶）
BACKEND_RE = re.compile(
    r"mysql|innodb|索引|事务|隔离级别|\bb\+?树\b|redis|kafka|spring|jvm|垃圾回收|"
    r"tcp|http|三次握手|操作系统|进程|线程|死锁|分库分表|主从|binlog",
    re.I,
)


def quality_ok(q):
    """返回 (是否保留, 原因)"""
    s = q.strip()
    n = len(s)
    if n < 8:
        return False, "too_short"
    if n > 80:
        return False, "too_long"
    for r in NOISE_RE:
        if r.search(s):
            return False, "noise"
    # 至少要像个问题：含疑问词/问号，或是明确的技术名词罗列考点
    interrogative = re.search(
        r"[?？]|为什么|怎么|如何|是什么|什么是|哪些|区别|对比|讲讲|说说|介绍|"
        r"原理|实现|优化|设计|解决|处理|选型|流程|机制|作用|区分|评估",
        s,
    )
    if not interrogative:
        return False, "not_question"
    return True, "ok"


def relevance(q):
    if AI_RE.search(q):
        return "ai"
    if BACKEND_RE.search(q):
        return "backend"
    return "other"


def process_and_merge():
    bank_data = bank.load()
    bank_keys = [PS.norm(PS.bank_text(it)) for it in bank_data.get("items", []) if PS.bank_text(it)]
    merged = []
    for src in SOURCES:
        # 抽取 + 题库 0.85 去重（process 内部已写 refined.jsonl）
        PS.process(src)
        rf = BASE / "data" / "tmp" / src / "refined.jsonl"
        if not rf.exists():
            continue
        for line in open(rf, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            merged.append((src, r))
    # 跨源去重（同一题可能多源出现）
    seen_norms = []
    final = []
    for src, r in merged:
        q = r["question"].strip()
        nq = PS.norm(q)
        if any(SequenceMatcher(None, nq, x).ratio() >= PS.STRICT for x in seen_norms):
            continue
        seen_norms.append(nq)
        final.append((src, r))
    return final, bank_keys


def main():
    final, bank_keys = process_and_merge()
    # 加载小红书 posts 的 url->date 映射，用于日期过滤
    xhs_posts = [json.loads(l) for l in open(BASE / "data" / "tmp" / "xiaohongshu" / "posts.jsonl", encoding="utf-8") if l.strip()]
    url2date = {}
    for p in xhs_posts:
        u = p.get("url", "")
        d = parse_xhs_date(p.get("date", ""))
        if u:
            url2date[u] = d

    out = []
    rej = {"too_short": 0, "too_long": 0, "noise": 0, "not_question": 0,
           "bank_dup": 0, "out_of_window": 0, "not_ai": 0}
    for src, r in final:
        q = r["question"].strip()
        cat = r["category"]
        nq = PS.norm(q)
        # 与题库再核一遍（process 已做，这里双重保险）
        if any(SequenceMatcher(None, nq, bk).ratio() >= PS.STRICT for bk in bank_keys):
            rej["bank_dup"] += 1
            continue
        ok, why = quality_ok(q)
        if not ok:
            rej[why] += 1
            continue
        rel = relevance(q)
        # 日期
        d = None
        if src == "xiaohongshu":
            for u in r.get("sources", []):
                if u in url2date and url2date[u]:
                    d = url2date[u]; break
        in_range = date_in_range(d)
        if in_range is False:
            rej["out_of_window"] += 1
            continue
        if rel == "other":
            rej["not_ai"] += 1
            continue
        out.append({
            "relevance": rel,
            "content": q,
            "category": cat,
            "type": "essay" if cat != "手撕算法" else "coding",
            "difficulty": guess_difficulty(cat, q),
            "tags": guess_tags(cat, q),
            "sources": r.get("sources", []),
            "platform": src,
            "date": (d.strftime("%Y-%m-%d") if d else ""),
            "date_in_range": in_range,
        })
    # 排序：AI 主线优先 -> 窗口内优先 -> 平台
    out.sort(key=lambda x: (x["relevance"] != "ai", x["date_in_range"] != True, x["platform"]))
    out_path = BASE / "data" / "tmp" / "_to_add.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    inwin = sum(1 for o in out if o["date_in_range"] is True)
    unknown = sum(1 for o in out if o["date_in_range"] == "unknown")
    ai = sum(1 for o in out if o["relevance"] == "ai")
    be = sum(1 for o in out if o["relevance"] == "backend")
    print("待入库清单：共 %d 题" % len(out))
    print("  AI/Agent 主线: %d | 传统后端八股: %d" % (ai, be))
    print("  窗口内(≤%d天): %d | 日期未知(知乎/掘金): %d" % (CUTOFF_DAYS, inwin, unknown))
    print("  按类别:", json.dumps(_catcount(out), ensure_ascii=False))
    print("  过滤统计:", json.dumps(rej, ensure_ascii=False))
    print("已写入", out_path)


def _catcount(out):
    from collections import Counter
    return dict(Counter(o["category"] for o in out))


if __name__ == "__main__":
    main()
