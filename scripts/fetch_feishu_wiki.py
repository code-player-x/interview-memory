#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从飞书知识库（多节点 wiki）拉取全部题目，导出为兼容 import_feishu_wiki.py 的 Markdown。

流程：
  1. 列出根节点下全部子节点（每个子节点 = 一个分类 docx）
  2. 逐个 `lark-cli docs +fetch --doc-format markdown` 拉取正文
  3. 转换：prepend '# <节点标题>' 作为题库分类(h1)；把文档内 h1 降一级为 h3（作为子分类 tag），
     h2 保持为题目；剥离飞书特有标签（<title>/<readonly-block>/<callout>...）
  4. 拼接为 data/feishu_cs_qa.md

用法：
  .venv/Scripts/python scripts/fetch_feishu_wiki.py --dry-run --limit 2   # 只拉前 2 个节点预览
  .venv/Scripts/python scripts/fetch_feishu_wiki.py                      # 全量拉取并写 MD
"""
import os
import re
import sys
import json
import shutil
import subprocess
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 计算机面试题题库 根节点
ROOT_TOKEN = "LlBswlr0mimN7hkxRxwczPYGnjD"
SPACE_ID = "7456629918934302723"
OUT_MD = os.path.join(DATA_DIR, "feishu_cs_qa.md")


def _lark_paths():
    """定位 lark-cli 的真实入口（它是 POSIX 包装脚本，Windows 子进程无法直接 exec，
    故直接调用 node <cli>/node_modules/@larksuite/cli/scripts/run.js）。"""
    base = os.path.expanduser("~")
    lark_dir = os.path.join(base, ".workbuddy", "binaries", "node", "cli-connector-packages")
    run_js = os.path.join(lark_dir, "node_modules", "@larksuite", "cli", "scripts", "run.js")
    node = shutil.which("node") or os.path.join(
        base, ".workbuddy", "binaries", "node", "versions", "22.22.2", "node.exe")
    return node, run_js


def lark(args):
    node, run_js = _lark_paths()
    cmd = [node, run_js] + args + ["--as", "user", "--format", "json"]
    env = dict(os.environ)
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"lark-cli 失败 ({args[:3]}): {r.stderr[:400]}")
    raw = r.stdout
    i = raw.find("{")
    if i < 0:
        raise RuntimeError(f"输出中无 JSON: {raw[:300]}")
    return json.loads(raw[i:])


def list_children():
    d = lark(["wiki", "+node-list", "--space-id", SPACE_ID,
              "--parent-node-token", ROOT_TOKEN, "--page-all"])
    return d["data"]["nodes"]


def fetch_doc(node_token):
    d = lark(["docs", "+fetch", "--doc", node_token, "--doc-format", "markdown"])
    return d["data"]["document"]["content"]


def transform(title, content):
    # 剥离文档级 <title>...</title>（我们有节点标题了）
    content = re.sub(r"<title>.*?</title>", "", content, flags=re.S)
    # 飞书特有块级标签（保留内部文字）
    content = re.sub(r"</?readonly-block[^>]*>", "", content)
    content = re.sub(r"</?callout[^>]*>", "", content)
    content = re.sub(r"<img[^>]*>", "", content)
    content = re.sub(r"<sheet[^>]*>", "", content)
    content = re.sub(r"<bitable[^>]*>", "", content)
    # 文档内 h1 降一级 -> h3（作为子分类 tag）；h2 题目保持不变
    content = re.sub(r"(?m)^# ", "### ", content)
    # 折叠多余空行
    content = re.sub(r"\n{3,}", "\n\n", content)
    return "# " + title + "\n\n" + content.strip() + "\n\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只预览，不覆盖正式 MD")
    ap.add_argument("--limit", type=int, default=0, help="最多拉取 N 个节点（调试用）")
    args = ap.parse_args()

    nodes = list_children()
    print(f"知识库子节点：{len(nodes)} 个")

    out_parts = []
    for idx, n in enumerate(nodes):
        title = (n.get("title") or "").strip()
        token = n["node_token"]
        if not title:
            print(f"  [跳过] 空标题节点 {token}")
            continue
        if args.limit and len(out_parts) >= args.limit:
            print(f"  [--limit {args.limit}] 已达上限，停止")
            break
        print(f"  [{len(out_parts)+1}/{len(nodes)}] 拉取：{title} ({token})")
        md = fetch_doc(token)
        out_parts.append(transform(title, md))

    combined = "\n".join(out_parts)
    if args.dry_run:
        prev = OUT_MD + ".preview"
        with open(prev, "w", encoding="utf-8") as f:
            f.write(combined)
        print(f"\n[dry-run] 预览写入 {prev}（{len(combined)} 字符，{len(out_parts)} 个分类），未覆盖正式文件")
        return

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(combined)
    print(f"\n完成：写入 {OUT_MD}（{len(combined)} 字符，{len(out_parts)} 个分类）")


if __name__ == "__main__":
    main()
