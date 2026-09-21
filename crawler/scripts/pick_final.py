#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 _curated_A / _curated_B 产出最终待写答案清单 _final_pick.jsonl

A 档：小红书近 35 天，再清一遍目录标题/感慨句
B 档：知乎/掘金，打分排序取 top N（默认 130）
"""
import json
import re
import sys
from pathlib import Path
from difflib import SequenceMatcher
from collections import Counter

BASE = Path(__file__).resolve().parent.parent
TMP = BASE / "data" / "tmp"
TOPN = int(sys.argv[1]) if len(sys.argv) > 1 else 130

# ---------- 硬拒绝 ----------
HARD_DROP = [
    # 营销 / 课程 / 引流
    r"花\s*\d+\s*[万千]|买.{0,4}课|踩过坑|替你|别踩|干货|收藏|点赞|关注我|公众号|星球|群里",
    r"实战项目|简历里|写进简历|保姆|手把手|从0到1|从零到一|带你|一文|系列|教程|专栏",
    # 前端 / 无关技术栈
    r"\bvue\b|\btoRefs?\b|\breactive\b|\bref\b\s*和|elementui|axios|webpack|css|html",
    r"spring\s*boot|springai|spring\s*ai|mybatis|\bjvm\b调优",
    # 叙述句 / 第二人称建议
    r"^(比如|例如|其|这条|这个路径|一句话|总结[:：]|另外|同时|因此|所以|而且|不过|但是)",
    r"你现在能|你可以说|你可以直接|我替你|建议你|不妨|记得|一定要",
    r"^(实现|封装|使用|采用|通过|基于|利用)[^?？]{0,60}$",
    # 职业规划 / 行业闲聊
    r"值不值得|要不要转|好找工作|薪资|涨薪|跳槽|前景如何|押注|风口",
    # 面试流程叙述
    r"问题\s*\d+[:：]|请描述你在|你在团队中的角色|完成了哪些关键工作",
    # 新闻资讯
    r"\d+年\d+月\d+日|发布了|上线了|开源了.{0,20}平台",
    # 残缺
    r"^.{0,8}$",
]
HARD_RE = [re.compile(p, re.I) for p in HARD_DROP]

# ---------- 问句判定 ----------
Q_MARK = re.compile(r"[?？]\s*$")
Q_WORD = re.compile(
    r"如何|怎么|怎样|为什么|为何|是什么|什么是|哪些|区别|对比|差异|异同|"
    r"原理|机制|流程|步骤|优缺点|优劣|讲讲|谈谈|简述|说说|介绍一下|描述一下|"
    r"解释|分析|设计|实现|优化|解决|处理|避免|权衡|选择|评估|定位|排查",
    re.I,
)

# ---------- 打分词表 ----------
CORE = re.compile(
    r"agent|智能体|多智能体|multi.?agent|工具调用|function\s*call|tool\s*call|"
    r"\bmcp\b|\ba2a\b|langchain|langgraph|autogen|crewai|"
    r"\breact\s*(框架|模式|范式|循环)?\b|plan.?and.?solve|reflexion|"
    r"记忆|memory|规划|planning|反思|轨迹|trajectory|"
    r"\brag\b|检索增强|召回|rerank|重排|向量库|知识库|切分|chunk|幻觉|"
    r"提示词|prompt|思维链|\bcot\b|上下文工程|context",
    re.I,
)
MODEL = re.compile(
    r"transformer|attention|注意力|\brope\b|位置编码|\bgqa\b|\bmqa\b|\bmla\b|\bmoe\b|"
    r"\bkv\s*cache\b|vllm|sglang|推理加速|量化|蒸馏|长上下文|外推|"
    r"softmax|layernorm|归一化|激活函数|\bbert\b|\bgpt\b|解码|采样|温度|top.?[pk]",
    re.I,
)
TRAIN = re.compile(
    r"\bsft\b|\blora\b|\bqlora\b|\bdpo\b|\bppo\b|\bgrpo\b|\brlhf\b|微调|"
    r"奖励模型|reward|强化学习|对齐|预训练|数据构造|数据配比|灾难性遗忘|过拟合|"
    r"loss|梯度|学习率|batch|评测|benchmark|llm\s*as\s*judge",
    re.I,
)
ENG = re.compile(
    r"并发|限流|重试|熔断|降级|超时|缓存|幂等|流式|sse|websocket|监控|可观测|"
    r"链路|trace|成本|token\s*(消耗|预算|超|限)|延迟|吞吐|部署|容器|灰度|回滚|"
    r"沙箱|安全|注入|越狱|权限|审计",
    re.I,
)


def clean(s):
    s = s.strip()
    s = re.sub(r"^[▪▫️•·\-—*>》\s\U0001F300-\U0001FAFF]+", "", s)
    s = re.sub(r"^Q\d*\s*[.:：]\s*", "", s)
    s = re.sub(r"^\d+\s*[.、)）]\s*", "", s)
    s = re.sub(r"^[a-zA-Z]\s*[.、)）]\s*", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def hard_dropped(s):
    return any(r.search(s) for r in HARD_RE)


def is_question(s):
    return bool(Q_MARK.search(s) or Q_WORD.search(s))


def is_catalog(s):
    """目录标题式：多个顿号枚举且无疑问词"""
    if s.count("、") >= 3 and not Q_MARK.search(s):
        return True
    if re.search(r"等[。\.]?$", s) and not Q_MARK.search(s):
        return True
    if re.match(r"^[\w\u4e00-\u9fff]{2,10}[:：]", s) and not is_question(s):
        return True
    return False


def score(s):
    sc = 0
    if CORE.search(s):
        sc += 4
    if MODEL.search(s):
        sc += 3
    if TRAIN.search(s):
        sc += 3
    if ENG.search(s):
        sc += 2
    if Q_MARK.search(s):
        sc += 2
    if Q_WORD.search(s):
        sc += 2
    n = len(s)
    if 14 <= n <= 45:
        sc += 2
    elif n <= 60:
        sc += 1
    # 多信号叠加加分（跨领域综合题更像真面试题）
    hits = sum(bool(r.search(s)) for r in (CORE, MODEL, TRAIN, ENG))
    if hits >= 2:
        sc += 2
    return sc


def dedup(rows, thr=0.80):
    out, norms = [], []
    for r in rows:
        n = re.sub(r"[^\w\u4e00-\u9fff]", "", r["content"].lower())
        if any(SequenceMatcher(None, n, x).ratio() >= thr for x in norms):
            continue
        norms.append(n)
        out.append(r)
    return out


def load(name):
    p = TMP / f"_curated_{name}.jsonl"
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    # ---- A 档 ----
    A = []
    for r in load("A"):
        c = clean(r["content"])
        if len(c) < 12 or len(c) > 70:
            continue
        if hard_dropped(c) or is_catalog(c):
            continue
        if not is_question(c):
            continue
        r["content"] = c
        r["_score"] = score(c)
        r["_tier"] = "A"
        A.append(r)
    A = dedup(A)

    # ---- B 档 ----
    Bc = []
    for r in load("B"):
        c = clean(r["content"])
        if len(c) < 12 or len(c) > 70:
            continue
        if hard_dropped(c) or is_catalog(c):
            continue
        if not is_question(c):
            continue
        sc = score(c)
        if sc < 9:          # B 档门槛更高
            continue
        r["content"] = c
        r["_score"] = sc
        r["_tier"] = "B"
        Bc.append(r)
    Bc.sort(key=lambda x: -x["_score"])
    Bc = dedup(Bc)

    # B 与 A 交叉去重
    a_norms = [re.sub(r"[^\w\u4e00-\u9fff]", "", x["content"].lower()) for x in A]
    B = []
    for r in Bc:
        n = re.sub(r"[^\w\u4e00-\u9fff]", "", r["content"].lower())
        if any(SequenceMatcher(None, n, x).ratio() >= 0.80 for x in a_norms):
            continue
        B.append(r)
        if len(B) >= TOPN:
            break

    final = A + B
    p = TMP / "_final_pick.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for d in final:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print("A 档保留:", len(A))
    print("B 档精选:", len(B), " (候选池", len(Bc), ")")
    print("最终清单:", len(final), "→", p)
    print("按类别:", dict(Counter(x["category"] for x in final)))
    print("按平台:", dict(Counter(x["platform"] for x in final)))


if __name__ == "__main__":
    main()
