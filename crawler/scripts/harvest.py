#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent 面经收割机 · 一键增量调度器。

用法：
    # 采集 + 抽取去重 全链路（默认）
    python harvest.py --source all
    # 只采集某源（登录墙源撞验证会自动等待，重跑即 resume 续传）
    python harvest.py --source xiaohongshu
    python harvest.py --source juejin
    python harvest.py --source v2ex
    python harvest.py --source maimai        # 需先在 Chrome 登录脉脉
    python harvest.py --source nowcoder
    python harvest.py --source zhihu         # 需先在 Chrome 登录知乎
    python harvest.py --source github        # AI Infra 仓库 Markdown 采集 + 抽题
    python harvest.py --source onepoint3acres # 海外面经版公开标题索引
    # 只跑后处理（抽取+去重，产出 shortlist/refined 供挑题）
    python harvest.py --source juejin --stage process

说明：
- 采集和后处理复用当前 Python；需安装 crawler/requirements.txt。
- 所有 CDP 源串行复用同一 Chrome 标签，请勿并行启动多个采集。
- 登录墙源（小红书/脉脉/知乎）撞滑块验证会原地等待，最长 300s，期间在浏览器滑掉即可续抓。
- 知乎为强登录墙 + 强反爬，必须先在 Chrome 登录 zhihu.com 再跑，否则详情页正文残缺被跳过。
"""
import subprocess
import argparse
import sys
from pathlib import Path
from browser_startup import ensure_browser

VENV = Path(sys.executable)
MANAGED = Path(sys.executable)
HERE = Path(__file__).resolve().parent
BROWSER_SOURCES = ["xiaohongshu", "juejin", "v2ex", "maimai", "nowcoder", "zhihu"]
SOURCES = [*BROWSER_SOURCES, "github", "onepoint3acres"]


def collect(source):
    if source in BROWSER_SOURCES:
        ensure_browser()
    script = HERE / f"{source}_harvest.py"
    if not script.exists():
        print(f"[collect] 无采集脚本: {script}")
        return
    print(f"\n===== COLLECT {source} =====")
    subprocess.run([str(VENV), str(script)], check=True)


def process(source):
    if source == "onepoint3acres":
        print("[onepoint3acres] 仅索引标题和链接，结果见 data/tmp/onepoint3acres/index.jsonl")
        return
    print(f"\n===== PROCESS {source} =====")
    subprocess.run([str(MANAGED), str(HERE / "process_source.py"), "--source", source], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, choices=SOURCES + ["all"])
    ap.add_argument("--stage", choices=["collect", "process", "all"], default="all")
    a = ap.parse_args()
    srcs = SOURCES if a.source == "all" else [a.source]
    for s in srcs:
        if a.stage in ("collect", "all"):
            collect(s)
        if a.stage in ("process", "all"):
            process(s)


if __name__ == "__main__":
    main()
