#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
split_cat_xml.py — 把一个分类的完整汇总 XML 切分成 N 个「在题目边界上」的完整分片，
用于绕过 lark-cli docs +update --command overwrite 对单次大体量（~>150KB）请求的服务端超时：
  - 分片 0：含 <title>/<h1>/<blockquote>/<hr/> 头 + 前若干题
  - 分片 1..N：仅题目块（<h2>...<hr/>），供 --command append 续写
上传时：overwrite(分片0) → append(分片1) → append(分片2) ... 合并成「一个分类一个文档」。

用法：
  python scripts/split_cat_xml.py 后端八股 6
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(BASE, "data", "questions-bank.json")
TMP = os.path.join(BASE, "data", "tmp")
os.makedirs(TMP, exist_ok=True)


def sanitize(name: str) -> str:
    return re.sub(r'[:*?"<>|/\\]', "_", name)


def esc(t: str) -> str:
    if t is None:
        return ""
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def header(cat: str, n: int) -> str:
    return "\n".join([
        f'<title>{esc(cat)}（共 {n} 题）</title>',
        f"<h1>{esc(cat)} 面试题汇总（共 {n} 题）</h1>",
        "<blockquote>本文件由 Agent 面经收割机自动汇总，按分类归档。"
        "每题含「简版 / 展开 / 加分点 / 雷区」四段式答案。</blockquote>",
        "<hr/>",
    ])


def q_block(it: dict) -> str:
    a = it.get("answer", {}) or {}
    p = [f'<h2>Q{it["_idx"]}. {esc(it["content"])}</h2>']
    meta = (
        f'<b>来源</b>：{esc(it.get("source", ""))} ｜ '
        f'<b>难度</b>：{esc(it.get("difficulty", ""))} ｜ '
        f'<b>标签</b>：{esc("，".join(it.get("tags", [])))}'
    )
    p.append(f"<p>{meta}</p>")
    if a.get("简版"):
        p += ["<h3>简版</h3>", f'<p>{esc(a["简版"])}</p>']
    if a.get("展开"):
        p += ["<h3>展开</h3>", f'<p>{esc(a["展开"])}</p>']
    if a.get("加分点"):
        p += ["<h3>加分点</h3><ul>"] + [f"<li>{esc(s.strip())}</li>" for s in a["加分点"].split("；") if s.strip()] + ["</ul>"]
    if a.get("雷区"):
        p += ["<h3>雷区 / 易错</h3><ul>"] + [f"<li>{esc(s.strip())}</li>" for s in a["雷区"].split("；") if s.strip()] + ["</ul>"]
    for u in (it.get("sources", []) or []):
        p += ['<h3>来源</h3><ul>', f'<li><a href="{esc(u)}">{esc(u)}</a></li>', "</ul>"]
    if it.get("leetcode_url"):
        u = it["leetcode_url"]
        p += [f'<p><b>力扣</b>：<a href="{esc(u)}">{esc(u)}</a></p>']
    p.append("<hr/>")
    return "\n".join(p)


def main():
    cat = sys.argv[1] if len(sys.argv) > 1 else "后端八股"
    nparts = int(sys.argv[2]) if len(sys.argv) > 2 else 6

    with open(BANK, encoding="utf-8") as f:
        bank = json.load(f)
    items = [it for it in bank["items"] if it.get("category") == cat]
    items = [{**it, "_idx": i + 1} for i, it in enumerate(items)]
    k = len(items)
    print(f"分类 {cat}: 共 {k} 题，切 {nparts} 片")

    base = k // nparts
    rem = k % nparts
    parts, start = [], 0
    for pi in range(nparts):
        cnt = base + (1 if pi < rem else 0)
        parts.append(items[start:start + cnt])
        start += cnt

    for i, grp in enumerate(parts):
        if i == 0:
            xml = header(cat, k) + "\n" + "\n".join(q_block(it) for it in grp)
        else:
            xml = "\n".join(q_block(it) for it in grp)
        path = os.path.join(TMP, f"cat_{sanitize(cat)}_part{i}.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"  分片{i}: {len(xml)} 字符 | {len(grp)} 题 -> {os.path.basename(path)}")


def split_xml(xml_path: str, cat_name: str, nparts: int, prefix: str = "cat_"):
    """从已有 XML 文件中按 <h2> 题目边界切分为 N 片（通用版本）。
    分片 0 含原始头（<title>/<h1>/...），后续片仅题目块。
    """
    with open(xml_path, encoding="utf-8") as f:
        content = f.read()

    # 找到第一个 <h2> 作为头/体分界点
    first_h2 = content.find("<h2>")
    if first_h2 == -1:
        raise ValueError(f"No <h2> found in {xml_path}")

    header_text = content[:first_h2]
    body = content[first_h2:]

    # 按 <h2> 拆成题目块
    blocks = re.split(r'(?=<h2>)', body)
    blocks = [b.strip() for b in blocks if b.strip()]

    k = len(blocks)
    base = k // nparts
    rem = k % nparts
    parts, start = [], 0
    for pi in range(nparts):
        cnt = base + (1 if pi < rem else 0)
        parts.append(blocks[start:start + cnt])
        start += cnt

    san = sanitize(cat_name)
    for i, grp in enumerate(parts):
        if i == 0:
            xml = header_text + "\n" + "\n".join(grp)
        else:
            xml = "\n".join(grp)
        path = os.path.join(TMP, f"{prefix}{san}_part{i}.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"  part{i}: {len(xml)} chars | {len(grp)} questions -> {os.path.basename(path)}")


if __name__ == "__main__":
    main()
