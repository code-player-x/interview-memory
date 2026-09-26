"""interview-memory 后端单元测试。

运行：pytest tests/ -q
"""
import os
import sys
import tempfile
import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# 使用临时数据库
TMP_DB = os.path.join(tempfile.gettempdir(), "im_test.db")
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)
os.environ["DATABASE_URL"] = "sqlite:///" + TMP_DB
os.environ["AGENT_JUDGE_URL"] = ""
os.environ["LLM_BASE_URL"] = ""

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

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
    assert r["app_base_url"] == "http://localhost:8000"


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


def test_review_feedback_handles_legacy_null_review_count(client):
    r = client.post("/api/questions/import", json={
        "category": "兼容性", "question_text": "旧复习记录", "reference_answer": "答案", "difficulty": 1,
    })
    qid = r.json()["id"]
    client.post("/api/answer", json={"question_id": qid, "user_answer": "错误"})
    # 用独立 session 写入 NULL，模拟早期库中遗漏该字段的记录。
    db = SessionLocal()
    try:
        schedule = db.query(models.ReviewSchedule).filter_by(question_id=qid).first()
        schedule.review_count = None
        db.commit()
    finally:
        db.close()
    result = client.post(f"/api/review/{qid}", json={"remembered": True})
    assert result.status_code == 200


def test_tag_filter_matches_complete_comma_tokens_only(client):
    exact = client.post("/api/questions/import", json={
        "category": "标签测试", "tags": "JVM,并发", "question_text": "精确 JVM 标签",
        "reference_answer": "答案", "difficulty": 1,
    }).json()
    client.post("/api/questions/import", json={
        "category": "JVM", "tags": "JVM调优,并发", "question_text": "不应被 JVM 标签命中",
        "reference_answer": "答案", "difficulty": 1,
    })

    rows = client.get("/api/questions?tags=JVM").json()["items"]
    ids = {row["id"] for row in rows}
    assert exact["id"] in ids
    assert all(row["tags"] != "JVM调优,并发" for row in rows)


def test_tag_filter_normalizes_spaces_and_escapes_like_tokens(client):
    tagged = client.post("/api/questions/import", json={
        "category": "标签测试", "tags": "System Design,foo_bar,100%",
        "question_text": "含空格和 LIKE 特殊字符的标签", "reference_answer": "答案", "difficulty": 1,
    }).json()
    client.post("/api/questions/import", json={
        "category": "标签测试", "tags": "System Designs,fooXbar,1000",
        "question_text": "不应被特殊标签误命中", "reference_answer": "答案", "difficulty": 1,
    })

    for tag in ("System Design", "foo_bar", "100%"):
        rows = client.get("/api/questions", params={"tags": tag}).json()["items"]
        assert tagged["id"] in {row["id"] for row in rows}


def test_question_detail_normalizes_legacy_nullable_string_columns(client):
    q = client.post("/api/questions/import", json={
        "category": "兼容", "question_text": "历史空字段题", "reference_answer": "答案", "difficulty": 1,
    }).json()
    db = SessionLocal()
    try:
        legacy = db.query(models.Question).filter_by(id=q["id"]).one()
        legacy.platform = None
        legacy.category = None
        legacy.tags = None
        legacy.images = None
        legacy.keywords = None
        db.commit()
    finally:
        db.close()

    result = client.get(f"/api/question/{q['id']}")
    assert result.status_code == 200
    payload = result.json()
    assert payload["platform"] == ""
    assert payload["category"] == ""
    assert payload["tags"] == ""
    assert payload["images"] == ""
    assert payload["keywords"] == ""


def test_invalid_settings_do_not_overwrite_persisted_values(client):
    valid = {
        "email": "settings@example.com",
        "push_time": "08:30",
        "ebbinghaus_steps": "1,3,7",
        "app_base_url": "http://localhost:8000",
    }
    assert client.post("/api/settings", json=valid).status_code == 200

    for bad in (
        {**valid, "push_time": "24:00"},
        {**valid, "push_time": "8:30"},
        {**valid, "ebbinghaus_steps": "1,1,3"},
        {**valid, "ebbinghaus_steps": "3,1"},
        {**valid, "ebbinghaus_steps": "1,0,3"},
    ):
        assert client.post("/api/settings", json=bad).status_code == 422

    actual = client.get("/api/settings").json()
    assert actual["push_time"] == "08:30"
    assert actual["ebbinghaus_steps"] == "1,3,7"


