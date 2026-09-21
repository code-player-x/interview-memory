#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""只读扫描：按「比较主体对」识别同根条目。

「同根」= 比较的是同一组主体（如都是 Agent vs LLM），但对比角度/要点不同。
做法：从对比类题面抽取出参与比较的技术实体集合，
      - 实体集合完全相同 → 【确定同根】候选合并组
      - 只共享部分主体（如同以 Agent 为主角但对比对手不同）→ 【边界模糊】，单列不合并

全程只读。
用法：python scripts/scan_same_root_pairs.py [--top 30]
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
BANK = PROJ / "data" / "questions-bank.json"

# 对比类判定
CMP_PAT = re.compile(
    r"(区别|差别|差异|有什么不同|不同之处|对比|相比|而不用|而不是|而非|"
    r"优先选|还是用|如何选择|选哪个|哪个好|"
    r"\bvs\b|\bVS\b|各有(什么)?(优缺|优劣)|优劣|"
    r"为什么.{0,14}(使用|用|选|选择)|为什么不)"
)

# 技术实体词典：canonical -> 正则别名
ENTITIES = {
    "agent":        r"(?<!\w)agent(?!\w)|ag[eé]ntic|ai\s*agent|智能体",
    "llm":          r"(?<!\w)llm(?!\w)|大模型|语言模型",
    "rag":          r"(?<!\w)rag(?!\w)|检索增强",
    "微调":          r"微调|fine[\s\-]?tun|(?<!\w)sft(?!\w)",
    "mcp":          r"(?<!\w)mcp(?!\w)",
    "function calling": r"function\s*call(ing)?|函数调用|工具调用",
    "skill":        r"skills?|skills",
    "langchain":    r"langchain",
    "langgraph":    r"langgraph",
    "autogpt":      r"autogpt",
    "crewai":       r"crewai",
    "autogen":      r"autogen",
    "llamaindex":   r"llamaindex",
    "react":        r"(?<!\w)react(?!\w)|reason\s*\+\s*act",
    "codeact":      r"codeact",
    "workflow":     r"workflow|工作流",
    "multi-agent":  r"multi[\s\-]?agent|多智能体|多个\s*agent",
    "single-agent": r"single[\s\-]?agent|单智能体",
    "a2a":          r"(?<!\w)a2a(?!\w)",
    "prompt":       r"prompt|提示词",
    "a2a-ignore":   r"^$",

    "mysql":        r"mysql",
    "innodb":       r"innodb",
    "myisam":       r"myisam",
    "redis":        r"redis",
    "memcached":    r"memcached",
    "mongodb":      r"mongo(db)?",
    "postgresql":   r"postgres(ql)?|(?<!\w)pg(?!\w)",
    "elasticsearch": r"elasticsearch|(?<!\w)es(?!\w)",
    "clickhouse":   r"clickhouse",
    "hbase":        r"hbase",
    "leveldb":      r"leveldb",
    "rocksdb":      r"rocksdb",

    "b+树":         r"b\s*\+\s*树|b\+tree",
    "b树":          r"(?<![+\w])b\s*树(?![+\w])|(?<!\w)btree(?!\w)",
    "b*树":         r"b\*\s*树",
    "红黑树":        r"红黑树|red[\s\-]?black",
    "avl树":        r"avl",
    "哈希表":        r"哈希(表|索引)|hash\s*(表|索引)|hashtable",
    "跳表":          r"跳表|skiplist|skip\s*list",
    "二叉树":        r"二叉树|binary\s*tree",
    "lsm":          r"lsm[\s\-]?tree|lsm",
    "聚簇索引":       r"聚簇索引|聚集索引|簇索引",
    "二级索引":       r"二级索引|辅助索引|非聚簇索引|普通索引",
    "覆盖索引":       r"覆盖索引",
    "联合索引":       r"联合索引|复合索引|组合索引",
    "唯一索引":       r"唯一索引",
    "前缀索引":       r"前缀索引",

    "tcp":          r"(?<!\w)tcp(?!\w)",
    "udp":          r"(?<!\w)udp(?!\w)",
    "http":         r"(?<!\w)http(?!\w)",
    "https":        r"(?<!\w)https(?!\w)",
    "http1.1":      r"http\s*/?\s*1\.1|http1",
    "http2":        r"http\s*/?\s*2(?!\w)|http2",
    "http3":        r"http\s*/?\s*3(?!\w)|http3",
    "websocket":    r"websocket",
    "grpc":         r"grpc",
    "rpc":          r"(?<!\w)rpc(?!\w)",

    "进程":         r"进程",
    "线程":         r"线程",
    "协程":         r"协程",
    "goroutine":    r"goroutine",
    "channel":      r"channel",
    "mutex":        r"mutex|互斥锁",
    "rwmutex":      r"rwmutex|读写锁",
    "atomic":       r"atomic|原子操作",
    "乐观锁":        r"乐观锁",
    "悲观锁":        r"悲观锁",
    "死锁":         r"死锁",
    "gc":           r"垃圾回收|(?<!\w)gc(?!\w)",
    "内存逃逸":      r"逃逸分析|内存逃逸|逃逸",
    "defer":        r"(?<!\w)defer(?!\w)",
    "panic":        r"panic",
    "接口":         r"接口|interface",
    "反射":         r"反射|reflect",
    "泛型":         r"泛型|generic",
    "上下文":        r"context|上下文",

    "分布式锁":      r"分布式锁",
    "分布式事务":    r"分布式事务",
    "cap":          r"(?<!\w)cap(?!\w)|cap定理",
    "raft":         r"raft",
    "paxos":        r"paxos",
    "2pc":          r"2pc|两阶段提交|二阶段提交",
    "3pc":          r"3pc|三阶段提交",
    "tcc":          r"tcc",
    "saga":         r"saga",
    "消息队列":      r"消息队列|(?<!\w)mq(?!\w)|message\s*queue",
    "kafka":        r"kafka",
    "rocketmq":     r"rocketmq",
    "rabbitmq":     r"rabbitmq",
    "token bucket": r"令牌桶",
    "漏桶":         r"漏桶",
    "限流":         r"限流",
    "熔断":         r"熔断",
    "降级":         r"降级",
    "幂等":         r"幂等",
    "负载均衡":      r"负载均衡|load\s*balance",
    "一致性哈希":    r"一致性哈希|consistent\s*hash",
    "服务发现":      r"服务发现",
    "注册中心":      r"注册中心",
    "灰度发布":      r"灰度|金丝雀",
    "回滚":         r"回滚",

    "docker":       r"docker|容器",
    "k8s":          r"k8s|kubernetes",
    "虚拟机":        r"虚拟机|(?<!\w)vm(?!\w)",
    "微服务":        r"微服务",
    "单体":         r"单体(架构)?|monolith",
    "soa":          r"(?<!\w)soa(?!\w)",

    "intent":       r"意图识别|intent",
    "embedding":    r"embedding|向量化|嵌入",
    "rerank":       r"rerank|重排",
    "幻觉":         r"幻觉|hallucination",
    "向量库":        r"向量(数据)?库|milvus",
    "fine_tune_ignore": r"^$",
}

