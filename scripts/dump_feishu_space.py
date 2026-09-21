#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dump 飞书知识库（wiki）节点正文到本地 Markdown，并输出结构统计。

用于「外部题库 vs 项目题库」的差距分析：
  - 每个节点导出一份清洗后的 Markdown（剥离飞书 <title>/<readonly-block>/<callout>/<img> 等标签）
  - 汇总每份文档的标题层级分布、字数，便于判断分类颗粒度与内容质量

依赖：本机 lark-cli（@larksuite/cli），且已完成用户态授权（`lark-cli auth login`）。

用法：
  .venv/Scripts/python scripts/dump_feishu_space.py --space-id 7456629918934302723
  .venv/Scripts/python scripts/dump_feishu_space.py --space-id 7662025183418387409 --out agent

产物：
  data/feishu_dump/<out>/<标题>.md     每个节点一份
  data/feishu_dump/<out>/_summary.csv  节点级统计
"""
import os
import re
import csv
import json
import time
import shutil
import argparse
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP_DIR = os.path.join(BASE_DIR, "data", "feishu_dump")


def _lark_paths():
    base = os.path.expanduser("~")
    lark_dir = os.path.join(base, ".workbuddy", "binaries", "node", "cli-connector-packages")
    run_js = os.path.join(lark_dir, "node_modules", "@larksuite", "cli", "scripts", "run.js")
    node = shutil.which("node") or os.path.join(
        base, ".workbuddy", "binaries", "node", "versions", "22.22.2", "node.exe")
    return node, run_js


def lark(args, max_retry=3):
    node, run_js = _lark_paths()
    env = dict(os.environ)
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    last_err = None
    for attempt in range(max_retry):
        cmd = [node, run_js] + args + ["--as", "user", "--format", "json"]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        raw = r.stdout or ""
        i = raw.find("{")
        if i >= 0:
            try:
                data = json.loads(raw[i:])
            except json.JSONDecodeError as e:
                last_err = f"JSON 解析失败: {e}"
                continue
            if data.get("ok"):
                return data
            last_err = json.dumps(data.get("error", {}), ensure_ascii=False)[:300]
        else:
            last_err = (r.stderr or raw)[:300]
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"lark-cli 失败 ({' '.join(args[:3])}): {last_err}")


def list_nodes(space_id, parent=None):
    args = ["wiki", "+node-list", "--space-id", space_id, "--page-all"]
    if parent:
        args += ["--parent-node-token", parent]
    return lark(args)["data"]["nodes"]


def walk(space_id, parent=None, depth=0, path=""):
    """深度优先遍历节点树，返回 [(depth, path, node)]。"""
    out = []
    for n in list_nodes(space_id, parent):
        title = (n.get("title") or "").strip()
        p = f"{path}/{title}" if path else title
        out.append((depth, p, n))
        if n.get("has_child"):
            out += walk(space_id, n["node_token"], depth + 1, p)
    return out


TAG_RE = [
    re.compile(r"</?readonly-block[^>]*>"),
    re.compile(r"</?callout[^>]*>"),
    re.compile(r"<img[^>]*>"),
    re.compile(r"<sheet[^>]*>"),
    re.compile(r"<bitable[^>]*>"),
]


def clean(title, content):
    content = re.sub(r"<title>.*?</title>", "", content, flags=re.S)
    for rx in TAG_RE:
        content = rx.sub("", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return "# " + title + "\n\n" + content.strip() + "\n"


def analyze(text):
    lines = text.split("\n")
    return {
        "h1": sum(1 for l in lines if re.match(r"^# ", l)),
        "h2": sum(1 for l in lines if re.match(r"^## ", l)),
        "h3": sum(1 for l in lines if re.match(r"^### ", l)),
        "bullets": sum(1 for l in lines if re.match(r"^\s*[-*] ", l)),
        "chars": len(text),
    }


def sanitize(title, used):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", title).strip() or "untitled"
    name = name[:60]
    base = name
    n = 1
    while name.lower() in used:
        n += 1
        name = f"{base}_{n}"
    used.add(name.lower())
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--space-id", required=True)
    ap.add_argument("--parent", default=None, help="父节点 token；不传则列知识库根下全部节点")
    ap.add_argument("--out", default=None, help="输出子目录名，默认用 space-id")
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument("--recursive", action="store_true", help="递归遍历子节点")
    args = ap.parse_args()

    if args.recursive:
        nodes = walk(args.space_id, args.parent)
    else:
        nodes = [(0, n.get("title", ""), n) for n in list_nodes(args.space_id, args.parent)]
    print(f"节点数：{len(nodes)}")

    out_dir = os.path.join(DUMP_DIR, args.out or args.space_id)
    os.makedirs(out_dir, exist_ok=True)
    rows, used = [], set()

    for idx, (depth, path, n) in enumerate(nodes, 1):
        title = (n.get("title") or "").strip()
        token = n["node_token"]
        if not title:
            print(f"  [跳过] 空标题节点 {token}")
            continue
        print(f"  [{idx}/{len(nodes)}] {'  ' * depth}{path} ({token})")
        md = lark(["docs", "+fetch", "--doc", token, "--doc-format", "markdown"])["data"]["document"]["content"]
        text = clean(title, md)
        fname = sanitize(path.replace("/", "__"), used) + ".md"
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as f:
            f.write(text)
        stat = analyze(text)
        rows.append({"path": path, "depth": depth, "title": title, "node_token": token,
                     "file": fname, **stat})
        time.sleep(args.sleep)

    csv_path = os.path.join(out_dir, "_summary.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "depth", "title", "node_token", "file",
                                          "h1", "h2", "h3", "bullets", "chars"])
        w.writeheader()
        w.writerows(rows)

    print(f"\n完成：{len(rows)} 个文档写入 {out_dir}")
    for r in rows:
        print(f"  {r['title'][:28]:30s} h1={r['h1']:3d} h2={r['h2']:4d} h3={r['h3']:4d} 字数={r['chars']:7d}")


if __name__ == "__main__":
    main()
