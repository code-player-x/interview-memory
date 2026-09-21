#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""只读扫描：找题库里「同根但对比点不同」的对比类条目。

「同根」判定 = 两道对比类题目共享显著技术名词（文档频率低 = 区分度高）。
用并查集把共享术语的题目连成候选分组，输出分组规模与成员。

全程只读，不改任何数据。
用法：python scripts/scan_same_root.py [--min-terms 2] [--df-max 60] [--top 40]
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
BANK = PROJ / "data" / "questions-bank.json"

# 对比类题目的判定：明确在比较两个及以上事物 / 做选型取舍
CMP_PAT = re.compile(
    r"(区别|差别|差异|有什么不同|对比|相比|而不用|而不是|优先选|"
    r"为什么.{0,12}(使用|用|选择).{0,10}(不是|而不用)|"
    r"\bvs\b|\bVS\b|哪个好|如何选|为什么要|为什么不|"
    r"与.{1,20}的|和.{1,20}(相比|比))"
)

STOP_TERMS = {
    "mysql", "redis", "http", "https", "tcp", "udp", "sql", "innodb", "myisam",
    "kafka", "docker", "kubernetes", "k8s", "linux", "gin", "gorm", "etcd", "rpc",
    "grpc", "jwt", "oauth", "cpu", "io", "api", "sdk", "qa", "qa", "mq", "lsm",
    "b树", "b+树", "哈希表", "红黑树", "跳表", "二叉树", "avl树", "二叉搜索树",
    "mvcc", "acid", "cap", "raft", "mongo", "mongodb", "nginx", "https",
}


def load():
    with open(BANK, encoding="utf-8") as f:
        return json.load(f)


def extract_terms(text: str) -> set:
    t = text or ""
    terms = set()
    # ASCII 技术词（含 + # . 的变体，如 B+树 / .NET / C++）
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9+#._]{1,15}", t):
        w = m.group(0).strip(".")
        if len(w) >= 2:
            terms.add(w.lower())
    # 中文技术词（ curated 关键概念）
    zh = [
        "索引", "事务", "隔离级别", "锁", "死锁", "间隙锁", "行锁", "表锁", "乐观锁", "悲观锁",
        "mvcc", "日志", "redolog", "undolog", "binlog", "主从复制", "分库分表", "回表",
        "覆盖索引", "聚簇索引", "缓存穿透", "缓存击穿", "缓存雪崩", "淘汰策略", "持久化",
        "协程", "goroutine", "进程", "线程", "调度", "内存逃逸", "垃圾回收", "gc",
        "channel", "mutex", "rwmutex", "原子操作", "上下文", "defer", "panic", "接口",
        "结构体", "切片", "映射", "反射", "泛型", "指针", "值传递", "引用传递",
        "一致性哈希", "负载均衡", "限流", "熔断", "降级", "幂等", "分布式锁", "分布式事务",
        "消息队列", "消息丢失", "重复消费", "顺序消费", "堆积", "topic", "分区", "副本",
        "向量", "embedding", "rag", "agent", "llm", "prompt", "fine-tuning", "微调",
        "注意力", "transformer", "意图识别", "知识库", "召回", "重排", "幻觉",
        "监控", "链路追踪", "日志采集", "灰度发布", "滚动更新", "服务发现", "注册中心",
    ]
    low = t.lower()
    for z in zh:
        if z in low:
            terms.add(z)
    return terms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-terms", type=int, default=2, help="两题共享多少个术语即视为同根")
    ap.add_argument("--df-max", type=int, default=60, help="术语文档频率上限，超过则视为过于宽泛")
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()

    data = load()
    items = data["items"]
    print(f"题库总数 {len(items)}\n")

    # 1) 筛出对比类条目
    cmp_items = [it for it in items if CMP_PAT.search(it.get("content", "") or "")]
    print(f"[筛选] 对比类条目 {len(cmp_items)} 条\n")

    # 2) 术语文档频率
    term_df = defaultdict(int)
    terms_per = {}
    for it in cmp_items:
        terms = extract_terms(it.get("content", ""))
        terms_per[it["id"]] = terms
        for t in terms:
            term_df[t] += 1

    # 3) 只对区分度高的术语建边
    useful = {t for t, c in term_df.items() if c <= args.df_max}
    inv = defaultdict(list)
    for qid, terms in terms_per.items():
        for t in terms & useful:
            inv[t].append(qid)

    parent = {q["id"]: q["id"] for q in cmp_items}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    pair_terms = defaultdict(set)
    for t, qids in inv.items():
        for i in range(len(qids)):
            for j in range(i + 1, len(qids)):
                pair_terms[(qids[i], qids[j])].add(t)
    for (a, b), ts in pair_terms.items():
        if len(ts) >= args.min_terms:
            union(a, b)

    comp = defaultdict(list)
    for q in cmp_items:
        comp[find(q["id"])].append(q)

    groups = sorted(comp.values(), key=len, reverse=True)
    multi = [g for g in groups if len(g) > 1]
    print(f"[分组] 候选同根分组 {len(multi)} 组（成员>1），涉及题目 {sum(len(g) for g in multi)} 条\n")

    by_id = {it["id"]: it for it in items}
    for gi, g in enumerate(multi[:args.top], 1):
        # 组内共享术语
        shared = set(terms_per[g[0]["id"]])
        for q in g[1:]:
            shared &= terms_per[q["id"]]
        shared_txt = ", ".join(sorted(s for s in shared if s in useful)[:6])
        cats = defaultdict(int)
        for q in g:
            cats[q.get("category", "")] += 1
        print(f"── 组 {gi}（{len(g)} 条）  共享词根: {shared_txt or '—'}   分类: {dict(cats)}")
        for q in sorted(g, key=lambda x: x["id"]):
            toks = sorted((terms_per[q['id']] & useful))
            print(f"   [{q['id']}] {q.get('content','')[:66]}")
            print(f"        术语: {', '.join(toks[:8])}")
        print()

    print(f"[说明] 以上是只读扫描结果。参数: min_terms={args.min_terms} df_max={args.df_max}")
    print("       调整 --min-terms 变小会得到更多（更激进的）分组。")


if __name__ == "__main__":
    main()
