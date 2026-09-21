#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用后处理：对任意源的 posts.jsonl 抽取候选面试题 + 与题库去重。

用法：
    python process_source.py --source juejin
    # 或在 harvest.py 中 import process_source; process_source('juejin')

输出（data/tmp/<source>/）：
    candidates.jsonl   原始候选（按出现频次排序）
    shortlist.jsonl    去重后精选（与题库 0.72 相似即跳过 + 内部去重，按类别分组）
    refined.jsonl      与题库 0.85 严格去重后的干净新题（供模型挑题手写答案）
"""
import json
import re
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict, Counter
from difflib import SequenceMatcher

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
BANK = BASE / "data" / "questions-bank.json"

NOISE = re.compile(
    r"(发面经|攒人品|求offer|泪目|第一帖|开工|无实习|如何秋招|点赞|收藏|关注|插眼|"
    r"祝大家|大佬|蹲一个|同求|求捞|感谢|谢谢|加油|冲冲冲|码住|mark|顶|沙发|"
    r"浏览|参与|次浏览|人参与|全站热榜|创作者|正在热议|移动版|京ICP|反问|"
    r"几面|一面|二面|三面|hr面|面试官|时长|分钟|offer|流程如下|base|地点|"
    r"扫码|下载|客户端|登录|注册)"
)
LEAD = re.compile(r"(问|讲讲|讲一下|介绍|说说|说一下|如何|怎么|为什么|什么是|谈谈|解释|"
                  r"手撕|算法题|设计|实现|区别|原理|对比|了解|聊聊|描述|分析)")
# 拒绝代码行（技术帖里大量代码被误判为"题"）：赋值/函数/关键字/特殊符号
CODE = re.compile(r"[=<>{};]|//|/\*|\*/|def\s|class\s|import\s|return\s|function\s|=>|print\(|"
                  r"console\.|self\.|select\s|from\s|where\s|#include|std::|\bvoid\b|\bpublic\b|"
                  r"\bprivate\b|^\s*[a-zA-Z_]\w*\.\w+")
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
SIM = 0.72          # 内部 + 题库去重阈值
STRICT = 0.85       # refined 严格去重阈值
DROP = re.compile(
    r"^(八股|项目[一二三四]|项目，|追问|然后|接着|最后|首先|其次|另外|以及|还有|"
    r"这个|那个|就是|比如|例如|包括)|"
    r"(简历|自我介绍|你的项目|我的项目|上文|下文|如上|如下|见上|楼主|楼上|评论区|"
    r"私信|求捞|求内推|详见|不展开|略|待补充|未完|tbc)"
)
TAIL_BAD = re.compile(r"(的|了|和|与|或|及|把|被|让|如果|因为|所以|但是|而且|还有|以及)$")

# ---------- 近一月时间窗过滤 ----------
REL_RE = re.compile(r"(\d+)\s*(分钟|小时|天|周|个月|月)前")
ABS_YEAR_RE = re.compile(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})")
MD_RE = re.compile(r"(?<!\d)(\d{1,2})[-/月.](\d{1,2})(?!\d)")


def parse_post_date(s):
    """尽力解析帖子发布时间；返回 datetime 或 None（解析不出=无法判断，保守保留）。"""
    if not s:
        return None
    s = s.strip()
    m = ABS_YEAR_RE.search(s)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if "今天" in s or "刚刚" in s or "小时前" in s or "分钟前" in s:
        return datetime.now()
    if "昨天" in s:
        return datetime.now() - timedelta(days=1)
    if "前天" in s:
        return datetime.now() - timedelta(days=2)
    rm = REL_RE.search(s)
    if rm:
        n = int(rm.group(1)); u = rm.group(2)
        if u in ("分钟", "小时"):
            return datetime.now()
        if u == "天":
            return datetime.now() - timedelta(days=n)
        if u == "周":
            return datetime.now() - timedelta(days=n * 7)
        if u in ("月", "个月"):
            return datetime.now() - timedelta(days=n * 30)
    m = MD_RE.search(s)
    if m:
        return datetime(datetime.now().year, int(m.group(1)), int(m.group(2)))
    return None


def within_window(post, cutoff):
    """近一月判定：有可解析日期且早于 cutoff 才丢弃；无日期（搜索新鲜）保守保留。"""
    ds = (post.get("date") or "").strip()
    dp = parse_post_date(ds)
    if dp is not None and dp < cutoff:
        return False
    return True


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
    if len(s) < 5 or len(s) > 70:
        return False
    if NOISE.search(s) or CODE.search(s):
        return False
    if "?" in s or "？" in s:
        return True
    # LEAD 命中但需带疑问语气词，避免把代码注释/标题当题
    if LEAD.search(s) and re.search(
            r"(吗|怎么|为什么|如何|什么|哪些|几|是不是|能否|区别|对比|原理|步骤|方式|优劣|场景|方案)", s):
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


def process(source, days=30):
    posts_path = BASE / "data" / "tmp" / source / "posts.jsonl"
    out_dir = posts_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    cand_path = out_dir / "candidates.jsonl"
    short_path = out_dir / "shortlist.jsonl"
    refined_path = out_dir / "refined.jsonl"

    posts = [json.loads(l) for l in open(posts_path, encoding="utf-8") if l.strip()]
    # 微信源：混有官方噪声号（微信公众平台）与《投诉指引》等，过滤掉再处理
    if source == "weixin":
        before = len(posts)
        posts = [p for p in posts
                 if (p.get("account") or "") != "微信公众平台"
                 and "投诉指引" not in (p.get("title") or "")
                 and "名誉保护" not in (p.get("title") or "")]
        print("  [weixin] 过滤非面经账号/噪声 %d 篇" % (before - len(posts)))
    print("[%s] posts(raw): %d" % (source, len(posts)))

    # ---- 近一月时间窗过滤 ----
    cutoff = datetime.now() - timedelta(days=days)
    kept_posts, dropped, no_date = [], 0, 0
    for p in posts:
        if not within_window(p, cutoff):
            dropped += 1
            continue
        if not (p.get("date") or "").strip():
            no_date += 1
        kept_posts.append(p)
    print("  [时间窗 ≤%d天] 丢弃 %d 篇(超窗)，保留 %d 篇（其中 %d 篇无日期字段，按搜索新鲜保留）"
          % (days, dropped, len(kept_posts), no_date))
    posts = kept_posts

    # ---- extract ----
    cand = {}
    for p in posts:
        blob = (p.get("title", "") + "\n" + (p.get("text") or p.get("content") or ""))
        for q in split_candidates(blob):
            key = norm(q)
            if len(key) < 4:
                continue
            if key in cand:
                cand[key]["srcs"].add(p.get("url", ""))
                continue
            cand[key] = {"q": q, "category": categorize(q), "srcs": {p.get("url", "")}}
    rows = [{"question": v["q"], "category": v["category"],
             "sources": list(v["srcs"])[:3], "src_count": len(v["srcs"])}
            for v in cand.values()]
    rows.sort(key=lambda r: r["src_count"], reverse=True)
    with open(cand_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("  candidates: %d" % len(rows))

    # ---- curate (0.72 vs bank + 内部去重) -> shortlist ----
    bank = json.load(open(BANK, encoding="utf-8"))
    bank_keys = [norm(bank_text(it)) for it in bank.get("items", []) if bank_text(it)]
    kept, kept_norms = [], []
    for c in rows:
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
            continue
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
    with open(short_path, "w", encoding="utf-8") as f:
        for cat in bycat:
            for r in bycat[cat]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("  shortlist: %d (去重掉 %d)" % (len(kept), len(rows) - len(kept)))

    # ---- refine (0.85 严格 vs bank) -> refined（供挑题）----
    refined = []
    for c in rows:
        q = c["question"].strip()
        q = re.sub(r"^(项目[一二三四五]|八股|追问)[，,、\s]+", "", q).strip()
        if len(q) < 6:
            continue
        nq = norm(q)
        if any(similar(nq, bk) >= STRICT for bk in bank_keys):
            continue
        refined.append({"question": q, "category": c["category"],
                        "sources": c["sources"], "src_count": c["src_count"]})
    # 内部 0.85 去重
    rn, final = [], []
    for r in sorted(refined, key=lambda x: x["src_count"], reverse=True):
        nr = norm(r["question"])
        if any(similar(nr, x) >= STRICT for x in rn):
            continue
        rn.append(nr)
        final.append(r)
    with open(refined_path, "w", encoding="utf-8") as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("  refined (0.85 严格新题): %d" % len(final))
    print("  by category:", dict(Counter(r["category"] for r in final)))
    return len(final)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--days", type=int, default=30, help="近 N 天时间窗（默认 30）")
    args = ap.parse_args()
    process(args.source, days=args.days)
