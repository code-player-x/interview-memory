#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对 _to_add.jsonl 做第二档收紧，产出可入库的精选清单。

分层：
  A 档 = 小红书近 35 天（date_in_range=True）  -> 时间窗可保证，优先入库
  B 档 = 知乎/掘金（date 未知）                -> 需强 Agent 信号才留

输出 data/tmp/_curated_A.jsonl / _curated_B.jsonl
"""
import json
import re
from pathlib import Path
from difflib import SequenceMatcher

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "data" / "tmp" / "_to_add.jsonl"

# 广告 / 求赞 / 反问面试官 / 叙述句 —— 一律剔除
DROP = [
    r"找不到方向|虐哭|免费领|私聊|扣1|抽奖|资料包|课程|训练营|带你|保姆级|一文",
    r"^[▪▫️•·]\s*团队|团队.*(规划|方向|措施|氛围|构成)[?？]?$",  # 反问面试官
    r"(贵司|咱们团队|这个岗位).*[?？]",
    r"^(我|你|他|她|它|我们|大家|笔者|作者)[^?？]{0,40}$",         # 纯叙述
    r"^涵盖|^包含|^分为|^主要是|^就像|^全部记下来",
    r"[。！!]$",                                                   # 陈述句结尾
    r"^\s*Q\d*[.:：]?\s*$",
]
DROP_RE = [re.compile(p, re.I) for p in DROP]

# 强 AI/Agent 信号（B 档门槛）
STRONG = re.compile(
    r"agent|智能体|\bllm\b|大模型|\brag\b|langchain|langgraph|\bmcp\b|\ba2a\b|"
    r"function\s*call|tool\s*call|工具调用|react|plan.?and.?solve|reflexion|"
    r"提示词|prompt|思维链|\bcot\b|微调|\bsft\b|\blora\b|\bdpo\b|\bppo\b|\brlhf\b|"
    r"embedding|向量库|检索增强|召回|rerank|重排|知识库|幻觉|对齐|"
    r"多智能体|multi.?agent|长短期记忆|上下文窗口|\bkv\s*cache\b|\bmoe\b|"
    r"注意力|attention|transformer|\brope\b|\bgqa\b|\bmla\b|vllm|sglang|"
    r"奖励模型|reward|强化学习|蒸馏|量化|评测|llm\s*as\s*judge",
    re.I,
)

# 弱 AI 信号（A 档门槛，因为 A 档已有时间窗+面经语境兜底）
WEAK = re.compile(r"agent|智能体|大模型|\bllm\b|\brag\b|模型|向量|检索|prompt|记忆|工具|微调|token", re.I)


def clean(s):
    s = s.strip()
    s = re.sub(r"^[▪▫️•·\-—*>》\s]+", "", s)
    s = re.sub(r"^Q\d*\s*[.:：]\s*", "", s)
    s = re.sub(r"^[a-zA-Z]\s*[.、)]\s*", "", s)
    s = re.sub(r"^\d+\s*[.、)]\s*", "", s)
    return s.strip()


def dropped(s):
    return any(r.search(s) for r in DROP_RE)


def dedup(rows, thr=0.82):
    out, norms = [], []
    for r in rows:
        n = re.sub(r"[^\w\u4e00-\u9fff]", "", r["content"].lower())
        if any(SequenceMatcher(None, n, x).ratio() >= thr for x in norms):
            continue
        norms.append(n)
        out.append(r)
    return out


def main():
    rows = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]
    A, B = [], []
    for r in rows:
        c = clean(r["content"])
        if len(c) < 10 or len(c) > 75:
            continue
        if dropped(c):
            continue
        r["content"] = c
        if r["date_in_range"] is True:
            if WEAK.search(c):
                A.append(r)
        else:
            if STRONG.search(c):
                B.append(r)
    A = dedup(A)
    B = dedup(B)
    for name, data in (("A", A), ("B", B)):
        p = BASE / "data" / "tmp" / f"_curated_{name}.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for d in data:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
    from collections import Counter
    print("A 档（小红书近35天）:", len(A), dict(Counter(x["category"] for x in A)))
    print("B 档（知乎/掘金，强AI信号）:", len(B), dict(Counter(x["category"] for x in B)))
    print("合计可入库候选:", len(A) + len(B))


if __name__ == "__main__":
    main()
