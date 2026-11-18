"""Regression checks for category cards and single-question memorization."""

from pathlib import Path

from backend import app as appmod


FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def test_mongodb_category_description_does_not_match_go():
    assert appmod._category_description("MongoDB") == "文档数据库、BSON 与数据建模面试题"
    assert appmod._category_description("Go") == "Go 语言并发与工程实践面试题"


def test_memorize_controls_describe_single_question_navigation():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")

    assert 'id="memSize"' not in html
    assert 'id="memPrev">← 上一题</button>' in html
    assert 'id="memNext">下一题 →</button>' in html
    assert 'getElementById("memSize")' not in script
