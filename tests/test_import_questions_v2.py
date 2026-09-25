"""questions_v2 到应用数据模型的导入前校验。"""
import os
import shutil
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import import_questions_v2 as importer  # noqa: E402


def test_curated_questions_v2_is_complete_and_answered():
    questions = list(importer.load_questions(importer.DEFAULT_SOURCE))
    assert len(questions) == importer.CURATED_QUESTION_COUNT
    assert len({item["question_text"] for item in questions}) == len(questions)
    assert all(item["reference_answer"] for item in questions)
    assert {item["category"] for item in questions} == set(importer.DOMAIN_LABELS.values())


def test_missing_domain_is_rejected_before_import(tmp_path):
    (tmp_path / "redis.jsonl").write_text('{"id":"q1","title":"题目","answer":"答案"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="分类文件不完整"):
        list(importer.load_questions(tmp_path))


def test_truncated_corpus_is_rejected_before_import(tmp_path):
    for domain in importer.DOMAIN_LABELS:
        source = importer.DEFAULT_SOURCE / f"{domain}.jsonl"
        shutil.copyfile(source, tmp_path / source.name)
    redis = tmp_path / "redis.jsonl"
    redis.write_text("\n".join(redis.read_text(encoding="utf-8").splitlines()[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="题库数量不符"):
        list(importer.load_questions(tmp_path))
