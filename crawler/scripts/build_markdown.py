# -*- coding: utf-8 -*-
"""把 6 份内容 JSON 合并为单文件 Markdown 题库（带目录 + 固定五段结构）。
输出: questions_v2/AI应用开发高频面试题-2026版.md
"""
import json, re, sys
from pathlib import Path
from datetime import date

V2 = Path("G:/interview-memory/crawler/questions_v2")
ORDER = ["rag", "agent", "llm_basic", "training", "misc_ai", "serving"]

def load(key):
    p = V2 / f"{key}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))

def main():
    problems = []
    categories = []  # (category_name, [(question_dict, global_no)])
    gno = 0
    for key in ORDER:
        data = load(key)
        if not data:
            problems.append(f"[缺失] {key}.json 未生成")
            continue
        for cat in data.get("categories", []):
            name = cat.get("category", "未命名分类")
            qs = []
            for q in cat.get("questions", []):
                gno += 1
                # 校验
                for fld in ("id", "title", "freq", "kaodian", "framework", "answer", "followups"):
                    if fld not in q or q.get(fld) in (None, "", [], {}):
                        problems.append(f"[字段空] {name} #{gno} 缺 {fld}")
                if not (1 <= int(q.get("freq", 0)) <= 5):
                    problems.append(f"[freq越界] {name} #{gno} freq={q.get('freq')}")
                if not isinstance(q.get("followups"), list) or len(q["followups"]) < 1:
                    problems.append(f"[追问] {name} #{gno} 追问不足")
                qs.append((q, gno))
            categories.append((name, qs))

    # 渲染
    out = []
    out.append("# AI 应用开发高频面试题（2026 版）\n")
    total = gno
    out.append(f"> 面向 **Go 后端 → 大模型应用 / 训练** 转型面试　｜　共 **{total}** 题　｜　生成日期：{date.today().isoformat()}\n")
    out.append("> 来源：从 3917 题总库按领域抽取、由面试官视角重写的「考察点 / 回答框架 / 参考回答 / 常见追问」精炼集。\n")
    out.append("\n## 目录\n")
    for i, (name, qs) in enumerate(categories, 1):
        anchor = f"cat-{i}"
        out.append(f"- <a id=\"toc-{i}\"></a>[{name}](#{anchor})（{len(qs)}）\n")
    out.append("\n---\n")

    for i, (name, qs) in enumerate(categories, 1):
        out.append(f"\n<a id=\"cat-{i}\"></a>\n## {name}\n")
        out.append("\n---\n")
        for q, no in qs:
            stars = "★" * int(q.get("freq", 3)) + "☆" * (5 - int(q.get("freq", 3)))
            out.append(f"\n<a id=\"q-{no}\"></a>\n### {no}. {q.get('title','')}\n")
            out.append(f"\n> **高频程度**：{stars}　|　**原题 ID**：`{q.get('id','')}`\n")
            out.append(f"\n**考察点**：{q.get('kaodian','')}\n")
            out.append(f"\n**回答框架**：{q.get('framework','')}\n")
            ans = q.get("answer", "").strip()
            ans = re.sub(r"\n{3,}", "\n\n", ans)
            out.append(f"\n**参考回答**\n\n{ans}\n")
            fus = q.get("followups", [])
            if fus:
                out.append("\n**常见追问**\n")
                for f in fus:
                    out.append(f"{f}\n")
                # 用有序列表形式更清晰
                out.append("\n")
            out.append("\n")

    md = "".join(out)
    dest = V2 / "AI应用开发高频面试题-2026版.md"
    dest.write_text(md, encoding="utf-8")

    rep = []
    rep.append(f"total_questions={total}")
    rep.append(f"categories={len(categories)}")
    rep.append(f"output_bytes={len(md.encode('utf-8'))}")
    rep.append(f"problems={len(problems)}")
    if problems:
        rep.append("--- 问题清单 ---")
        rep.extend(problems[:200])
    (Path("G:/interview-memory/crawler/data/tmp/md_report.txt")
     .write_text("\n".join(rep), encoding="utf-8"))

if __name__ == "__main__":
    main()
