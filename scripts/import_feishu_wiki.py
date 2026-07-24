#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""解析飞书 Wiki 导出的 Markdown（Golang 面试题整理），提取 Q/A 并入库。

用法：
  .venv/Scripts/python scripts/import_feishu_wiki.py --md data/feishu_go_qa.md --dry-run
  .venv/Scripts/python scripts/import_feishu_wiki.py --md data/feishu_go_qa.md

约定：
- 文档结构：一级标题(h1)=分类，二级标题(h2)=题目，h2 正文为答案（含 **分析**/**回答**）。
- 分类直接用文档自带 h1 映射到题库分类（Go 体系，不与大模型/Java 题混）。
- 答案保留原文字面（关键词高亮依赖逐字命中）；仅剥离飞书特有标签、折叠空行。
- platform = 'feishu-wiki'；keywords 留空，待 LLM/启发式统一提取。
"""
import os
import re
import sys
import argparse
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "interview_memory.db")
DEFAULT_MD = os.path.join(BASE_DIR, "data", "feishu_cs_qa.md")

PLATFORM = "feishu-wiki"

# 文档 h1 -> 题库分类（Go 体系自成一类，避免和 AI/Java 题混）
CAT_MAP = {
    "基础相关": "Go基础",
    "Slice相关": "Go切片",
    "Interface相关": "Go接口",
    "Context 相关": "Go Context",
    "Channel 相关": "Go Channel",
    "Map 相关": "Go Map",
    "sync.Map相关": "Go sync.Map",
    "GMP 相关": "Go调度(GMP)",
    "sync相关": "Go同步(sync)",
    "并发相关": "Go并发",
    "GC相关": "Go GC",
    "内存相关": "Go内存",
    "Go代码性能优化": "Go性能优化",
    "Gin框架相关": "Go框架-Gin",
    "Gorm框架相关": "Go框架-Gorm",
    "其他": "Go其他",
    "代码题相关": "算法手撕(Go)",
}

# 已知明显错字修正（仅限确凿的源文档笔误，保持其余原文）
TYPO_FIX = [
    ("垃圾语高", "垃圾回收"),
]


def normalize_cat(raw: str) -> str:
    raw = raw.strip().rstrip("：:").strip()
    # 去掉括号注释（如 "sync相关（重点看，这块非常陌生）" -> "sync相关"）
    raw = re.sub(r"[（(].*?[)）]", "", raw).strip()
    # 兜底：直接用原文作分类（多节点 wiki 的 h1 是文档标题，如 "Redis面试题整理"）
    return CAT_MAP.get(raw, raw)


def _strip_xml(text: str) -> str:
    """把飞书 docx markdown 导出中夹杂的 XML 富文本块归一化为纯文本/markdown。"""
    # 块级
    text = re.sub(r"<p>\s*", "", text)
    text = re.sub(r"\s*</p>", "\n\n", text)
    text = re.sub(r"</?ol[^>]*>", "", text)
    text = re.sub(r"</?ul[^>]*>", "", text)
    text = re.sub(r"<li[^>]*>", "- ", text)
    text = re.sub(r"</li>", "\n", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<code>", "`", text)
    text = re.sub(r"</code>", "`", text)
    text = re.sub(r"</?b>", "**", text)
    text = re.sub(r"</?strong>", "**", text)
    # 引用 / 容器：保留内部文字或整体移除
    text = re.sub(r"<cite[^>]*>.*?</cite>", "", text, flags=re.S)
    text = re.sub(r"<callout[^>]*>.*?</callout>", "", text, flags=re.S)
    text = re.sub(r"<img[^>]*>", "", text)
    text = re.sub(r"<sheet[^>]*>.*?</sheet>", "", text, flags=re.S)
    text = re.sub(r"<bitable[^>]*>.*?</bitable>", "", text, flags=re.S)
    text = re.sub(r"<readonly-block[^>]*>.*?</readonly-block>", "", text, flags=re.S)
    text = re.sub(r"<title>.*?</title>", "", text, flags=re.S)
    # 残留标签兜底
    text = re.sub(r"<[^>]+>", "", text)
    return text


def clean_answer(text: str) -> str:
    out = []
    for ln in text.split("\n"):
        s = ln.strip()
        # 整行是图片/纯链接（飞书导出会把图片转成 ![...](internal-api-drive...) 超长 URL）-> 直接丢弃
        if s.startswith("!") and "](" in s:
            continue
        # 链接：去掉 URL / #锚点编码，仅保留可见文字
        s = re.sub(r"\]\(https?://[^)]*\)", "](", s)
        s = re.sub(r"\]\(#[^)]*\)", "](", s)
        s = re.sub(r"https?://\S+", "", s)
        out.append(s)
    text = "\n".join(out)
    # 归一化飞书导出的 XML 富文本块
    text = _strip_xml(text)
    # 折叠多余空行（>=3 个换行 -> 2 个）
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 已知错字修正
    for bad, good in TYPO_FIX:
        text = text.replace(bad, good)
    return text.strip()


def _parse_section(lines):
    """解析单个文档段落（已按 h1 文档标题切分），返回本段题目列表。"""
    items = []
    cat = None
    subcat = ""        # 当前子分类（文档内原 h1 降级为 h3 后作 tag）
    cur_q = None
    cur_body = []
    in_code = False

    def flush():
        nonlocal cur_q, cur_body
        if cur_q is not None:
            ans = clean_answer("\n".join(cur_body))
            items.append((cat or "未分类", cur_q, ans, subcat))
            cur_q = None
            cur_body = []

    for ln in lines:
        # 跟踪代码围栏
        if ln.lstrip().startswith("```"):
            in_code = not in_code
            continue
        m1 = re.match(r"^#\s+(.+)$", ln)
        m2 = re.match(r"^##\s+(.+)$", ln)
        m3 = re.match(r"^###\s+(.+)$", ln)
        if m1 or m2 or m3:
            # 题目/子分类标题绝不可能位于代码块内：强制结束围栏，
            # 兜底个别文档代码围栏未闭合导致的状态泄漏
            if m2 or m3:
                in_code = False
            if m1:
                flush()
                cat = normalize_cat(m1.group(1))
                subcat = ""     # 切换分类时重置子分类
                continue
            if m3:
                subcat = re.sub(r"[*#]", "", m3.group(1)).strip().rstrip("：:").strip()
                continue
            if m2:
                flush()
                cur_q = m2.group(1).strip()
                cur_body = []
                continue
        if in_code:
            if cur_q is not None:
                cur_body.append(ln)
            continue
        # 其余行归属当前题目正文
        if cur_q is not None:
            cur_body.append(ln)
    flush()
    return items


def parse(md_path: str):
    """返回 [(category, question_text, answer, subcat_tag), ...]

    先按 h1 文档标题切分为独立段落，逐段解析，避免某个文档的代码围栏
    未闭合泄漏到后续文档（曾导致仅首篇被解析）。
    """
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    starts = [i for i, l in enumerate(lines) if re.match(r"^#\s+\S", l)]
    if not starts:
        return []
    items = []
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        items.extend(_parse_section(lines[s:e]))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=DEFAULT_MD, help="飞书导出的 Markdown 路径")
    ap.add_argument("--dry-run", action="store_true", help="只打印解析结果，不写库")
    args = ap.parse_args()

    items = parse(args.md)
    print(f"解析得到 {len(items)} 道题")

    # 分类分布
    from collections import Counter
    dist = Counter(c for c, _, _, _ in items)
    print("\n分类分布：")
    for c, n in dist.most_common():
        print(f"  {c}: {n}")

    if args.dry_run:
        print("\n--- 前 3 题预览 ---")
        for c, q, a, t in items[:3]:
            print(f"[{c}] (tag:{t}) {q}\n答案前 120 字：{a[:120]}\n")
        return

    db = sqlite3.connect(DB_PATH)
    seen = set(r[0] for r in db.execute("SELECT TRIM(question_text) FROM questions"))
    ins = 0
    skip = 0
    for c, q, a, t in items:
        key = q.strip()
        if key in seen:
            skip += 1
            continue
        db.execute(
            "INSERT INTO questions (platform, category, tags, difficulty, question_text, reference_answer, created_at, images, keywords) "
            "VALUES (?,?,?,?,?,?, datetime('now'), '', ?)",
            (PLATFORM, c, t, None, q, a, ""),
        )
        seen.add(key)
        ins += 1
    db.commit()
    print(f"\n入库完成：新增 {ins} 题，跳过重复 {skip} 题（platform={PLATFORM}）")


if __name__ == "__main__":
    main()
