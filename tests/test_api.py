"""interview-memory 后端单元测试。

运行：pytest tests/ -q
"""
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

# 使用临时数据库
TMP_DB = os.path.join(tempfile.gettempdir(), "im_test.db")
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)
os.environ["DATABASE_URL"] = "sqlite:///" + TMP_DB
os.environ["AGENT_JUDGE_URL"] = ""
os.environ["LLM_BASE_URL"] = ""

sys.path.insert(0, r"G:\interview-memory")

import backend.app as appmod
from backend.db import SessionLocal, engine, Base
from backend import models


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(appmod.app) as c:
        yield c
    try:
        appmod.scheduler.shutdown(wait=False)
    except Exception:
        pass
    engine.dispose()
    if os.path.exists(TMP_DB):
        os.remove(TMP_DB)


def test_import_and_list(client):
    r = client.post("/api/questions/import", json={
        "platform": "test", "category": "并发", "tags": "volatile,线程安全",
        "question_text": "volatile 的作用？",
        "reference_answer": "保证可见性与禁止指令重排",
        "difficulty": 3,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["id"] > 0
    assert data["tags"] == "volatile,线程安全"

    # 列表 + 标签筛选
    qs = client.get("/api/questions?tags=volatile").json()
    assert qs["total"] == 1

    # 标签 API
    tags = client.get("/api/tags").json()
    assert "volatile" in tags
    assert "线程安全" in tags


def test_random_question_not_stuck(client):
    # 导入多题
    ids = []
    for i in range(5):
        r = client.post("/api/questions/import", json={
            "category": "测试", "question_text": f"Q{i}",
            "reference_answer": f"A{i}", "difficulty": 2,
        })
        ids.append(r.json()["id"])

    got = set()
    for _ in range(20):
        r = client.get("/api/questions/random")
        assert r.status_code == 200
        got.add(r.json()["id"])
    # 20 次内至少抽到 2 个不同 id
    assert len(got) >= 2


def test_answer_and_wrong_book(client):
    r = client.post("/api/questions/import", json={
        "category": "测试", "question_text": "测试题？",
        "reference_answer": "正确答案", "difficulty": 2,
    })
    qid = r.json()["id"]

    # 答对
    res = client.post("/api/answer", json={"question_id": qid, "user_answer": "正确答案"}).json()
    assert res["is_correct"] is True

    # 答错
    res = client.post("/api/answer", json={"question_id": qid, "user_answer": "错误答案"}).json()
    assert res["is_correct"] is False

    wb = client.get("/api/wrong-book").json()
    assert len(wb) == 1
    assert wb[0]["question_id"] == qid

    # 聚类
    grouped = client.get("/api/wrong-book?group_by_reason=true").json()
    assert "groups" in grouped


def test_settings(client):
    r = client.get("/api/settings").json()
    assert r["push_time"] == "09:00"
    client.post("/api/settings", json={
        "email": "a@b.com", "push_time": "08:30",
        "ebbinghaus_steps": "1,3,7", "app_base_url": "http://localhost:8000",
    })
    r = client.get("/api/settings").json()
    assert r["push_time"] == "08:30"
    assert r["ebbinghaus_steps"] == "1,3,7"


def test_pdf_export(client):
    r = client.post("/api/questions/import", json={
        "category": "导出", "question_text": "PDF 导出测试",
        "reference_answer": "答案", "difficulty": 2,
    })
    qid = r.json()["id"]
    client.post("/api/answer", json={"question_id": qid, "user_answer": "错"})
    r = client.get("/api/wrong-book/export-pdf")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1
    assert "/data/wrong_book_export.pdf" in data["download_url"]
