"""questions_v2 到应用数据模型的导入前校验。"""
import os
import sys


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
