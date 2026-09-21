#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 DeepSeek API 为题库中「空答案」的题补答案（简历面试向，结构化输出）。

安全/可用设计：
  - 仅处理 answer.展开 为空的题（默认即本次新增的 2652 道 status="新增(待补答案)"）；
  - 启动前复制题库为 .bak_<时间戳>（硬回滚点）；
  - 进度落盘 data/tmp/answer_fill_progress.json（已完成的 id 集合），可断点续跑；
  - 每批（--flush）写回一次题库，避免单点失败丢进度；
  - 并发 --workers 调用，遇 429/网络错指数退避重试；
  - 结构化解析失败则该题留空、记入 skipped，不中断整体。

答案结构：{简版, 展开, 加分点, 雷区}，按分类微调提示词。

用法：
  python scripts/fill_answers_deepseek.py --limit 12 --workers 4        # 先小批量试质量
  python scripts/fill_answers_deepseek.py --workers 8                  # 全量（后台跑）
  python scripts/fill_answers_deepseek.py --dry-run                    # 仅统计待补
"""
import argparse
import json
import os
import shutil
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))
import bank  # noqa: E402

BANK_PATH = BASE / "data" / "questions-bank.json"
PROGRESS = BASE / "data" / "tmp" / "answer_fill_progress.json"
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
CAT_HINT = {
    "概念基础": "侧重概念定义、为什么、适用场景，用通俗类比讲清原理。",
    "工程落地": "侧重真实工程实践、踩坑、权衡（性能/一致性/可维护性）。",
    "架构设计": "侧重模块划分、数据流、取舍与扩展性，可画文字示意图。",
    "项目深挖": "假设你做过该项目，讲清背景、难点、你的决策与复盘。",
    "手撕算法": "给出思路、复杂度、边界 case，并给一段可运行的核心代码（伪码/Python）。",
    "后端八股（Go）": "Go 语言特性/调度/内存/并发相关，给出原理与代码示例。",
    "后端八股": "后端通用八股（网络/DB/缓存/中间件），原理+示例。",
    "行为与HR": "给出结构化回答思路与可落地的话术，注意真实可信。",
}


def build_prompt(item):
    cat = item.get("category") or "概念基础"
    hint = CAT_HINT.get(cat, "给出清晰、准确、有深度的面试回答。")
    q = (item.get("content") or "").strip()
    return (
        "你是一位资深后端 / AI Agent 技术面试官。请针对下面这道面试题，"
        "用简体中文作答，并【严格只输出一个 JSON 对象】（不要 markdown 代码块、不要多余说明），"
        "字段为：\n"
        "  \"简版\": 一句话核心要点；\n"
        "  \"展开\": 详细解答，含原理与必要例子；\n"
        "  \"加分点\": 能体现深度的点（源码/论文/踩坑均可）；\n"
        "  \"雷区\": 候选人常见的误解或答错点。\n"
        f"题目分类：{cat}。提示：{hint}\n"
        f"面试题：{q}"
    )


def call_deepseek(api_key, prompt, timeout=60, retries=4):
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }).encode("utf-8")
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                API_URL, data=payload,
                headers={"Content-Type": "application/json",
                          "Authorization": f"Bearer {api_key}"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # 指数退避，应对 429/抖动
    raise last


def parse_answer(text):
    # 容错：去掉可能的 ```json 包裹
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.lower().startswith("json"):
            t = t[4:]
    t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError as e:
        # 容错：DeepSeek 偶发在 JSON 后多附内容（Extra data），
        # 或前后有多余说明，提取第一个完整匹配的 {...}
        if "Extra data" in str(e) or "Expecting" in str(e):
            depth = 0
            start = None
            for i, ch in enumerate(t):
                if ch == "{":
                    if start is None:
                        start = i
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0 and start is not None:
                        return json.loads(t[start:i + 1])
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="最多处理多少道（0=全部）")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--flush", type=int, default=50, help="每完成多少道写回一次题库")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        sys.exit("[X] 未找到 DEEPSEEK_API_KEY 环境变量，无法生成答案。")
    if args.dry_run:
        data = bank.load(BANK_PATH)
        todo = [it for it in data["items"]
                if not (it.get("answer") or {}).get("展开")]
        print("[dry-run] 待补答案题数: %d" % len(todo))
        return 0

    data = bank.load(BANK_PATH)
    items = data["items"]
    progress = set()
    if PROGRESS.exists():
        progress = set(json.loads(PROGRESS.read_text(encoding="utf-8")).get("done", []))
    print("已完成(续跑跳过): %d" % len(progress))

    todo = [it for it in items
            if not (it.get("answer") or {}).get("展开") and it.get("id") not in progress]
    if args.limit:
        todo = todo[:args.limit]
    print("本次待处理: %d（workers=%d）" % (len(todo), args.workers))

    # 备份
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = Path(str(BANK_PATH) + ".bak_%s" % ts)
    shutil.copy2(BANK_PATH, bak)
    print("[备份] %s" % bak)

    done_ids = set(progress)
    skipped = []
    lock = {}

    def work(it):
        try:
            raw = call_deepseek(api_key, build_prompt(it))
            ans = parse_answer(raw)
            return it["id"], ans, None
        except Exception as e:  # noqa: BLE001
            return it["id"], None, repr(e)[:120]

    cnt = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, it): it for it in todo}
        for fut in as_completed(futs):
            qid, ans, err = fut.result()
            if err or not ans:
                skipped.append((qid, err))
                continue
            # 写回该题 answer
            for it in items:
                if it.get("id") == qid:
                    it["answer"] = {
                        "简版": (ans.get("简版") or "").strip(),
                        "展开": (ans.get("展开") or "").strip(),
                        "加分点": (ans.get("加分点") or "").strip(),
                        "雷区": (ans.get("雷区") or "").strip(),
                    }
                    if it.get("status") == "新增(待补答案)":
                        it["status"] = "已补答案"
                    break
            done_ids.add(qid)
            cnt += 1
            if cnt % args.flush == 0:
                data["meta"]["total"] = len(items)
                bank.save(data, BANK_PATH)
                PROGRESS.write_text(json.dumps({"done": list(done_ids)}, ensure_ascii=False),
                                   encoding="utf-8")
                print("  ...已写回 %d 道（累计完成 %d）" % (cnt, len(done_ids)))

    # 末次落盘
    data["meta"]["total"] = len(items)
    bank.save(data, BANK_PATH)
    PROGRESS.write_text(json.dumps({"done": list(done_ids)}, ensure_ascii=False), encoding="utf-8")
    print("完成：本次补 %d 道，跳过/失败 %d 道。" % (cnt, len(skipped)))
    for qid, e in skipped[:10]:
        print("  [SKIP] %s %s" % (qid, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
