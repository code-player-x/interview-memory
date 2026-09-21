#!/usr/bin/env python3
"""把用户飞书知识库(只读)的八股文批量并入 questions-bank.json。
读取 data/tmp/feishu/doc_*.md（已由 lark-cli docs +fetch 抓取，不修改飞书），
按文档标题映射到 7 大分类，抽取 ## 级问题 + **回答** 正文，生成四段式答案，
与现有题库做 0.85 跳过 / 0.70 待复核 去重后并入。
用法：python scripts/merge_feishu_bank.py [--dry-run] [--doc N]
"""
import json
import re
import sys
import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK_PATH = ROOT / "data" / "questions-bank.json"
FEISHU_ROOT = "https://my.feishu.cn/wiki/LlBswlr0mimN7hkxRxwczPYGnjD"
TMP = ROOT / "data" / "tmp" / "feishu"

# doc index -> (显示名, 分类, node_token, 短标签)
DOC_META = {
    0: ("简历专项题库", "项目深挖", "NQtPw5n7eih9MckHffLciPKgnIb", "简历"),
    1: ("系统设计面试题题库", "架构设计", "LhUbwRIwLi26WjkuDsfcybrJnec", "系统设计"),
    2: ("Kafka面试题整理", "后端八股", "PDSswRcURiUImOk6jh5cUuCXnur", "Kafka"),
    3: ("Golang面试题整理", "后端八股（Go）", "M62HwzQqPilNyckIYdKcGYGwnTe", "Go"),
    4: ("Redis面试题整理", "后端八股", "A11CwFoFOiuaEdkTgCqceWoOnBe", "Redis"),
    5: ("Mysql面试题整理", "后端八股", "LGFvwYnMoiAzvIkHwlhcieu5nuo", "Mysql"),
    6: ("操作系统面试题整理", "后端八股", "V5CMwNSAjizbaNkpvfNchvKNnbh", "操作系统"),
    7: ("计算机网络面试题整理", "后端八股", "A3ilwDF2eiXFDrkEu4LcAySyncb", "计算机网络"),
    8: ("智力题题库", "行为与HR", "RO9RwVoM1i5fvok1kkucjS3YnXe", "智力题"),
    9: ("docker面试题整理", "工程落地", "CBr2wHlFJi3KJwkXMbQcUyDinIe", "docker"),
    10: ("K8s面试题整理", "工程落地", "KWedwL7FnieaTBkPlzccsn2anCc", "K8s"),
    11: ("分布式面试题整理", "架构设计", "A1RmwstHWiruHWkTIpVc5ZjTnJb", "分布式"),
    12: ("设计模式知识库", "概念基础", "XxqNwLD1cisEWrkePZccndVLnhg", "设计模式"),
    13: ("系统设计题库", "架构设计", "FFOzwOYfIi3OELkpxRUcapm2n2g", "系统设计"),
    14: ("海量数据处理题库", "架构设计", "ARRNwYEmAibmWnklzgycHdtcnPg", "海量数据"),
    15: ("架构设计题库", "架构设计", "XkEVwrDeCi1XKGkEP8Uc9yMznUd", "架构设计"),
    16: ("其他", None, "YzHBw2NpTixjFRkBVHDcY4KDnyg", "其他"),
    17: ("HR面问题准备", "行为与HR", "JkoqwNbUbiCCEpkOk3McMjJunsE", "HR面"),
    18: ("未命名文档A", None, "Teb3wwImQi7vPTkPq7ocV7Qbn5n", "未命名A"),
    19: ("MongoDB面试题库", "后端八股", "BEyzwmZoOiYd5fkyHsnczyn6nfM", "MongoDB"),
}

SKIP = {16, 18}  # 空文档

IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
CALL_RE = re.compile(r"</?callout[^>]*>", re.I)


def normalize(text: str) -> str:
    t = text.lower()
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"[，。、；：？！,.?;:!“”\"'()（）\[\]【】{}<>《》\/\\|#@*~`\-_=+^$%&]", "", t)
    return t


