#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""无 LLM 的启发式关键词提取：从答案原文抽取 3-6 个词写回 questions.keywords。

关键词必须是 reference_answer 的逐字子串（保证前端 <mark> 高亮命中）。
策略：jieba 分词 -> 过滤停用词/单字 -> 技术词表加权 -> 按 (频次, 词长, 技术权重) 排序取前 N。
仅处理 keywords 为空（或 --force 全量）的题，不会覆盖已有 LLM 结果（除非 --force）。

用法：
  .venv/Scripts/python scripts/extract_keywords_heuristic.py --dry-run
  .venv/Scripts/python scripts/extract_keywords_heuristic.py
  .venv/Scripts/python scripts/extract_keywords_heuristic.py --force
"""
import os
import re
import sqlite3
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "interview_memory.db")

STOPWORDS = set(
    "的 了 和 是 在 我 有 也 就 不 都 而 及 与 或 对 等 一个 一种 可以 我们 你 他 她 它 这 那 这些 那些 "
    "因为 所以 如果 但是 并且 以及 通过 对于 关于 进行 实现 使用 需要 就是 这样 那样 一些 没有 不是 这个 那个 "
    "主要 可能 比较 非常 一定 通常 一般 比如 例如 如下 之间 之后 之前 时候 情况 问题 方式 过程 作用 特点 优点 缺点 "
    "a an the of to in on for with and or but if then is are be can will from by as at this that these those "
    "it its we you they he she do does done has have had not no yes so because but when where what how which "
    "go golang 语言 代码 函数 方法 类型 系统 程序 数据 对象 概念 机制 原理 用户 业务 场景 内容 部分 其他 相关 "
    "term terms style styles short long kind kinds way ways example examples use uses using used based note notes "
    "type types name names value values result results state states step steps time times call calls code codes "
    "function functions class classes object objects field fields method methods property properties item items "
    "default standard common simple basic normal special normal different same each both all any many few much "
    "one two three first second third new old open close read write"
    .split()
)

# 英文停用词（额外，避免把 code style / short-term 里的 term/style 当关键词）
ENG_STOP = set(
    "term terms style styles short long kind kinds way ways example examples use uses using used based note notes "
    "type types name names value values result results state states step steps time times call calls code codes "
    "function functions class classes object objects field fields method methods property properties item items "
    "default standard common simple basic normal special different same each both all any many few much one two three "
    "first second third new old open close read write the a an and or but if then else for while of to in on at by "
    "with from as is are be can will do does has have had not no yes so because when where what how which it its we you "
    "they he she go golang lang api http tcp ip url json xml html css id ids key keys"
    .split()
)

# 技术词表（领域加权，命中则优先）：Go / 后端 / 大模型通用
TECH_TERMS = set(
    "goroutine channel 协程 并发 并行 GMP 调度 调度器 垃圾回收 GC 三色标记 混合写屏障 写屏障 逃逸 内存逃逸 "
    "slice 切片 map 哈希表 散列表 interface 接口 channel 通道 context 上下文 mutex 互斥锁 读写锁 锁 原子操作 "
    "原子 sync 同步 waitgroup once 内存 堆 栈 逃逸分析 指针 unsafe 反射 reflect 泛型 组合 嵌入 面向对象 封装 继承 多态 "
    "defer panic recover init 闭包 泛型 nil 零值 结构体 struct 方法 值类型 引用类型 线程安全 阻塞 非阻塞 select "
    "RWMutex 自旋 CAS channel 缓冲 无缓冲 有缓冲 超时 截止时间 优雅退出 连接池 协程池 ants 性能优化 压测 调优 "
    "RAG 微调 预训练 对齐 提示工程 大模型 推理 部署 向量  embedding 注意力 多头 自注意力 transformer token "
    "agent 智能体 多模态 检索 知识库 幻觉 评测 可观测 蒸馏 量化 提示词 上下文 长文本 流式 批处理"
    .split()
)

try:
    import jieba

    jieba.setLogLevel(20)
    HAVE_JIEBA = True
except Exception:
    HAVE_JIEBA = False

ENG_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CAMEL_RE = re.compile(r"[a-z][A-Z0-9]|[A-Z]{2,}[a-z]")


def tokenize(text: str):
    toks = []
    if HAVE_JIEBA:
        for w in jieba.cut(text):
            w = w.strip()
            if not w:
                continue
            toks.append(w)
    # 英文 / 代码标识符
    for m in ENG_RE.findall(text):
        if len(m) >= 2:
            toks.append(m)
    return toks


def is_kept(tok: str) -> bool:
    if len(tok) < 2:
        return False
    if tok in STOPWORDS:
        return False
    if re.fullmatch(r"[A-Za-z0-9_]+", tok) and tok.lower() in ENG_STOP:
        return False
    # 纯标点/数字
    if re.fullmatch(r"[\W\d_]+", tok):
        return False
    # 过滤飞书文档内部 ID / URL 编码碎片 / 哈希串
    if len(tok) > 20:
        return False
    if "%" in tok or "=" in tok or "/" in tok:
        return False
    # 像哈希的十六进制长串（含连续 hex 且带下划线）
    if re.fullmatch(r"[0-9a-f]{12,}", tok.lower()):
        return False
    if "_" in tok and re.search(r"[0-9a-f]{8,}", tok.lower()):
        return False
    return True


def extract(answer: str, top_n: int = 6):
    if not answer:
        return []
    # 清洗：去掉图片/链接 URL、裸链接，避免 URL 碎片变成关键词
    answer = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", answer)
    answer = re.sub(r"\[[^\]]*\]\([^)]*\)", "", answer)
    answer = re.sub(r"https?://\S+", "", answer)
    toks = tokenize(answer)
    # 统计（保留大小写原始形态用于回写，但计数归一化小写英文）
    from collections import Counter

    cnt = Counter()
    forms = {}
    for t in toks:
        if not is_kept(t):
            continue
        key = t.lower() if re.fullmatch(r"[A-Za-z0-9_]+", t) else t
        cnt[key] += 1
        forms.setdefault(key, t)

    scored = []
    for key, f in cnt.items():
        tok = forms[key]
        # 必须是答案的逐字子串
        if tok not in answer:
            continue
        tech = 3 if key in TECH_TERMS or tok in TECH_TERMS else 0
        # 英文 CamelCase/专有名词加权
        if CAMEL_RE.search(tok) or (re.fullmatch(r"[A-Za-z0-9_]+", tok) and tok[0].isupper()):
            tech += 1
        score = f * 2 + len(tok) + tech
        scored.append((score, f, -len(tok), tok))
    # 排序：分数降序，频次降序，词长短的优先（更精准）
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    picked = []
    seen = set()
    for _, _, _, tok in scored:
        if tok in seen:
            continue
        seen.add(tok)
        picked.append(tok)
        if len(picked) >= top_n:
            break
    return picked[:top_n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="全量重提（含已有 keywords 的题）")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写库")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    print(f"jieba: {'available' if HAVE_JIEBA else 'NOT available (n-gram fallback)'}")

    db = sqlite3.connect(DB_PATH)
    if args.force:
        rows = db.execute("SELECT id, question_text, reference_answer FROM questions").fetchall()
    else:
        rows = db.execute(
            "SELECT id, question_text, reference_answer FROM questions "
            "WHERE keywords IS NULL OR TRIM(keywords)=''"
        ).fetchall()
    if args.limit:
        rows = rows[: args.limit]
    print(f"待处理：{len(rows)} 题")

    if args.dry_run:
        for qid, q, a in rows[:5]:
            kws = extract(a or "")
            print(f"\n[id={qid}] {q[:50]}\n  -> {kws}")
        return

    done = 0
    for qid, q, a in rows:
        kws = extract(a or "")
        if kws:
            db.execute("UPDATE questions SET keywords=? WHERE id=?", (",".join(kws), qid))
            done += 1
    db.commit()
    print(f"\n完成：写入 {done}/{len(rows)} 题的关键词。")


if __name__ == "__main__":
    main()