# 别名归一：把不同写法映射到同一 canonical
ALIAS = {
    "reason_act": "react",
}


def detect_entities(text: str) -> set:
    t = (text or "").lower()
    found = set()
    for canon, pat in ENTITIES.items():
        if canon.endswith("_ignore"):
            continue
        if re.search(pat, t):
            found.add(canon)
    # 消歧：multi-agent / single-agent 出现时把它们映射回 agent 以避免重复计数
    if "multi-agent" in found or "single-agent" in found:
        found.discard("multi-agent")
        found.discard("single-agent")
        found.add("agent")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--max-ent", type=int, default=4,
                    help="实体数超过该值的题面当作综述题，不参与合并判断")
    args = ap.parse_args()

    data = json.loads(BANK.read_text(encoding="utf-8"))
    items = data["items"]

    cmp_items = [it for it in items if CMP_PAT.search(it.get("content", "") or "")]
    print(f"题库总数 {len(items)}")
    print(f"对比类条目 {len(cmp_items)} 条\n")

    ents = {}
    for it in cmp_items:
        ents[it["id"]] = detect_entities(it.get("content", ""))

    # 只保留参与比较的聚焦题（实体数适中）
    focused = {k: v for k, v in ents.items() if 1 < len(v) <= args.max_ent}
    broad = {k: v for k, v in ents.items() if len(v) > args.max_ent}
    print(f"聚焦对比题 {len(focused)} 条 / 综述型(实体>{args.max_ent}) {len(broad)} 条（后者不参与自动合并）\n")

    # ---- 确定同根：实体集合完全相同 ----
    exact = defaultdict(list)
    for qid, s in focused.items():
        exact[frozenset(s)].append(qid)
    groups = [sorted(v) for v in exact.values() if len(v) > 1]
    groups.sort(key=lambda g: (-len(g), g[0]))

    print(f"========== 【确定同根】候选合并组 {len(groups)} 组 ==========\n")
    for i, g in enumerate(groups[:args.top], 1):
        key = sorted(ents[g[0]])
        print(f"【组 {i}】主体对: {' × '.join(key)}   成员 {len(g)} 条")
        for qid in g:
            it = next(x for x in items if x["id"] == qid)
            print(f"   [{qid}] {it.get('content','')[:70]}")
        print()

    # ---- 边界模糊：共享主体但对比对手不同 ----
    print(f"\n========== 【边界模糊】共享主体但比较对象不同（不建议擅自合并）==========\n")
    subject_clusters = defaultdict(set)
    for qid, s in focused.items():
        for e in s:
            subject_clusters[e].add(qid)
    # 找出被多个「不同实体集合」共享的主体
    amb = []
    for ent, qids in subject_clusters.items():
        keyset = defaultdict(list)
        for q in qids:
            keyset[frozenset(ents[q])].append(q)
        if len(keyset) >= 3:  # 同一主体下有 3+ 种不同对比组合
            amb.append((ent, keyset))
    amb.sort(key=lambda x: -len(x[1]))
    for ent, keyset in amb[:12]:
        print(f"【主体: {ent}】下共有 {len(keyset)} 种不同对比组合:")
        for k, v in sorted(keyset.items(), key=lambda x: -len(x[1])):
            members = " × ".join(sorted(k))
            print(f"   - {members}  ({len(v)} 条) : {', '.join(sorted(v, key=lambda s:int(s[1:]))[:6])}")
        print()

    print("\n[说明] 只读扫描，未改动任何数据。")


if __name__ == "__main__":
    main()
