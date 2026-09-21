#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书采集后处理：抽取候选面试题 + 与现有题库去重，输出 candidates/shortlist。

输入：data/tmp/xiaohongshu/posts.jsonl（67 篇真实面经）
输出：data/tmp/xiaohongshu/candidates.jsonl（按频率排序）
      data/tmp/xiaohongshu/shortlist.jsonl（已与题库 68 题 + 内部去重）
"""
import json
import re
from pathlib import Path
from collections import defaultdict, Counter
from difflib import SequenceMatcher

HERE = Path(__file__).resolve().parent
POSTS = HERE.parent / "data" / "tmp" / "xiaohongshu" / "posts.jsonl"
CAND = HERE.parent / "data" / "tmp" / "xiaohongshu" / "candidates.jsonl"
SHORT = HERE.parent / "data" / "tmp" / "xiaohongshu" / "shortlist.jsonl"
BANK = HERE.parent / "data" / "questions-bank.json"

# ---- 通用抽取规则（同牛客，适用清单体面经）----
NOISE = re.compile(
    r"(发面经|攒人品|求offer|泪目|第一帖|开工|无实习|如何秋招|点赞|收藏|关注|插眼|"
    r"祝大家|大佬|蹲一个|同求|求捞|感谢|谢谢|加油|冲冲冲|码住|mark|顶|沙发|"
    r"浏览|参与|次浏览|人参与|全站热榜|创作者|正在热议|移动版|京ICP|反问|薪资|"
    r"几面|一面|二面|三面|hr面|面试官|时长|分钟|offer|流程如下|base|地点)"
)
LEAD = re.compile(r"(问|讲讲|讲一下|介绍|说说|说一下|如何|怎么|为什么|什么是|谈谈|解释|"
                  r"手撕|算法题|设计|实现|区别|原理|对比|了解|聊聊|描述|分析)")
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
SIM = 0.72
DROP = re.compile(
    r"^(八股|项目[一二三四]|项目，|追问|然后|接着|最后|首先|其次|另外|以及|还有|"
    r"这个|那个|就是|比如|例如|包括)|"
    r"(简历|自我介绍|你的项目|我的项目|上文|下文|如上|如下|见上|楼主|楼上|评论区|"
    r"私信|求捞|求内推|详见|不展开|略|待补充|未完|tbc)"
)
TAIL_BAD = re.compile(r"(的|了|和|与|或|及|把|被|让|如果|因为|所以|但是|而且|还有|以及)$")


def clean(s):
    s = s.strip()
    s = re.sub(r"^[\d\.、\)）\(（\s\-—>》•·*#]+", "", s)
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
    if "?" in s or "？" in s:
        return True
    if LEAD.search(s):
        return True
    return False


def split_candidates(text):
    out = []
    numbered = re.split(r"(?:(?<=\D)|^)\s*\d{1,2}[\.、\)）]\s*", text)
    for seg in numbered:
        seg = seg.strip()
        if not seg:
            continue
        for part in re.split(r"[？?\n]", seg):
            c = clean(part)
            if looks_like_question(c):
                out.append(c)
    for part in re.split(r"[；;。\n]", text):
        c = clean(part)
        if looks_like_question(c):
            out.append(c)
    return out


def norm(s):
    return re.sub(r"[\s\W]+", "", s.lower())


def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


def bank_text(it):
    return (it.get("content") or it.get("question") or "").strip()


def extract():
    posts = [json.loads(l) for l in open(POSTS, encoding="utf-8")]
    cand = {}
    for p in posts:
        blob = (p.get("title", "") + "\n" + p.get("text", ""))
        for q in split_candidates(blob):
            key = norm(q)
            if len(key) < 4:
                continue
            if key in cand:
                cand[key]["srcs"].add(p["url"])
                continue
            cand[key] = {"q": q, "category": categorize(q), "srcs": {p["url"]}}
    rows = []
    for v in cand.values():
        rows.append({"question": v["q"], "category": v["category"],
                     "sources": list(v["srcs"])[:3], "src_count": len(v["srcs"])})
    rows.sort(key=lambda r: r["src_count"], reverse=True)
    with open(CAND, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[extract] candidates: {len(rows)}")
    print("  by category:", dict(Counter(r["category"] for r in rows)))
    return rows


def curate():
    cands = [json.loads(l) for l in open(CAND, encoding="utf-8")]
    bank = json.load(open(BANK, encoding="utf-8"))
    bank_keys = [norm(bank_text(it)) for it in bank.get("items", []) if bank_text(it)]
    kept, kept_norms = [], []
    for c in cands:
        q = c["question"].strip()
        if DROP.search(q) or TAIL_BAD.search(q):
            continue
        q = re.sub(r"^(项目[一二三四五]|八股|追问)[，,、\s]+", "", q).strip()
        if len(q) < 6 or len(q) > 60:
            continue
        q = re.split(r"[？?]\s*\d+[\.、]", q)[0].strip().rstrip("？?")
        if len(q) < 6:
            continue
        nq = norm(q)
        if any(similar(nq, bk) >= SIM for bk in bank_keys):
            continue  # 与题库重复，跳过
        dup = False
        for i, kn in enumerate(kept_norms):
            if similar(nq, kn) >= SIM:
                if c["src_count"] > kept[i]["src_count"]:
                    kept[i] = {**c, "question": q}
                dup = True
                break
        if dup:
            continue
        kept.append({**c, "question": q})
        kept_norms.append(nq)
    bycat = defaultdict(list)
    for k in kept:
        bycat[k["category"]].append(k)
    for cat in bycat:
        bycat[cat].sort(key=lambda r: r["src_count"], reverse=True)
    with open(SHORT, "w", encoding="utf-8") as f:
        for cat in bycat:
            for r in bycat[cat]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[curate] shortlist total: {len(kept)} (去重掉 {len(cands)-len(kept)})")
    for cat, rows in sorted(bycat.items(), key=lambda x: -len(x[1])):
        print(f"\n### {cat} ({len(rows)})")
        for r in rows[:20]:
            print(f"  [{r['src_count']}] {r['question']}")


if __name__ == "__main__":
    extract()
    curate()
