#!/usr/bin/env python3
"""将已审核的 questions_v2 JSONL 题库安全导入应用数据库。

默认读取 crawler/questions_v2/authored/：该目录是 curate_full_v2.py 的最终来源，
与 full_v2/ 中渲染出的当前题库一一对应。默认按题面去重，可重复执行；
--replace 只替换 platform=questions_v2 的题，并在发现学习记录关联时拒绝执行。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "crawler" / "questions_v2" / "authored"
CURATED_QUESTION_COUNT = 2582

DOMAIN_LABELS = {
    "agent": "Agent 架构与工程",
    "ai-product": "AI 产品与应用",
    "algorithm": "算法与数据结构",
    "behavioral": "行为与项目面试",
    "design-pattern": "设计模式",
    "distributed": "分布式系统",
    "engineering": "工程化与 DevOps",
    "evaluation": "评估与可观测",
    "frontend": "前端工程",
    "general": "通用技术与职业问题",
    "go": "Go",
    "java": "Java",
    "llm-basics": "大模型与 AI 基础概念",
    "llm-posttraining": "大模型后训练（微调/对齐）",
    "llm-pretraining": "大模型预训练",
    "mq": "消息队列",
    "multimodal": "多模态",
    "mongodb": "MongoDB",
    "mysql": "MySQL",
    "os-network": "操作系统与网络",
    "prompt": "提示工程",
    "puzzle": "智力与开放题",
    "rag": "RAG 与向量检索",
    "redis": "Redis",
    "safety": "安全与沙箱",
    "system-design": "系统设计",
}


def load_questions(source: Path, *, with_source_id: bool = False) -> Iterable[dict]:
    """读取完整的审核题库；保留 JSONL 文件名作为最终分类依据。"""
    if not source.is_dir():
        raise FileNotFoundError(f"题库目录不存在: {source}")
    # 下划线前缀是 authored/ 里的临时批次（如 _b.jsonl），不参与 curate_full_v2.py 渲染，
    # 不属于 full_v2 正式题库，导入时必须排除，否则会多出未审核的题目。
    files = sorted(p for p in source.glob("*.jsonl") if not p.name.startswith("_"))
    expected_files = {f"{domain}.jsonl" for domain in DOMAIN_LABELS}
    actual_files = {file.name for file in files}
    if actual_files != expected_files:
        raise ValueError(
            f"题库分类文件不完整或含未知分类: 缺少 {sorted(expected_files - actual_files)}，"
            f"多出 {sorted(actual_files - expected_files)}"
        )
    questions = []
    seen_ids = set()
    seen_titles = set()
    for file in files:
        domain = file.stem
        category = DOMAIN_LABELS.get(domain, domain)
        for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"无效 JSONL：{file}:{number}") from exc
            title = str(item.get("title") or "").strip()
            answer = str(item.get("answer") or "").strip()
            if not title or not answer:
                raise ValueError(f"题目或答案为空：{file}:{number}")
            qid = str(item.get("id") or "").strip()
            if not qid or qid in seen_ids:
                raise ValueError(f"题目 ID 为空或重复：{file}:{number} ({qid})")
            if title in seen_titles:
                raise ValueError(f"题面重复：{file}:{number} ({title})")
            seen_ids.add(qid)
            seen_titles.add(title)
            freq = item.get("freq")
            tags = [category]
            if isinstance(freq, int) and freq >= 4:
                tags.append("高频")
            question = {
                "platform": "questions_v2",
                "category": category,
                "tags": ",".join(tags),
                # 原始数据并不定义难度；固定中等，避免把“出现频率”误作难度。
                "difficulty": 2,
                "question_text": title,
                "reference_answer": answer,
                "keywords": str(item.get("kaodian") or "").strip(),
            }
            if with_source_id:
                question["source_id"] = qid
            questions.append(question)
    if len(questions) != CURATED_QUESTION_COUNT:
        raise ValueError(
            f"题库数量不符：实际 {len(questions)}，预期 {CURATED_QUESTION_COUNT}；"
            "请核对审核题库后再更新预期数量"
        )
    yield from questions


def import_questions(
    source: Path, dry_run: bool = False, replace: bool = False,
) -> tuple[int, int, int]:
    """导入题库，返回 (总数, 新增数, 去重跳过数)。

    ``replace`` 仅用于把已导入的 questions_v2 批次同步到审核后的源题库。
    为保护学习进度，任何关联的作答、错题、复习或笔记记录都会使替换失败。
    """
    questions = list(load_questions(source))
    if dry_run:
        return len(questions), 0, 0

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from backend.db import SessionLocal, init_db
    from backend.models import Question, QuestionNote, ReviewSchedule, Submission, WrongBook

    init_db()
    db = SessionLocal()
    try:
        if replace:
            current_ids = [
                row[0]
                for row in db.query(Question.id)
                .filter(Question.platform == "questions_v2")
                .all()
            ]
            if current_ids:
                dependent_count = sum((
                    db.query(Submission).filter(Submission.question_id.in_(current_ids)).count(),
                    db.query(WrongBook).filter(WrongBook.question_id.in_(current_ids)).count(),
                    db.query(ReviewSchedule).filter(ReviewSchedule.question_id.in_(current_ids)).count(),
                    db.query(QuestionNote).filter(QuestionNote.question_id.in_(current_ids)).count(),
                ))
                if dependent_count:
                    raise ValueError(
                        "拒绝替换 questions_v2：已有学习记录关联这些题目，请先完成迁移。"
                    )
                db.query(Question).filter(Question.platform == "questions_v2").delete(
                    synchronize_session=False
                )
            db.add_all(Question(**item) for item in questions)
            db.commit()
            return len(questions), len(questions), 0

        existing = {text for (text,) in db.query(Question.question_text).all()}
        new_rows = [item for item in questions if item["question_text"] not in existing]
        db.add_all(Question(**item) for item in new_rows)
        db.commit()
        return len(questions), len(new_rows), len(questions) - len(new_rows)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="导入已审核的 questions_v2 题库")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="JSONL 题库目录")
    parser.add_argument("--dry-run", action="store_true", help="仅校验题库，不写入数据库")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="安全替换已导入的 questions_v2 批次；存在关联学习记录时拒绝执行",
    )
    args = parser.parse_args()
    total, imported, skipped = import_questions(args.source, args.dry_run, args.replace)
    if args.dry_run:
        print(f"校验通过：{total} 道题")
    else:
        print(f"导入完成：总计 {total}，新增 {imported}，已存在跳过 {skipped}")
        if skipped and not args.replace:
            print("注意：增量导入不会更新已有答案。同步本地 SQLite 请使用 scripts/sync_questions_v2.py，先预览再 --write。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