def test_question_notes_require_existing_question_and_are_cleaned_on_delete(client):
    assert client.get("/api/questions/999999/notes").status_code == 404
    q = client.post("/api/questions/import", json={
        "category": "笔记", "question_text": "会被删除的题", "reference_answer": "答案", "difficulty": 1,
    }).json()
    note = client.post(f"/api/questions/{q['id']}/notes", json={"content": "临时笔记"})
    assert note.status_code == 200

    assert client.delete(f"/api/questions/{q['id']}").status_code == 200
    db = SessionLocal()
    try:
        assert db.query(models.QuestionNote).filter_by(question_id=q["id"]).count() == 0
    finally:
        db.close()
    assert client.get(f"/api/questions/{q['id']}/notes").status_code == 404


def test_new_question_submission_and_experience_use_utc_timestamps(client):
    before = datetime.utcnow() - timedelta(seconds=1)
    q = client.post("/api/questions/import", json={
        "category": "时间", "question_text": "UTC 题", "reference_answer": "UTC 答案", "difficulty": 1,
    }).json()
    answer = client.post("/api/answer", json={"question_id": q["id"], "user_answer": "UTC 答案"})
    assert answer.status_code == 200
    exp = client.post("/api/experiences", json={
        "company": "时间公司", "content": "时间面经",
    })
    assert exp.status_code == 200

    db = SessionLocal()
    try:
        question = db.query(models.Question).filter_by(id=q["id"]).one()
        submission = db.query(models.Submission).filter_by(question_id=q["id"]).order_by(
            models.Submission.id.desc()
        ).first()
        experience = db.query(models.InterviewExp).filter_by(id=exp.json()["id"]).one()
        assert question.created_at >= before
        assert submission.submitted_at >= before
        assert experience.created_at >= before
    finally:
        db.close()


def test_wrong_book_and_review_schedule_are_single_rows_per_question(client):
    q = client.post("/api/questions/import", json={
        "category": "并发写入", "question_text": "错题唯一性", "reference_answer": "唯一约束", "difficulty": 2,
    }).json()
    for answer in ("第一次错误", "第二次错误"):
        assert client.post("/api/answer", json={"question_id": q["id"], "user_answer": answer}).status_code == 200

    db = SessionLocal()
    try:
        wrong_rows = db.query(models.WrongBook).filter_by(question_id=q["id"]).all()
        schedule_rows = db.query(models.ReviewSchedule).filter_by(question_id=q["id"]).all()
        assert len(wrong_rows) == 1
        assert wrong_rows[0].wrong_count == 2
        assert len(schedule_rows) == 1
    finally:
        db.close()


def test_todo_category_filter(client):
    assert client.post("/api/todos", json={"title": "后端待办", "category": "后端"}).status_code == 200
    assert client.post("/api/todos", json={"title": "前端待办", "category": "前端"}).status_code == 200
    rows = client.get("/api/todos?category=后端").json()
    assert rows and all(row["category"] == "后端" for row in rows)


def test_quiz_rejects_duplicate_and_oversized_items(client, monkeypatch):
    q = client.post("/api/questions/import", json={
        "category": "组卷", "question_text": "组卷去重题", "reference_answer": "答案", "difficulty": 1,
    }).json()
    duplicate = client.post("/api/quiz/submit", json={"items": [
        {"question_id": q["id"], "user_answer": "答案"},
        {"question_id": q["id"], "user_answer": "答案"},
    ]})
    assert duplicate.status_code == 422

    too_many = client.post("/api/quiz/submit", json={"items": [
        {"question_id": q["id"], "user_answer": ""}
        for _ in range(appmod.MAX_QUIZ_ITEMS + 1)
    ]})
    assert too_many.status_code == 422


def test_quiz_judging_respects_concurrency_limit(client, monkeypatch):
    ids = []
    for index in range(3):
        q = client.post("/api/questions/import", json={
            "category": "组卷并发", "question_text": f"并发题 {index}",
            "reference_answer": "参考答案", "difficulty": 1,
        }).json()
        ids.append(q["id"])

    inflight = 0
    maximum = 0

    async def fake_judge(*_args):
        nonlocal inflight, maximum
        inflight += 1
        maximum = max(maximum, inflight)
        await asyncio.sleep(0.01)
        inflight -= 1
        return True, "ok", "", "test"

    monkeypatch.setattr(appmod, "MAX_CONCURRENT_JUDGES", 1)
    monkeypatch.setattr(appmod, "judge", fake_judge)
    result = client.post("/api/quiz/submit", json={"items": [
        {"question_id": question_id, "user_answer": "答案"} for question_id in ids
    ]})
    assert result.status_code == 200
    assert len(result.json()["results"]) == 3
    assert maximum == 1


def test_articles_status_reports_available_test_resource(client):
    status = client.get("/api/articles/status")
    assert status.status_code == 200
    assert status.json() == {"available": True, "message": ""}


