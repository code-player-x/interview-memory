"""questions_v2 到应用数据模型的导入前校验。"""
import os
import sys
import json

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


@pytest.mark.parametrize("replace", [False, True])
def test_import_deduplicates_same_batch_and_preserves_first_answer(tmp_path, monkeypatch, replace):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend import db as database
    from backend.models import Question

    source = tmp_path / "source"
    source.mkdir()
    (source / "agent.jsonl").write_text("\n".join(json.dumps(item) for item in [
        {"title": "重复题", "answer": "第一份答案"},
        {"title": "重复题", "answer": "第二份答案"},
        {"title": "已有题", "answer": "更新答案"},
    ]), encoding="utf-8")
    (source / "go.jsonl").write_text(json.dumps({
        "title": "重复题", "answer": "另一分类答案",
    }), encoding="utf-8")

    # 独立内存库，不依赖全局 API 测试库或用户配置。
    engine = create_engine("sqlite://")
    database.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    monkeypatch.setattr(database, "init_db", lambda: None)
    try:
        with session_factory() as session:
            session.add(Question(platform="questions_v2", question_text="已有题", reference_answer="原答案"))
            session.commit()

        assert importer.import_questions(source, replace=replace) == (
            (4, 2, 2) if replace else (4, 1, 3)
        )
        with session_factory() as session:
            rows = {row.question_text: row for row in session.query(Question).all()}
            assert session.query(Question).count() == 2
            assert rows["重复题"].reference_answer == "第一份答案"
            assert rows["重复题"].category == importer.DOMAIN_LABELS["agent"]
            assert rows["已有题"].reference_answer == ("更新答案" if replace else "原答案")
        assert importer.import_questions(source) == (4, 0, 4)
    finally:
        engine.dispose()
