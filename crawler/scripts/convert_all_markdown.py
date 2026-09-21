# -*- coding: utf-8 -*-
"""全量转换：把 questions/*.md（3917 题，已按领域分好）重排为固定五段结构的 Markdown。
输出: questions_v2/full/<domain>.md  +  INDEX.md
五段结构: 高频程度★ / 考察点 / 回答框架 / 参考回答 / 常见追问
说明: 题库原始只有 简版/展开/加分点/雷区，无 考察点/框架/追问 字段；
      - 参考回答: 保留题库真实内容(简版+展开+加分点+雷区) 不丢失
      - 高频程度: 由题库自身难度评级(★数)映射
      - 考察点/回答框架/常见追问: 基于 分类+标签+答案首句 的轻量派生, 明确标注, 不编造伪专家内容
"""
import re, json
from pathlib import Path
from datetime import date

SRC = Path("G:/interview-memory/crawler/questions")
OUT = Path("G:/interview-memory/crawler/questions_v2/full")
OUT.mkdir(parents=True, exist_ok=True)

def parse_block(b: str):
    mt = re.search(r"^## \s*\d+\.\s*(.+)$", b, re.M)
    if not mt:
        return None
    title = mt.group(1).strip()
    mid = re.search(r"原题 ID：`?(q\d+)`?", b)
    qid = mid.group(1) if mid else ""

    def sec(name, nxt):
        m = re.search(rf"### {name}\s*\n(.*?)(?=\n### {nxt}\s*|\Z)", b, re.S)
        return m.group(1).strip() if m else ""

    answer = sec("答案", "解析")
    analysis = sec("解析", "难度")
    difficulty = sec("难度", "标签")
    tags_m = re.search(r"### 标签\s*\n(.+)", b, re.S)
    tags = re.findall(r"`([^`]+)`", tags_m.group(1)) if tags_m else []
    stars = difficulty.count("★")
    if stars == 0:
        stars = 3
    return {"title": title, "id": qid, "answer": answer,
            "analysis": analysis, "tags": tags, "stars": stars}

def first_sentence(txt, n=40):
    txt = re.sub(r"\s+", " ", txt).strip()
    m = re.split(r"[。！？\n]", txt)
    s = m[0].strip() if m else txt
    if len(s) > n:
        s = s[:n] + "…"
    return s

def render(category, items):
    out = [f"# {category}\n"]
    out.append(f"> 题目数量：**{len(items)}** ｜ 生成时间：{date.today().isoformat()} ｜ 格式：固定五段（高频程度 / 考察点 / 回答框架 / 参考回答 / 常见追问）\n")
    out.append("> 字段说明：参考回答=题库真实内容（简版+展开+加分点+雷区）全保留；高频程度=题库难度评级映射；考察点/回答框架/常见追问=基于分类+标签+答案首句的轻量派生并标注，非逐题专家撰写。\n")
    out.append("\n---\n")
    for i, it in enumerate(items, 1):
        stars = "★" * it["stars"] + "☆" * (5 - it["stars"])
        tagstr = " ".join(f"`{t}`" for t in it["tags"]) or "（无）"
        fw = first_sentence(it["answer"]) if it["answer"] else ""
        out.append(f"\n## {i}. {it['title']}\n")
        out.append(f"\n> **高频程度**：{stars}　|　**原题 ID**：`{it['id']}`　|　**标签**：{tagstr}\n")
        kd = (f"【由分类/标签推断】{category} 方向，重点考察 "
              + ("、".join(it["tags"][:4]) if it["tags"] else "该主题")
              + " 的理解与工程落地、边界场景的掌握。")
        out.append(f"\n**考察点**：{kd}\n")
        if fw:
            out.append(f"\n**回答框架**：{fw}\n")
        out.append("\n**参考回答**\n")
        if it["answer"]:
            out.append(f"{it['answer']}\n")
        if it["analysis"]:
            out.append(f"\n{it['analysis']}\n")
        out.append("\n**常见追问**\n")
        out.append("\n> 【题库未含追问，以下为基于标签的延伸方向，建议面试前自测】\n")
        if it["tags"]:
            out.append(f"- 结合 `{it['tags'][0]}` 的落地细节与踩坑经验？\n")
            if len(it["tags"]) > 1:
                out.append(f"- `{it['tags'][0]}` 与 `{it['tags'][1]}` 的取舍与权衡？\n")
            out.append(f"- 在真实项目中如何验证 / 量化这一点的效果？\n")
        else:
            out.append(f"- 该主题在真实项目中的落地细节与踩坑经验？\n")
            out.append(f"- 相近技术的取舍与权衡？\n")
        out.append("\n---\n")
    return "".join(out)

def main():
    files = sorted([f for f in SRC.glob("*.md") if f.name != "README.md"])
    total = 0
    index = ["# 面试题库 · 全量五段结构版（INDEX）\n",
             f"> 生成时间：{date.today().isoformat()} ｜ 来源：questions-bank.json 全库 3917 题 ｜ 按领域拆分\n",
             "> 每题固定五段：高频程度★ / 考察点 / 回答框架 / 参考回答 / 常见追问\n",
             "\n## 领域索引\n"]
    for f in files:
        text = f.read_text(encoding="utf-8")
        h1 = re.search(r"^#\s+(.+)$", text, re.M)
        category = h1.group(1).strip() if h1 else f.stem
        blocks = re.split(r"\n---\n", text)
        items = []
        for b in blocks:
            it = parse_block(b)
            if it:
                items.append(it)
        if not items:
            continue
        md = render(category, items)
        (OUT / f.name).write_text(md, encoding="utf-8")
        total += len(items)
        index.append(f"- [{category}]({f.stem}.md)（{len(items)}）\n")
    index.append(f"\n**合计：{total} 题**\n")
    (OUT / "INDEX.md").write_text("".join(index), encoding="utf-8")

    (Path("G:/interview-memory/crawler/data/tmp/conv_report.txt")
     .write_text(f"domains={len(files)}\ntotal={total}\n", encoding="utf-8"))

if __name__ == "__main__":
    main()