def test_blank_quiz_retains_question_and_does_not_write_activity(client):
    q = client.post("/api/questions/import", json={"question_text": "未答题回归", "reference_answer": "有效参考"}).json()
    activity = client.get("/api/activity").json()
    rows = client.post("/api/quiz/submit", json={"items": [
        {"question_id": q["id"], "user_answer": " "},
        {"question_id": 999999999, "user_answer": ""},
    ]}).json()["results"]
    assert rows[0]["explanation"] == "未作答"
    assert rows[0]["reference_answer"] == "有效参考"
    assert rows[1]["error_reason"] == "question_missing"
    assert client.get("/api/activity").json() == activity


def test_new_random_round_excludes_last_seen_not_highest_id(client):
    ids = [client.post("/api/questions/import", json={"category": "轮次回归", "question_text": f"轮次题{i}", "reference_answer": "答案"}).json()["id"] for i in range(2)]
    result = client.get("/api/practice/next", params={"category": "轮次回归", "seen_ids": f"invalid,{ids[1]},999999999,{ids[0]}"}).json()
    assert result["id"] == ids[1]
    assert result["round_complete"] is True
    assert result["remaining"] == 1
    # Single-question scopes must still cycle.
    only = client.get("/api/practice/next", params={"category": "轮次回归", "seen_ids": str(ids[0])}).json()
    assert only["id"] == ids[1] and not only["round_complete"]


@pytest.mark.parametrize("endpoint", ["import-json", "import-batch"])
def test_batch_import_deduplicates_within_and_across_batches(client, tmp_path, endpoint):
    import json
    title = "同批去重-" + endpoint
    if endpoint == "import-json":
        payload = {"items": [{"question_text": title, "reference_answer": "答案"}] * 2}
    else:
        source = tmp_path / "bank.json"
        source.write_text(json.dumps({"questions": [{"question": title, "reference_answer": "答案"}] * 2}))
        payload = {"path": str(source)}
    first = client.post("/api/questions/" + endpoint, json=payload).json()
    second = client.post("/api/questions/" + endpoint, json=payload).json()
    assert (first["imported"], first["skipped"]) == (1, 1)
    assert (second["imported"], second["skipped"]) == (0, 2)


def test_forgotten_mastered_question_reopens_both_states(client):
    q = client.post("/api/questions/import", json={"question_text": "遗忘状态回归", "reference_answer": "参考标准答案"}).json()["id"]
    client.post("/api/answer", json={"question_id": q, "user_answer": "zzzz"})
    assert client.post(f"/api/wrong-book/{q}/master").status_code == 200
    result = client.post(f"/api/review/{q}", json={"remembered": False}).json()
    assert result["stage"] == 1 and result["status"] == "pending"
    db = SessionLocal()
    try:
        assert db.query(models.WrongBook).filter_by(question_id=q).one().mastery == "reviewing"
    finally:
        db.close()


@pytest.mark.parametrize("invalid", [{"title": " "}, {"priority": -10}, {"priority": 5}, {"due_date": "2026-99-99"}, {"due_date": "2026-2-3"}])
def test_todo_rejects_invalid_create_and_update(client, invalid):
    assert client.post("/api/todos", json={"title": "合法待办", **invalid}).status_code == 422
    row = client.post("/api/todos", json={"title": " 保留低优先级 ", "priority": 4, "due_date": "2026-09-26"}).json()
    assert row["title"] == "保留低优先级"
    assert client.put(f'/api/todos/{row["id"]}', json=invalid).status_code == 422
    for minutes in (-25, 0, 1441):
        assert client.post(f'/api/todos/{row["id"]}/focus/start', params={"minutes": minutes}).status_code == 422
    assert client.post(f'/api/todos/{row["id"]}/focus/start', params={"minutes": 25}).status_code == 200


def test_malformed_agent_result_is_pending_in_answer_and_quiz(client, monkeypatch):
    import httpx

    class Response:
        def raise_for_status(self): pass
        def json(self): return {"is_correct": True, "explanation": {"invalid": "object"}, "error_reason": ""}

    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return Response()

    monkeypatch.setenv("AGENT_JUDGE_URL", "http://agent.example")
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    q = client.post("/api/questions/import", json={"question_text": "坏响应回归", "reference_answer": "标准答案"}).json()["id"]
    data = {"question_id": q, "user_answer": "回答内容"}
    single = client.post("/api/answer", json=data)
    assert single.status_code == 200
    assert single.json()["is_correct"] is None and single.json()["source"] == "pending"
    batch = client.post("/api/quiz/submit", json={"items": [data]})
    assert batch.status_code == 200
    result = batch.json()["results"][0]
    assert result["is_correct"] is None and result["judge_by"] == "pending"
