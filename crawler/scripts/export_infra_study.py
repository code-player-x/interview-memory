#!/usr/bin/env python3
"""Render reviewed AI Infra questions in the source learning-map order.

Inputs are curated JSONL, not automatically extracted or generated answers.
Example (project root):
  python crawler/scripts/export_infra_study.py --questions reviewed.jsonl \
      --posts posts.jsonl --output ai-infra-study.md
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

DEFAULT_MAP = Path(__file__).resolve().parents[1] / "config" / "ai-infra-map-order.json"
START_DATE = date(2026, 9, 18)
END_DATE = date(2026, 11, 18)


def read_jsonl(path: Path):
    with path.open(encoding="utf-8-sig") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number}: 无效 JSON") from exc
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{number}: 每行必须是 JSON 对象")
            yield item


def nonempty(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空字符串")
    return value.strip()


def link(title: str, url: str) -> str:
    title = nonempty(title, "链接标题")
    url = nonempty(url, "链接地址")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or any(ch.isspace() for ch in url):
        raise ValueError(f"无效 HTTP(S) 链接: {url}")
    title = title.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
    title = re.sub(r"\s+", " ", title)
    return f"[{title}](<{url.replace('>', '%3E').replace('<', '%3C')}>)"


def question_key(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in normalized if not ch.isspace() and not unicodedata.category(ch).startswith("P"))


def prepare(question_files: list[Path], posts_file: Path, map_file: Path, start=START_DATE, end=END_DATE):
    mapping = json.loads(map_file.read_text(encoding="utf-8-sig"))
    domains = mapping["children"]
    groups = {group["id"]: domain["id"] for domain in domains for group in domain["children"]}
    if len(groups) != sum(len(domain["children"]) for domain in domains):
        raise ValueError("知识图谱存在重复 group id")
    posts = {}
    for post in read_jsonl(posts_file):
        post_id = str(post.get("id", "")).strip()
        if not post_id:
            raise ValueError("来源帖子缺少 id")
        if post_id in posts and posts[post_id] != post:
            raise ValueError(f"来源帖子 id 重复且内容冲突: {post_id}")
        posts[post_id] = post
    merged = {}
    for path in question_files:
        for item in read_jsonl(path):
            question = nonempty(item.get("question"), "question")
            answer = nonempty(item.get("answer"), f"{question}: answer")
            domain_id, group_id = item.get("domain_id"), item.get("group_id")
            if group_id not in groups or groups[group_id] != domain_id:
                raise ValueError(f"{question}: 无效 domain/group: {domain_id}/{group_id}")
            source_ids = item.get("source_ids")
            if not isinstance(source_ids, list) or not source_ids:
                raise ValueError(f"{question}: source_ids 必须是非空列表")
            source_ids = list(dict.fromkeys(str(value) for value in source_ids))
            for source_id in source_ids:
                if source_id not in posts:
                    raise ValueError(f"{question}: 找不到来源 {source_id}")
                post = posts[source_id]
                try:
                    published = date.fromisoformat(post.get("date", ""))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"来源 {source_id} 的发布日期无效或缺失") from exc
                if not start <= published <= end:
                    raise ValueError(f"来源 {source_id} 发布时间 {published} 不在指定范围内")
                link(post.get("title"), post.get("url"))
            refs = item.get("references", [])
            if not isinstance(refs, list):
                raise ValueError(f"{question}: references 必须是列表")
            for ref in refs:
                if not isinstance(ref, dict):
                    raise ValueError(f"{question}: reference 必须是对象")
                link(ref.get("title"), ref.get("url"))
            key = question_key(question)
            if not key:
                raise ValueError("question 不能只包含标点")
            if key not in merged:
                merged[key] = dict(question=question, answer=answer, domain_id=domain_id,
                                   group_id=group_id, source_ids=source_ids, references=list(refs))
            else:
                existing = merged[key]
                existing["source_ids"] = list(dict.fromkeys(existing["source_ids"] + source_ids))
                old_urls = {ref["url"] for ref in existing["references"]}
                for ref in refs:
                    if ref["url"] not in old_urls:
                        existing["references"].append(ref)
                        old_urls.add(ref["url"])
                # Preserve the first reviewed answer and assignment deterministically.
    return mapping, list(merged.values()), posts


def render(mapping: dict, questions: list[dict], posts: dict, start=START_DATE, end=END_DATE) -> str:
    cited = {source_id for item in questions for source_id in item["source_ids"]}
    lines = [
        "# AI Infra 岗位面试题学习册", "",
        f"> 来源发布日期范围：{start.isoformat()} 至 {end.isoformat()}（含首尾日期）。", "",
        f"本册整理 **{len(questions)} 道题**，引用 **{len(cited)} 篇来源帖子**。分类及子分类严格按《AI Infra 学习图谱》的原始顺序排列。", "",
        "日期范围依据帖子**发布时间**，不是实际面试日期；检索覆盖配置关键词和有限搜索页，不能视为全站穷尽。", "",
        "检索不限地域。正文或标题明确标注为时间范围之外的旧面试已剔除；未明确面试日期的来源按发布日期纳入。", "",
        "仅收录原帖或检索摘要里明确出现的问题。详情获取失败时只使用完整可辨的题目，不根据摘要补造问题；各条来源标注提取依据。", "",
        "题目标题可能经过归纳改写；每题的**生成参考回答**由本次整理补充，不是原帖提供的标准答案，也不代表面试官认可的唯一解法。请结合参考资料验证具体版本行为。", "",
        "相同题面经标准化去重后合并来源，保留首次整理的回答与分类；相近但不同的题目不强行合并。未找到匹配题的分类明确标记为“本次未收录”。", "",
        "## 分类目录", "",
        "| 顺序 | 分类 | 题数 |", "| --- | --- | ---: |",
    ]
    for index, domain in enumerate(mapping["children"], 1):
        count = sum(q["domain_id"] == domain["id"] for q in questions)
        lines.append(f"| {index:02d} | [{domain['title']}](#domain-{domain['id']}) | {count} |")
    number = 0
    for di, domain in enumerate(mapping["children"], 1):
        lines.extend(["", f'<a id="domain-{domain["id"]}"></a>', "", f"## {di:02d} · {domain['title']}", ""])
        for gi, group in enumerate(domain["children"], 1):
            lines.extend([f"### {di:02d}.{gi:02d} · {group['title']}", ""])
            matching = [item for item in questions if item["group_id"] == group["id"]]
            if not matching:
                lines.extend(["本次未收录。", ""])
                continue
            for item in matching:
                number += 1
                heading = re.sub(r"\s+", " ", item["question"])
                lines.extend([f'<a id="q{number:03d}"></a>', "", f"#### Q{number:03d} · {heading}", "", "**生成参考回答（整理补充）**", "", item["answer"], "", "**面经来源**", ""])
                for source_id in item["source_ids"]:
                    post = posts[source_id]
                    evidence = {"full_text": "主帖全文", "image_verified": "原帖配图（已逐题核对）",
                                "full_text_and_images": "原帖正文及配图"}.get(post.get("detail_status"), "检索摘要")
                    lines.append(f"- {link(post['title'], post['url'])} · 发布日期：{post['date']} · 题目提取依据：{evidence}")
                lines.extend(["", "**参考资料**", ""])
                if item["references"]:
                    lines.extend(f"- {link(ref['title'], ref['url'])}" for ref in item["references"])
                else:
                    lines.append("本题未附独立参考资料，可结合本分类在知识图谱中的资料继续核对。")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, action="append", required=True)
    parser.add_argument("--posts", type=Path, required=True)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--date-from", type=date.fromisoformat, default=START_DATE)
    parser.add_argument("--date-to", type=date.fromisoformat, default=END_DATE)
    args = parser.parse_args()
    if args.date_from > args.date_to:
        parser.error("开始日期须早于或等于结束日期")
    mapping, questions, posts = prepare(args.questions, args.posts, args.map, args.date_from, args.date_to)
    document = render(mapping, questions, posts, args.date_from, args.date_to)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(document, encoding="utf-8", newline="\n")
    temporary.replace(args.output)
    print(f"Exported {len(questions)} questions to {args.output}")


if __name__ == "__main__":
    main()
