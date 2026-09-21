# -*- coding: utf-8 -*-
"""从 questions/*.md 领域文件抽取候选池，供内容生产 agent 使用。
输出: questions_v2/pools/<key>.json  (含 id/title/answer/analysis/tags/score)
"""
import json, re, sys
from pathlib import Path

QDIR = Path("G:/interview-memory/crawler/questions")
OUT = Path("G:/interview-memory/crawler/questions_v2/pools")
OUT.mkdir(parents=True, exist_ok=True)

LLM_KW = re.compile(
    r"大模型|LLM|llm|transformer|Transformer|attention|注意力|token|Token|分词|tokenizer|"
    r"嵌入|[Ee]mbedding|向量|微调|LoRA|QLoRA|RLHF|DPO|PPO|SFT|预训练|推理|量化|解码|采样|"
    r"temperature|top[-_ ]?[pk]|上下文|幻觉|prompt|Prompt|GPT|BERT|LLaMA|llama|Qwen|DeepSeek|"
    r"MCP|RAG|Agent|智能体|多模态|扩散|[Dd]iffusion|KV[ -]?[Cc]ache|蒸馏|对齐|奖励模型|"
    r"损失|梯度|并行|显存|过拟合|泛化|参数量|百亿|千亿|MoE|位置编码|归一化",
)
FREQ_KW = re.compile(
    r"原理|区别|为什么|如何|怎么|流程|优化|场景|对比|底层|实现|机制|设计|区别|哪些|什么"
)

def parse_md(path: Path):
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n---\n", text)
    items = []
    for b in blocks:
        mt = re.search(r"^## \d+\.\s*(.+)$", b, re.M)
        mid = re.search(r"原题 ID：`?(q\d+)`?", b)
        if not mt or not mid:
            continue
        def sec(name, nxt):
            m = re.search(rf"### {name}\n(.*?)(?=\n### {next}|\Z)", b, re.S)
            return m.group(1).strip() if m else ""
        ans = sec("答案", "解析")
        ana = sec("解析", "难度")
        mtags = re.search(r"### 标签\n(.+)", b, re.S)
        tags = re.findall(r"`([^`]+)`", mtags.group(1)) if mtags else []
        items.append({
            "id": mid.group(1),
            "title": mt.group(1).strip(),
            "answer": ans,
            "analysis": ana,
            "tags": tags,
        })
    return items

def score(it):
    s = len(it["answer"]) + len(it["analysis"]) + 40 * len(it["tags"])
    if FREQ_KW.search(it["title"]):
        s += 300
    return s

def cap(items, n, kw_filter=None, prefer=None):
    if kw_filter:
        items = [i for i in items if kw_filter.search(i["title"] + " " + i["answer"][:400])]
    if prefer:
        def bonus(i):
            return 500 if prefer.search(i["title"]) else 0
        items = sorted(items, key=lambda i: -(score(i) + bonus(i)))
    else:
        items = sorted(items, key=lambda i: -score(i))
    return items[:n]

def main():
    all_items = {}
    for f in QDIR.glob("*.md"):
        if f.name == "README.md":
            continue
        all_items[f.stem] = parse_md(f)

    report = [f"parsed: { {k: len(v) for k, v in all_items.items()} }"]

    plans = {
        # key: (来源配置 [(file, cap, kw_filter, prefer)], )
        "rag":       ([("rag", 90, None, None)],),
        "agent":     ([("agent", 90, None, None)],),
        "llm_basic": ([("llm-basics", 90, LLM_KW, None)],),
        "training":  ([("llm-posttraining", 80, None, None), ("llm-pretraining", 45, None, None)],),
        "misc_ai":   ([("prompt", 40, None, None), ("evaluation", 27, None, None),
                       ("multimodal", 29, None, None), ("safety", 33, None, None)],),
        "serving":   ([("engineering", 70, None, re.compile(r"部署|推理|vLLM|服务|性能|监控|[Dd]ocker|k8s|GPU|延迟|吞吐|压测|网关")),
                       ("system-design", 30, None, None)],),
        "backend":   ([("go", 40, None, None), ("mysql", 30, None, None), ("redis", 25, None, None)],),
    }

    for key, groups in plans.items():
        pool = []
        seen = set()
        for src in groups[0]:
            fname, n, kwf, pref = src
            picked = cap(all_items.get(fname, []), n, kwf, pref)
            for it in picked:
                if it["id"] in seen:
                    continue
                seen.add(it["id"])
                pool.append(it)
        out = {"key": key, "pool": pool}
        (OUT / f"{key}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        report.append(f"{key}: pool={len(pool)}")

    (Path("G:/interview-memory/crawler/data/tmp/pools_report.txt")
     .write_text("\n".join(report), encoding="utf-8"))

if __name__ == "__main__":
    main()
