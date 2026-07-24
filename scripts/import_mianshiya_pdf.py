#!/usr/bin/env python
"""解析面试鸭 PDF（AI大模型原理和应用面试题速记通关版）入库。

流程：
  1. pdfplumber 抽取全文
  2. 修复 PDF 字体把常用汉字映射成「康熙部首」码位的乱码（NFKC 归一化对应区间）
  3. 基于「？」做问答切分（处理问句换行、答案内偶发问号）
  4. 关键词规则分类（映射到现有 category，必要时新增）
  5. 写入 questions 表（platform=mianshiya.com，keywords 留空待 LLM 提取）

用法：
  .venv/Scripts/python scripts/import_mianshiya_pdf.py --dry-run
  .venv/Scripts/python scripts/import_mianshiya_pdf.py            # 实际入库
"""
import os
import re
import sys
import argparse
import sqlite3
import unicodedata

try:
    import pdfplumber
except Exception as e:
    print("缺少 pdfplumber：请先 .venv/Scripts/pip install pdfplumber")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "interview_memory.db")
PDF_PATH = r"D:/download_music/AI大模型原理和应用面试题速记通关版 _ 面试刷题 mianshiya.com.pdf"

# PDF 字体把常用汉字错误映射成「康熙部首/部首补充/笔画」码位：
#  - 康熙部首(U+2F00-2FDF) 与 CJK笔画(U+31C0-31EF)：NFKC 可归一化回正确汉字
#  - 部首补充(U+2E80-2EFF)：NFKC 不归一化，需显式映射（本 PDF 实测用到的 13 个）
_RADICAL_MAP = {
    0x2ED3: "长", 0x2EC5: "见", 0x2EDA: "页", 0x2EEC: "齐", 0x2EC6: "角",
    0x2EDB: "风", 0x2ED4: "门", 0x2ECB: "车", 0x2EDC: "飞", 0x2EE2: "马",
    0x2EE3: "骨", 0x2EC1: "虎", 0x2EC9: "贝",
}


def fix_char(ch: str) -> str:
    cp = ord(ch)
    if cp in _RADICAL_MAP:
        return _RADICAL_MAP[cp]
    if (0x2F00 <= cp <= 0x2FDF) or (0x31C0 <= cp <= 0x31EF):
        return unicodedata.normalize("NFKC", ch)
    return ch


def clean_text(s: str) -> str:
    return "".join(fix_char(c) for c in s)


def extract_pages(path: str):
    pages = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            pages.append(clean_text(pg.extract_text() or ""))
    return pages


def parse_qa(pages):
    """返回 [(question, answer), ...]。"""
    # 1) 展开成行
    lines = []
    for t in pages:
        for ln in t.split("\n"):
            ln = ln.rstrip()
            if ln.strip():
                lines.append(ln)

    # 2) 问答状态机：每个以 ？/? 结尾的行是「问题」边界，
    #    其前的行是「答案」；问句换行时，前驱的短行（无句末标点）回贴到问题。
    blocks = []  # ("Q", text) / ("A", text)
    cur = []     # 累积答案行
    for ln in lines:
        if ln.endswith("？") or ln.endswith("?"):
            answer_lines = list(cur)
            # 回贴问句前缀：仅紧邻 ？ 的上一行；短行且无句末标点，排除编号/项目符号行
            q_prefix = []
            while (answer_lines and len(q_prefix) < 1
                   and len(answer_lines[-1]) <= 55
                   and answer_lines[-1][-1] not in "。！？?"
                   and not re.match(r"^\d+[\.\)、）]", answer_lines[-1])
                   and not answer_lines[-1].startswith(("•", "-", "—"))):
                q_prefix.insert(0, answer_lines.pop())
            answer = "\n".join(answer_lines).strip()
            if answer:
                blocks.append(("A", answer))
            blocks.append(("Q", "\n".join(q_prefix + [ln])))
            cur = []
        else:
            cur.append(ln)
    if cur:
        blocks.append(("A", "\n".join(cur).strip()))

    # 3) 去掉开头的前言块
    if blocks and blocks[0][0] == "A":
        blocks = blocks[1:]

    # 4) 简单问答配对：每个 Q 累积其后的所有 A 片段（自然处理尾部 A、反问句切分）
    pairs = []
    cur_q = None
    cur_a = []
    for typ, txt in blocks:
        if typ == "Q":
            if cur_q is not None and cur_a:
                pairs.append((cur_q, " ".join(cur_a).strip()))
            cur_q = re.sub(r"\s+", " ", txt).strip().rstrip("？?").strip()
            cur_a = []
        else:
            at = re.sub(r"[ \t]+", " ", txt).strip()
            at = re.split(r"本资源来自面试鸭", at)[0].strip()  # 去掉 PDF 尾部推广
            if at:
                cur_a.append(at)
    if cur_q is not None and cur_a:
        pairs.append((cur_q, " ".join(cur_a).strip()))

    # 5) 终清：把"问题"实为答案片段（编号/项目符号/答：开头/代词开头、含自问自答、含多个问号）并回上一条
    final = []
    for q, a in pairs:
        is_frag = (
            re.match(r"^\d+[\.\)、）]", q)
            or q.startswith(("•", "-", "—", "答"))
            or re.match(r"^(我|你|他|她|它|我们|你们|他们|现在|接下来|这个|那个|这|那|其|该)", q)
            or "自问自答" in q
            or (q.count("？") + q.count("?")) >= 2
        )
        if is_frag:
            if final:
                final[-1] = (final[-1][0], final[-1][1] + "\n" + q + "\n" + a)
            continue
        final.append((q, a))
    return final


