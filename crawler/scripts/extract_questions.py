#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从牛客面经正文(posts.jsonl)抽取候选面试题，归一化+初步分类，输出候选清单。
输出: data/tmp/nowcoder/candidates.jsonl
"""
import json
import re
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent
POSTS = HERE.parent / "data" / "tmp" / "nowcoder" / "posts.jsonl"
OUT = HERE.parent / "data" / "tmp" / "nowcoder" / "candidates.jsonl"

# 噪声/无关行过滤
NOISE = re.compile(
    r"(发面经|攒人品|求offer|泪目|第一帖|开工|无实习|如何秋招|点赞|收藏|关注|插眼|"
    r"祝大家|大佬|蹲一个|同求|求捞|感谢|谢谢|加油|冲冲冲|码住|mark|顶|沙发|"
    r"浏览|参与|次浏览|人参与|全站热榜|创作者|正在热议|移动版|京ICP|反问|薪资|"
    r"几面|一面|二面|三面|hr面|面试官|时长|分钟|offer|流程如下|base|地点)"
)

# 明显是题目的引导词
LEAD = re.compile(r"(问|讲讲|讲一下|介绍|说说|说一下|如何|怎么|为什么|什么是|谈谈|解释|"
                  r"手撕|算法题|设计|实现|区别|原理|对比|了解|聊聊|描述|分析)")

# 分类关键词
CAT_RULES = [
    ("手撕算法", r"手撕|力扣|leetcode|算法题|反转|链表|二叉树|动态规划|dp|排序|"
                r"两数之和|最长|滑动窗口|回溯|二分|合并.*数组|字符串|数组|栈|队列|哈希"),
    ("后端八股（Go）", r"\bgo\b|golang|goroutine|gmp|channel|gc\b|context|sync\.|"
                    r"内存逃逸|协程|defer|mutex|map\b|切片|slice|垃圾回收|调度"),
    ("架构设计", r"架构|设计模式|高并发|分布式|微服务|负载均衡|限流|熔断|降级|"
              r"编排|多agent|multi.?agent|系统设计|扩展性|可用性|一致性"),
    ("工程落地", r"部署|落地|工程|监控|可观测|日志|流式|streaming|性能|优化|"
              r"缓存|服务化|超时|重试|并发|吞吐|延迟|token|成本"),
    ("概念基础", r"rag|检索增强|向量|embedding|向量库|大模型|llm|transformer|attention|"
              r"function.?call|工具调用|prompt|提示词|微调|fine.?tun|幻觉|"
              r"上下文|记忆|memory|agent|智能体|规划|反思|react|cot|思维链|"
              r"mcp|a2a|协议|多模态|推理|评估|评测"),
    ("项目深挖", r"项目|简历|你做过|贡献|难点|亮点|挑战|收益|指标|效果|落地效果"),
]


def clean(s):
    s = s.strip()
    s = re.sub(r"^[\d\.、\)）\(（\s\-—>》•·*#]+", "", s)  # 去前导序号/符号
    s = re.sub(r"[\s]+", " ", s)
    s = s.strip(" ：:，,。.；;")
    return s


def categorize(q):
    ql = q.lower()
    for cat, pat in CAT_RULES:
        if re.search(pat, ql):
            return cat
    return "概念基础"


def looks_like_question(s):
    if len(s) < 5 or len(s) > 80:
        return False
    if NOISE.search(s):
        return False
    # 含问号，或以引导词开头/含引导词，或是明确技术名词短语
    if "?" in s or "？" in s:
        return True
    if LEAD.search(s):
        return True
    return False


def split_candidates(text):
    out = []
    # 1) 按编号切分： 1. xxx 2. xxx
    numbered = re.split(r"(?:(?<=\D)|^)\s*\d{1,2}[\.、\)）]\s*", text)
    for seg in numbered:
        seg = seg.strip()
        if not seg:
            continue
        # 进一步按问号/换行切
        for part in re.split(r"[？?\n]", seg):
            c = clean(part)
            if looks_like_question(c):
                out.append(c)
    # 2) 直接按标点切，兜底
    for part in re.split(r"[；;。\n]", text):
        c = clean(part)
        if looks_like_question(c):
            out.append(c)
    return out


def main():
    posts = [json.loads(l) for l in open(POSTS, encoding="utf-8")]
    cand = {}
    for p in posts:
        blob = (p.get("title", "") + "\n" + p.get("text", ""))
        for q in split_candidates(blob):
            key = re.sub(r"[\s\W]+", "", q.lower())
            if len(key) < 4:
                continue
            if key in cand:
                cand[key]["srcs"].add(p["url"])
                continue
            cand[key] = {
                "q": q,
                "category": categorize(q),
                "srcs": {p["url"]},
            }
    rows = []
    for v in cand.values():
        rows.append({
            "question": v["q"],
            "category": v["category"],
            "sources": list(v["srcs"])[:3],
            "src_count": len(v["srcs"]),
        })
    # 高频优先
    rows.sort(key=lambda r: r["src_count"], reverse=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    c = Counter(r["category"] for r in rows)
    print(f"candidates: {len(rows)}")
    print("by category:", dict(c))
    print("--- top 25 by frequency ---")
    for r in rows[:25]:
        print(f"  [{r['src_count']}] ({r['category']}) {r['question']}")


if __name__ == "__main__":
    main()