def clean_md(text: str) -> str:
    text = IMG_RE.sub("", text)
    text = CALL_RE.sub("", text)
    text = re.sub(r"<[^>]+>", "", text)  # 去掉 <p>/<b>/<cite>/<readonly-block>/<br> 等飞书标签
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"^>\s?", "", text, flags=re.M)
    text = re.sub(r"`", "", text)
    lines = [ln.strip() for ln in text.splitlines()]
    out = []
    prev_blank = False
    for ln in lines:
        if ln == "":
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            out.append(ln)
            prev_blank = False
    return "\n".join(out).strip()


def parse_doc(text: str):
    lines = text.splitlines()
    questions = []
    cur = None
    section = None
    for line in lines:
        m1 = re.match(r"^#\s+(.+)$", line)
        if m1:
            section = m1.group(1).strip()
            continue
        m2 = re.match(r"^##\s+(.+)$", line)
        if m2:
            if cur:
                questions.append(cur)
            cur = {"q": m2.group(1).strip(), "section": section, "lines": []}
            continue
        if cur is not None:
            cur["lines"].append(line)
    if cur:
        questions.append(cur)
    return questions


def split_sections(lines):
    secs = {"分析": "", "回答": "", "推荐学习": "", "总结": "", "callout": ""}
    cur_key = None
    buf = []

    def flush():
        if cur_key:
            secs[cur_key] = "\n".join(buf).strip()

    for line in lines:
        s = line.strip()
        s_clean = re.sub(r"\*+", "", s).strip()
        if s_clean == "分析":
            flush(); cur_key = "分析"; buf = []
        elif s_clean == "回答":
            flush(); cur_key = "回答"; buf = []
        elif s_clean == "推荐学习":
            flush(); cur_key = "推荐学习"; buf = []
        elif s_clean.startswith("总结"):
            flush(); cur_key = "总结"; buf = []
        elif s.lower().startswith("<callout"):
            flush(); cur_key = "callout"; buf = []
        elif s.lower().startswith("</callout"):
            flush(); cur_key = None; buf = []
        else:
            if cur_key:
                buf.append(line)
    flush()
    return secs


def first_sentence(text, limit=120):
    text = text.strip()
    if not text:
        return ""
    # 优先取第一个非空的"要点行"或句子
    for sep in ["。", "！", "？", "\n", "；"]:
        idx = text.find(sep)
        if 0 < idx < limit:
            return text[: idx + 1].strip()
    return text[:limit].strip()


def extract_landmine(text):
    # 从分析/回答里抓含"坑/误区/不要/避免/注意/错误/陷阱"的句子
    sentences = re.split(r"(?<=[。！？])", text)
    hits = []
    keys = ["坑", "误区", "不要", "避免", "注意", "错误", "陷阱", "谨慎", "忌", "滥用", "误用", "避免"]
    for s in sentences:
        s = s.strip()
        if 6 <= len(s) <= 60 and any(k in s for k in keys):
            hits.append(s)
        if len(hits) >= 2:
            break
    return "；".join(hits)


def build_entry(doc_idx, q, sections):
    name, category, token, tag = DOC_META[doc_idx]
    raw_answer = sections.get("回答", "").strip()
    if not raw_answer:
        # 没有 回答 标记：取「分析」之后的正文（去掉 分析/推荐学习 区块）
        body = "\n".join(q["lines"])
        parts = re.split(r"\n\s*\*?分析\*?\s*\n", body)
        raw = parts[-1].strip() if len(parts) > 1 else body.strip()
        raw = re.split(r"\n\s*\*?推荐学习\*?\s*\n", raw)[0].strip()
        raw_answer = raw
    answer_full = clean_md(raw_answer)
    if not answer_full:
        return None
    # 简版
    callout = clean_md(sections.get("callout", ""))
    brief = (callout[:120] if callout else first_sentence(answer_full, 120))
    if not brief:
        brief = answer_full[:120]
    # 加分点
    summary = clean_md(sections.get("总结", ""))
    rec = clean_md(sections.get("推荐学习", ""))
    bonus = summary
    if rec and not bonus:
        # 抽取链接标题作为延伸阅读
        links = re.findall(r"\[([^\]]+)\]\([^)]+\)", rec)
        bonus = "延伸阅读：" + "；".join(links) if links else rec[:120]
    # 雷区
    landmine = extract_landmine(sections.get("分析", "") + "\n" + raw_answer)
    difficulty = "★★★" if "必问" in q["q"] else "★★☆"
    content = q["q"].rstrip("？?").strip()
    tags = [tag]
    if q.get("section"):
        sec = re.sub(r"\*\*", "", q["section"]).strip()
        if sec:
            tags.append(sec)
    entry = {
        "category": category,
        "type": "essay",
        "content": content,
        "source": f"飞书知识库·{name}",
        "difficulty": difficulty,
        "tags": tags,
        "status": "新增",
        "answer": {
            "简版": brief,
            "展开": answer_full,
            "加分点": bonus,
            "雷区": landmine,
        },
        "leetcode_url": "",
        "sources": [f"https://my.feishu.cn/wiki/{token}"],
        "wiki_node_token": token,
        "wiki_url": f"https://my.feishu.cn/wiki/{token}",
    }
    if len(answer_full) < 30:
        entry["status"] = "待复核"
    return entry