# 分类规则：按优先级匹配，命中即定类
CATEGORY_RULES = [
    ("模型微调与对齐", ["微调", "fine-tuning", "finetuning", "lora", "peft", "指令微调", "sft", "全参数", "rlhf", "dpo", "偏好对齐", "对齐训练"]),
    ("RAG与知识", ["rag", "检索", "向量", "embedding", "分块", "自查询", "提示压缩", "重排序", "rerank", "召回", "知识库", "向量库", "milvus", "chroma", "pinecone", "hyde"]),
    ("提示工程", ["提示", "prompt", "提示词", "上下文学习", "few-shot", "思维链", "cot", "零样本", "zer", "角色设定", "system"]),
    ("多模态与向量检索", ["多模态", "视觉", "图像", "跨模态", "clip", "文生图", "语音", "音频", "视频理解"]),
    ("Agent架构", ["agent", "智能体", "工具调用", "function calling", "规划", "react", "多智能体", "自主"]),
    ("安全与对齐", ["安全", "幻觉", "偏见", "隐私", "越狱", "价值观", "可控", "有害", "对齐"]),
    ("评估与观测", ["评估", "评测", "benchmark", "指标", "观测", "可解释", "监控", "评测集"]),
    ("模型推理与部署优化", ["推理", "量化", "蒸馏", "部署", "kv cache", "显存", "vllm", "批处理", "吞吐", "加速", "剪枝", "推理引擎", "推理优化", "并行"]),
    ("大模型预训练与原理", ["预训练", "transformer", "注意力", "attention", "自注意力", "位置编码", "激活函数", "损失函数", "训练", "梯度", "反向传播", "分词", "tokenizer", "词表", "embedding", "残差", "归一化", "layer norm", "batch"]),
    ("大模型应用与架构", ["应用", "架构", "业务", "场景", "落地", "工程", "系统设计", "微服务", "网关"]),
]


def classify(q: str, a: str) -> str:
    blob = (q + "\n" + a).lower()
    for cat, kws in CATEGORY_RULES:
        for kw in kws:
            if kw.lower() in blob:
                return cat
    return "大模型综合"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=PDF_PATH)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("抽取 PDF:", args.pdf)
    pages = extract_pages(args.pdf)
    pairs = parse_qa(pages)
    print(f"解析到问答对：{len(pairs)} 条")

    # 分类统计
    from collections import Counter
    cnt = Counter(classify(q, a) for q, a in pairs)
    print("\n=== 分类分布 ===")
    for cat, n in cnt.most_common():
        print(f"  {cat}: {n}")

    if args.dry_run:
        print("\n=== 全部问题预览（标记 ⚠️ 为疑似切分异常）===")
        for i, (q, a) in enumerate(pairs, 1):
            flag = " ⚠️短" if len(q) < 6 else ""
            print(f"[{i:2d}] 【{classify(q,a)}】{q}{flag}")
        return

    # 入库
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    cur = db.cursor()
    # 确保 keywords 列存在
    try:
        cur.execute("ALTER TABLE questions ADD COLUMN keywords TEXT DEFAULT ''")
        db.commit()
    except Exception:
        db.rollback()
    existing = cur.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    seen = set(r[0] for r in cur.execute("SELECT question_text FROM questions"))
    inserted = 0
    skipped = 0
    cats_seen = set()
    for q, a in pairs:
        if q in seen:
            skipped += 1
            continue
        seen.add(q)
        cat = classify(q, a)
        cats_seen.add(cat)
        cur.execute(
            "INSERT INTO questions (platform, category, tags, difficulty, question_text, reference_answer, created_at, images, keywords) "
            "VALUES (?,?,?,?,?,?, datetime('now'), '', ?)",
            ("mianshiya.com", cat, "", None, q, a, ""),
        )
        inserted += 1
    db.commit()
    total = cur.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    print(f"\n已插入 {inserted} 条（跳过重复 {skipped} 条；库原 {existing} -> 现 {total}）")
    print("涉及分类：", sorted(cats_seen))
    db.close()


if __name__ == "__main__":
    main()
