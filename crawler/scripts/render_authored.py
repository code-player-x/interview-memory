#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 writer 产出的 questions_v2/authored/<domain>.jsonl 渲染成按领域分类的 Markdown。
每题五段：高频程度 / 考察点 / 回答框架 / 参考回答 / 常见追问。
同时与 questions/<domain>.md 的 '## ' 题数做核对，报告缺漏。
用法：python scripts/render_authored.py
"""
import json, re, collections
from pathlib import Path

PROJ = Path(r"G:\interview-memory\crawler")
AUTH = PROJ / "questions_v2" / "authored"
SRC = PROJ / "questions"
OUT = PROJ / "questions_v2" / "full_v2"
OUT.mkdir(parents=True, exist_ok=True)

FREQ_STAR = {5: "★★★★★", 4: "★★★★", 3: "★★★", 2: "★★", 1: "★", 0: "（未评）"}

# 方案②：只渲染 AI 工程核心域（其余域保持派生版 full/*.md，不在此渲染）
AI_CORE = {
    "llm-basics", "llm-pretraining", "llm-posttraining", "multimodal",
    "agent", "rag", "prompt", "evaluation", "safety", "ai-product",
}

# 域文件名 → 中文域名（与 classify_questions.py 保持一致；供渲染标题用）
DOMAIN_CN = {
    "puzzle": "智力题与逻辑推理",
    "llm-posttraining": "大模型后训练（微调/对齐）",
    "llm-pretraining": "大模型预训练",
    "algorithm": "手撕算法",
    "mq": "消息队列（Kafka 等）",
    "java": "Java / JVM / 并发",
    "os-network": "操作系统与计算机网络",
    "distributed": "分布式系统",
    "redis": "Redis 与缓存",
    "mysql": "MySQL",
    "go": "Go 语言",
    "rag": "RAG 与向量检索",
    "multimodal": "多模态",
    "prompt": "提示工程",
    "safety": "安全与沙箱",
    "agent": "Agent 架构与工程",
    "evaluation": "评估与可观测",
    "system-design": "系统设计与场景题",
    "frontend": "前端与全栈",
    "ai-product": "AI 产品与应用",
    "design-pattern": "设计模式 / 面向对象",
    "llm-basics": "大模型与 AI 基础概念",
    "engineering": "工程落地与运维",
    "behavioral": "行为面试 / 项目深挖 / HR",
    "general": "其他 / 未分类",
}


def cn_of(domain, recs):
    return DOMAIN_CN.get(domain) or (recs[0].get("domain") if recs else None) or domain

def src_count(domain):
    f = SRC / f"{domain}.md"
    if not f.exists():
        return None
    return sum(1 for _ in re.finditer(r"^## ", f.read_text(encoding="utf-8"), re.M))

def main():
    jsonls = sorted([p for p in AUTH.glob("*.jsonl") if not p.stem.startswith("_")])
    if not jsonls:
        print("没有找到 authored/*.jsonl，作者可能还没产出。")
        return
    index_rows = []
    total_ok = 0
    total_expect = 0
    print(f"发现 {len(jsonls)} 个域文件\n")
    for jf in jsonls:
        domain = jf.stem
        recs = []
        bad = 0
        for ln in jf.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                recs.append(json.loads(ln))
            except Exception:
                bad += 1
        cn = cn_of(domain, recs)
        expect = src_count(domain)
        got = len(recs)
        total_ok += got
        if expect is not None:
            total_expect += expect
        flag = "OK" if expect is None or expect == got else f"缺 {expect-got}"
        print(f"{cn:<22} {domain:<16} 产出 {got:>4} / 源 {expect}  {flag}  (坏行 {bad})")

        # 渲染 markdown
        body = [f"# {cn}", "",
                f"> 题目数量：**{got}** ｜ 渲染时间：自动 ｜ 源：authored/{domain}.jsonl", "",
                "---", ""]
        for i, r in enumerate(recs, 1):
            title = (r.get("title") or "").strip()
            qid = (r.get("id") or "").strip()
            freq = int(r.get("freq") or 0)
            kaodian = (r.get("kaodian") or "").strip()
            framework = (r.get("framework") or "").strip()
            answer = (r.get("answer") or "").strip()
            zhui = (r.get("追问") or r.get("followup") or r.get("follow_up") or r.get("zhu问") or "").strip()
            stars = FREQ_STAR.get(freq, "（未评）")
            body.append(f"## {i}. {title}")
            body.append("")
            if qid:
                body.append(f"> 原题 ID：`{qid}`")
                body.append("")
            body.append(f"**高频程度**：{stars}")
            body.append("")
            body.append(f"**考察点**：{kaodian if kaodian else '（待补）'}")
            body.append("")
            body.append("**回答框架**：")
            body.append("")
            body.append(framework if framework else "（待补）")
            body.append("")
            body.append("**参考回答**：")
            body.append("")
            body.append(answer if answer else "（待补）")
            body.append("")
            if zhui:
                body.append(f"**常见追问**：{zhui}")
                body.append("")
            body.append("---")
            body.append("")
        (OUT / f"{domain}.md").write_text("\n".join(body), encoding="utf-8")

    # 索引
    idx = ["# 全量题库（精选标准 · 按领域）", "",
           f"> 总题数：{total_ok}（源 {total_expect}）｜ 渲染：questions_v2/full_v2/",
           "", "| 文件名 | 领域 | 题目数量 |", "| --- | --- | ---: |"]
    for jf in jsonls:
        recs = [json.loads(l) for l in jf.read_text(encoding="utf-8").splitlines() if l.strip()]
        cn = cn_of(jf.stem, recs)
        idx.append(f"| [{jf.stem}.md](./{jf.stem}.md) | {cn} | {len(recs)} |")
    idx.append(f"| **合计** | | **{total_ok}** |")
    (OUT / "INDEX.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    print(f"\n[done] 渲染 {len(jsonls)} 个域到 {OUT}")
    print(f"       总产出 {total_ok} 题（源 {total_expect}）")
    print(f"       索引: {OUT/'INDEX.md'}")

if __name__ == "__main__":
    main()
