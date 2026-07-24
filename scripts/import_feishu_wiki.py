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
import json
import argparse
import sqlite3
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 让本脚本能复用后端的存储抽象层（backend/storage.py）
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
from storage import get_storage
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
    # 注意：不再删除 <img>。图片交由 _resolve_images 下载到存储层后转成 markdown
    text = re.sub(r"<sheet[^>]*>.*?</sheet>", "", text, flags=re.S)
    text = re.sub(r"<bitable[^>]*>.*?</bitable>", "", text, flags=re.S)
    text = re.sub(r"<readonly-block[^>]*>.*?</readonly-block>", "", text, flags=re.S)
    text = re.sub(r"<title>.*?</title>", "", text, flags=re.S)
    # 残留标签兜底
    text = re.sub(r"<[^>]+>", "", text)
    return text


# ----------------------------- 图片处理（下载到存储层） -----------------------------
_IMG_TAG = re.compile(r'<img\b[^>]*?src=["\']([^"\']+)["\'][^>]*>', re.I)
_IMG_MD = re.compile(r'!\[[^\]]*\]\([^)]*\)')  # 含残缺 ![]( 也能匹配


def _download(url: str):
    """下载图片字节；失败（403/网络/超时）返回 None。可选 FEISHU_IMG_COOKIE 用于飞书鉴权。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        cookie = os.environ.get("FEISHU_IMG_COOKIE")
        if cookie:
            req.add_header("Cookie", cookie)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read()
    except Exception:
        return None


def _resolve_images(text: str):
    """扫描正文 <img> 与 ![alt](url)，下载到存储后端并替换为可访问 URL。
    下载失败则保留原 URL（信息不丢，前端可能 403）。返回 (新文本, url 列表)。"""
    storage = get_storage()
    urls = []

    def _save(url):
        url = url.strip()
        if not url:
            return url
        data = _download(url)
        new_url = storage.save(data, url.split("?")[0].rsplit("/", 1)[-1] or "img", None) if data else url
        if new_url not in urls:
            urls.append(new_url)
        return new_url

    def _rep_tag(m):
        return "![图片](" + _save(m.group(1)) + ")"

    def _rep_md(m):
        return "![%s](%s)" % (m.group(1), _save(m.group(2)))

    text = _IMG_TAG.sub(_rep_tag, text)
    text = _IMG_MD.sub(_rep_md, text)
    return text, urls


def _extract_img_urls(text: str):
    """从正文 markdown 提取图片 URL 列表（不下载，仅解析）。"""
    urls = []
    for inner in _IMG_MD.findall(text):
        mm = re.match(r"!\[[^\]]*\]\(([^)\s]+)\)", inner)
        if mm:
            u = mm.group(1).strip()
            if u and u not in urls:
                urls.append(u)
    return urls


def clean_answer(text: str) -> str:
    out = []
    for ln in text.split("\n"):
        s = ln.strip()
        # 整行是图片：保留（稍后 _resolve_images 下载 / 或保留原 markdown）
        out.append(s)
    text = "\n".join(out)
    # 归一化飞书导出的 XML 富文本块（<img> 不再删除）
    text = _strip_xml(text)
    # 抽离图片 markdown 占位，避免被下方「普通链接去 URL」误伤
    placeholders = []

    def _stash(m):
        placeholders.append(m.group(0))
        return "\x00IMG%d\x00" % (len(placeholders) - 1)

    text = _IMG_MD.sub(_stash, text)
    # 普通链接：去掉 URL / #锚点编码，仅保留可见文字（图片已抽离，不受影响）
    text = re.sub(r"\]\(https?://[^)]*\)", "](", text)
    text = re.sub(r"\]\(#[^)]*\)", "](", text)
    text = re.sub(r"https?://\S+", "", text)
    # 还原图片 markdown
    for i, ph in enumerate(placeholders):
        text = text.replace("\x00IMG%d\x00" % i, ph)
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
    ap.add_argument("--download-images", action="store_true",
                    help="把正文的 <img>/![alt](url) 下载到存储层（默认本地 data/images/），替换为可访问 URL")
    ap.add_argument("--update", action="store_true",
                    help="对已存在的题，若解析出图片则更新其 images 列（不改动正文）")
    args = ap.parse_args()

    items = parse(args.md)
    print(f"解析得到 {len(items)} 道题")

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
    existing = {r[0]: r[1] for r in db.execute("SELECT TRIM(question_text), id FROM questions")}
    ins = skip = upd = 0
    for c, q, a, t in items:
        key = q.strip()
        # 解析图片：下载模式替换为存储 URL；否则仅从正文提取原 URL 列表
        if args.download_images:
            a, imgs = _resolve_images(a)
        else:
            imgs = _extract_img_urls(a)
        if key in existing:
            if args.update and imgs:
                db.execute("UPDATE questions SET images=? WHERE id=?",
                           (json.dumps(imgs, ensure_ascii=False), existing[key]))
                upd += 1
            else:
                skip += 1
            continue
        db.execute(
            "INSERT INTO questions (platform, category, tags, difficulty, question_text, reference_answer, created_at, images, keywords) "
            "VALUES (?,?,?,?,?,?, datetime('now'), ?, ?)",
            (PLATFORM, c, t, None, q, a, json.dumps(imgs, ensure_ascii=False), ""),
        )
        existing[key] = None
        ins += 1
    db.commit()
    print(f"\n入库完成：新增 {ins} 题，更新 {upd} 题图片，跳过重复 {skip} 题（platform={PLATFORM}）")


if __name__ == "__main__":
    main()