def main():
    dry = "--dry-run" in sys.argv
    only = None
    for a in sys.argv[1:]:
        if a.startswith("--doc"):
            only = int(a.split("=")[1])
    bank = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    existing_norms = [normalize(it.get("content", "")) for it in bank["items"]]
    existing_norm_set = set(existing_norms)

    new_entries = []
    seen_norms = set()
    stats = {"parsed": 0, "skip_dup": 0, "review": 0, "added": 0, "empty": 0}
    cat_count = {}

    idxs = [only] if only is not None else sorted(DOC_META.keys() - SKIP)
    for di in idxs:
        meta = DOC_META[di]
        p = TMP / f"doc_{di}.md"
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        qs = parse_doc(text)
        for q in qs:
            stats["parsed"] += 1
            entry = build_entry(di, q, split_sections(q["lines"]))
            if entry is None:
                stats["empty"] += 1
                continue
            norm = normalize(entry["content"])
            # 批内去重
            if norm in seen_norms or norm in existing_norm_set:
                stats["skip_dup"] += 1
                continue
            # 相似度
            max_ratio = 0.0
            for en in existing_norms:
                r = difflib.SequenceMatcher(None, norm, en).ratio()
                if r > max_ratio:
                    max_ratio = r
            if max_ratio >= 0.85:
                stats["skip_dup"] += 1
                continue
            if max_ratio >= 0.70:
                entry["status"] = "待复核"
                stats["review"] += 1
            seen_norms.add(norm)
            cat = entry["category"]
            cat_count[cat] = cat_count.get(cat, 0) + 1
            new_entries.append(entry)
            stats["added"] += 1

    print("=== DRY RUN" if dry else "=== MERGE")
    print("parsed:", stats["parsed"], "empty:", stats["empty"],
          "skip_dup:", stats["skip_dup"], "review(0.70-0.85):", stats["review"],
          "added:", stats["added"])
    print("per-category added:", cat_count)

    if not dry:
        base = len(bank["items"])
        for i, e in enumerate(new_entries):
            e["id"] = f"q{base + i + 1:04d}"
            e["norm"] = normalize(e["content"])
            e["created_at"] = "2026-07-16"
            bank["items"].append(e)
        bank["meta"]["total"] = len(bank["items"])
        bank["meta"]["last_merged_feishu"] = "2026-07-16"
        BANK_PATH.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"WROTE bank: total now {bank['meta']['total']}")
    else:
        # 打印前 2 条样例
        for e in new_entries[:2]:
            print("\n--- SAMPLE ---")
            print("Q:", e["content"])
            print("cat:", e["category"], "tags:", e["tags"], "diff:", e["difficulty"], "status:", e["status"])
            print("简版:", e["answer"]["简版"][:80])
            print("展开[:120]:", e["answer"]["展开"][:120])
            print("加分点:", e["answer"]["加分点"][:80])
            print("雷区:", e["answer"]["雷区"][:80])


if __name__ == "__main__":
    main()
