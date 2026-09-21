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
    # 只跑后处理（抽取+去重，产出 shortlist/refined 供挑题）
    python harvest.py --source juejin --stage process

说明：
- 采集（CDP 源）统一用 venv python（含 websocket-client）；后处理用 managed python（仅 stdlib）。
- 所有 CDP 源串行复用同一 Chrome 标签，请勿并行启动多个采集。
- 登录墙源（小红书/脉脉/知乎）撞滑块验证会原地等待，最长 300s，期间在浏览器滑掉即可续抓。
- 知乎为强登录墙 + 强反爬，必须先在 Chrome 登录 zhihu.com 再跑，否则详情页正文残缺被跳过。
"""
import subprocess
import argparse
from pathlib import Path

VENV = Path("C:/Users/UserName/.workbuddy/binaries/python/envs/default/Scripts/python.exe")
MANAGED = Path("C:/Users/UserName/.workbuddy/binaries/python/versions/3.13.12/python.exe")
HERE = Path(__file__).resolve().parent
SOURCES = ["xiaohongshu", "juejin", "v2ex", "maimai", "nowcoder", "zhihu"]


def collect(source):
    script = HERE / f"{source}_harvest.py"
    if not script.exists():
        print(f"[collect] 无采集脚本: {script}")
        return
    print(f"\n===== COLLECT {source} =====")
    subprocess.run([str(VENV), str(script)], check=False)


def process(source):
    print(f"\n===== PROCESS {source} =====")
    subprocess.run([str(MANAGED), str(HERE / "process_source.py"), "--source", source], check=False)


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
