"""学习状态、时间约定、请求重试与设置的隔离回归。"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.app as appmod
from backend import models
from backend.db import Base, get_db
from backend.ebbinghaus import get_steps


@pytest.fixture
def api(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "learning.db").as_posix(),
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    def dependency():
        with sessions() as db:
            yield db
    appmod.app.dependency_overrides[get_db] = dependency
    with TestClient(appmod.app) as client:
        yield client, sessions
    appmod.app.dependency_overrides.pop(get_db, None)
    engine.dispose()


@pytest.mark.parametrize("value", ["9999999999999", "-1,2", "0,1", ",,,", "2,1"])
def test_legacy_invalid_intervals_fall_back(value):
    assert get_steps(value) == [1, 2, 4, 7, 15, 30, 60]


@pytest.mark.parametrize("editing", [False, True])
def test_note_response_survives_question_deletion_after_commit(api, editing):
    from sqlalchemy import event
    from backend import notes_routes

    client, sessions = api
    qid = client.post("/api/questions/import", json={"question_text": "notes"}).json()["id"]
    payload = notes_routes.NoteIn(content="saved")
    with sessions() as db:
        if editing:
            initial = notes_routes.create_note(qid, notes_routes.NoteIn(content="draft"), db)

        @event.listens_for(db, "after_commit", once=True)
        def delete_after_save(_session):
            with sessions() as concurrent:
                appmod.delete_question(qid, concurrent)

        result = (notes_routes.update_note(qid, initial.id, payload, db) if editing
                  else notes_routes.create_note(qid, payload, db))
        assert result.content == "saved" and result.question_id == qid
    with sessions() as db:
        assert db.query(models.QuestionNote).count() == 0


def test_large_intervals_rejected_before_saving(api):
    client, sessions = api
    original = client.get("/api/settings").json()
    assert client.post("/api/settings", json={**original, "ebbinghaus_steps": "999999999999"}).status_code == 422
    assert client.get("/api/settings").json() == original


@pytest.mark.parametrize("quiz", [False, True])
def test_grading_accepts_legacy_sqlite_creation_timestamp(api, quiz):
    from sqlalchemy import text
    client, sessions = api
    qid = client.post("/api/questions/import", json={"question_text": "legacy time",
                                                     "reference_answer": "exact"}).json()["id"]
    with sessions() as db:
        db.execute(text("UPDATE questions SET created_at='2025-01-02 03:04:05' WHERE id=:id"), {"id": qid})
        db.commit()
    item = {"question_id": qid, "user_answer": "exact"}
    response = client.post("/api/quiz/submit", json={"items": [item]}) if quiz else client.post("/api/answer", json=item)
    assert response.status_code == 200
    result = response.json()["results"][0] if quiz else response.json()
    assert result["is_correct"] is True


def test_pending_answers_count_towards_volume_only(api):
    client, sessions = api
    with sessions() as db:
        db.add_all([models.Submission(question_id=1, is_correct=True, judge_by="agent"),
                    models.Submission(question_id=2, is_correct=None, judge_by="pending"),
                    models.Activity(day=datetime.now().date(), answered=2, correct=1, wrong=0)])
        db.commit()
    admin = client.get("/api/admin/stats").json()
    week = client.get("/api/growth/summary").json()["report"]["week"]
    assert admin["total_submissions"] == week["answered"] == 2
    assert admin["accuracy"] == week["accuracy"] == 100


@pytest.mark.parametrize("quiz", [False, True])
def test_pending_judgment_refresh_uses_the_same_submission(api, monkeypatch, quiz):
    from backend import retry
    from backend.retry_models import JudgmentRetry
    client, sessions = api
    qid = client.post("/api/questions/import", json={"question_text": "retry question"}).json()["id"]
    async def offline(*args):
        return None, "暂时不可用", "judge_error", "pending"
    async def recovered(*args):
        return True, "判题服务已恢复", "", "agent"
    monkeypatch.setattr(appmod, "judge", offline)
    item = {"question_id": qid, "user_answer": "answer"}
    response = client.post("/api/quiz/submit", json={"items": [item]}) if quiz else client.post("/api/answer", json=item)
    assert response.status_code == 200
    out = response.json()["results"][0] if quiz else response.json()
    sid = out["submission_id"]
    url = f"/api/submissions/{sid}/judgment"
    assert client.get(url).json()["source"] == "pending"
    with sessions() as db:
        db.get(JudgmentRetry, sid).next_attempt_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
    monkeypatch.setattr(retry, "SessionLocal", sessions)
    monkeypatch.setattr(retry, "has_remote_judge", lambda: True)
    monkeypatch.setattr(retry, "judge", recovered)
    assert retry.run_pending_retries() == 1
    assert client.get(url).json() == {"submission_id": sid, "is_correct": True,
                                      "source": "agent", "explanation": "判题服务已恢复"}
    assert client.get("/api/activity").json()[0]["answered"] == 1


def test_uncategorized_card_matches_filters_and_management(api):
    client, sessions = api
    with sessions() as db:
        db.add_all([models.Question(question_text=f"uncategorized {i}", category=cat)
                    for i, cat in enumerate([None, "", "未分类"])])
        db.commit()
    for path in ["/api/categories/detail", "/api/categories/meta"]:
        rows = [row for row in client.get(path).json() if row["name"] == "未分类"]
        assert [row["count"] for row in rows] == [3]
    params = {"category": "未分类"}
    assert client.get("/api/questions", params=params).json()["total"] == 3
    assert client.post("/api/practice/next", params=params, json={"seen_ids": []}).json()["total"] == 3
    assert client.get("/api/quiz/generate", params=params).status_code == 200
    assert client.post("/api/categories/rename", json={"old_name": "未分类", "new_name": "整理完成"}).status_code == 200
    assert client.get("/api/questions", params={"category": "整理完成"}).json()["total"] == 3


def test_export_matches_difficulty_filter_and_round_trips_metadata(api):
    client, _ = api
    item = {"question_text": "hard", "difficulty": 5, "keywords": "索引", "tags": "DB",
            "images": '["/data/images/diagram.png"]', "reference_answer": "答案"}
    qid = client.post("/api/questions/import", json=item).json()["id"]
    client.post("/api/questions/import", json={"question_text": "easy", "difficulty": 1})
    rows = client.get("/api/questions/export", params={"level": 3}).json()
    assert [r["question_text"] for r in rows] == ["hard"]
    assert "id" not in rows[0]
    assert client.delete(f"/api/questions/{qid}").status_code == 200
    assert client.post("/api/questions/import-json", json={"items": rows}).json()["imported"] == 1
    assert client.get("/api/questions/export", params={"level": 3}).json() == rows
    assert all(rows[0][key] == val for key, val in item.items())
    legacy = {"question_text": "old export", "reference_answer": None, "category": None, "difficulty": None}
    assert client.post("/api/questions/import-json", json={"items": [legacy]}).json()["imported"] == 1


@pytest.mark.parametrize("quiz", [False, True])
def test_answer_request_replay_does_not_repeat_judging_or_activity(api, monkeypatch, quiz):
    client, sessions = api
    qid = client.post("/api/questions/import", json={"question_text": "request test"}).json()["id"]
    calls = []
    async def judge(*args):
        calls.append(args)
        return False, "wrong", "reason", "agent"
    monkeypatch.setattr(appmod, "judge", judge)
    payload = {"question_id": qid, "user_answer": "answer"}
    path = "/api/quiz/submit" if quiz else "/api/answer"
    if quiz:
        payload = {"items": [payload]}
    payload["request_id"] = "same-attempt"
    first = client.post(path, json=payload)
    second = client.post(path, json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(calls) == 1
    with sessions() as db:
        assert db.query(models.Submission).count() == 1
        assert db.query(models.Activity).one().answered == 1
        assert db.query(models.WrongBook).one().wrong_count == 1
    changed = {**payload}
    if quiz:
        changed["items"] = [{"question_id": qid, "user_answer": "different"}]
    else:
        changed["user_answer"] = "different"
    assert client.post(path, json=changed).status_code == 409


def test_duplicate_forgotten_review_does_not_advance_count(api):
    client, sessions = api
    qid = client.post("/api/questions/import", json={"question_text": "review"}).json()["id"]
    with sessions() as db:
        db.add(models.ReviewSchedule(question_id=qid, stage=1, review_count=0, status="pending",
                                     next_review_at=datetime.utcnow() - timedelta(days=1)))
        db.commit()
    item = client.get("/api/review/due").json()[0]
    payload = {"remembered": False, "expected_stage": item["stage"], "expected_review_count": item["review_count"]}
    assert client.post(f"/api/review/{qid}", json=payload).status_code == 200
    assert client.post(f"/api/review/{qid}", json=payload).status_code == 409
    with sessions() as db:
        assert db.query(models.ReviewSchedule).one().review_count == 1


def test_focus_statistics_include_legacy_utc_but_exclude_break(api):
    client, sessions = api
    with sessions() as db:
        for kind, minutes, start in [
            ("focus", 25, datetime.now()),
            ("pomodoro", 12, datetime.utcnow()),
            ("break", 5, datetime.now()),
        ]:
            db.add(models.FocusSession(kind=kind, actual_minutes=minutes, started_at=start, completed=True))
        db.commit()
    stats = client.get("/api/pomodoro/stats").json()
    assert stats["today"] == {"minutes": 37, "count": 2}
    growth = client.get("/api/growth/summary").json()
    badges = {b["id"]: b for b in growth["badges"]}
    assert badges["focus50"]["progress"] == 2
    assert badges["focus10h"]["progress"] == 37


def test_todo_focus_uses_elapsed_utc_time(api):
    client, sessions = api
    tid = client.post("/api/todos", json={"title": "focus"}).json()["id"]
    started = client.post(f"/api/todos/{tid}/focus/start").json()
    assert started["started_at"].endswith("+00:00")
    with sessions() as db:
        record = db.get(models.FocusSession, started["id"])
        assert record.kind == "pomodoro"
        assert abs((record.started_at - datetime.utcnow()).total_seconds()) < 30
        record.started_at -= timedelta(minutes=25)
        db.commit()
    stopped = client.post(f"/api/todos/{tid}/focus/stop", params={"session_id": started["id"]})
    assert stopped.json()["actual_minutes"] == 25


def test_healthy_database_startup_skips_deduplication(api, monkeypatch):
    from backend import db as database
    _client, sessions = api
    monkeypatch.setattr(database, "engine", sessions.kw["bind"])
    def forbidden(*args):
        pytest.fail("unique constraints already exist; no historical table scan needed")
    monkeypatch.setattr(database, "_dedupe_wrong_book", forbidden)
    monkeypatch.setattr(database, "_dedupe_review_schedule", forbidden)
    database.init_db()


def test_legacy_settings_singleton_preserves_first_saved_configuration(api, monkeypatch):
    from backend import db as database
    _client, sessions = api
    with sessions() as db:
        db.add(models.Settings(id=3, email="first@example.com", push_time="08:30"))
        db.add(models.Settings(id=4, email="second@example.com", push_time="10:00"))
        db.commit()
    monkeypatch.setattr(database, "engine", sessions.kw["bind"])
    database._ensure_settings_singleton()
    with sessions() as db:
        setting = db.query(models.Settings).one()
        assert setting.id == 1
        assert setting.email == "first@example.com"


def test_idempotency_claim_is_exclusive_between_connections(api):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi import HTTPException
    from backend.idempotency import begin_request
    _client, sessions = api
    barrier = Barrier(2)
    payload = appmod.AnswerIn(question_id=1, user_answer="answer", request_id="parallel")
    def claim():
        barrier.wait(timeout=5)
        with sessions() as db:
            try:
                begin_request(db, "answer", payload)
                return 200
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = [workers.submit(claim) for _ in range(2)]
        assert sorted(f.result(timeout=15) for f in results) == [200, 409]


def test_long_quiz_renews_claim_and_replays_large_report(api, monkeypatch):
    import asyncio
    from threading import Event
    from fastapi import HTTPException
    from backend import idempotency

    client, sessions = api
    # Two individually small answers exceed the MySQL TEXT limit as a single JSON response.
    reference = "数据" * 7000
    ids = [client.post("/api/questions/import", json={
        "question_text": f"quiz {n}", "reference_answer": reference}).json()["id"] for n in range(2)]
    payload = appmod.QuizSubmitIn(items=[{"question_id": qid, "user_answer": "answer"}
                                         for qid in ids], request_id="long-quiz")
    origin = datetime.utcnow()
    class Clock:
        current = origin
        @classmethod
        def utcnow(cls):
            return cls.current

    renew = idempotency._renew_request
    renewed = Event()
    def observe_renewal(*args):
        owned = renew(*args)
        renewed.set()
        return owned

    calls = []
    async def slow_judge(question, *_args):
        calls.append(question)
        if len(calls) == 1:
            Clock.current = origin + timedelta(minutes=9)
            assert await asyncio.to_thread(renewed.wait, 5)
            Clock.current = origin + timedelta(minutes=11)
            with sessions() as competing, pytest.raises(HTTPException) as conflict:
                idempotency.begin_request(competing, "quiz", payload)
            assert conflict.value.status_code == 409
        return True, "correct", "", "agent"

    monkeypatch.setattr(idempotency, "datetime", Clock)
    monkeypatch.setattr(idempotency, "_renew_request", observe_renewal)
    monkeypatch.setattr(idempotency, "RENEW_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(appmod, "MAX_CONCURRENT_JUDGES", 1)
    monkeypatch.setattr(appmod, "judge", slow_judge)
    response = client.post("/api/quiz/submit", json=payload.model_dump())
    assert response.status_code == 200
    assert all(row["is_correct"] is True for row in response.json()["results"])
    assert len(response.content) > 65535
    assert client.post("/api/quiz/submit", json=payload.model_dump()).json() == response.json()
    assert calls == ["quiz 0", "quiz 1"]
    with sessions() as db:
        assert db.query(models.Submission).count() == 2


def test_settings_first_read_is_singleton_between_connections(api):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    _client, sessions = api
    barrier = Barrier(2)
    def get_setting():
        barrier.wait(timeout=5)
        with sessions() as db:
            setting = appmod.get_settings(db)
            db.commit()
            return setting.id
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = [workers.submit(get_setting) for _ in range(2)]
        assert [f.result(timeout=15) for f in results] == [1, 1]
    with sessions() as db:
        assert db.query(models.Settings).count() == 1


def test_unexpected_quiz_judge_exception_is_queued(api, monkeypatch):
    from backend.retry_models import JudgmentRetry
    client, sessions = api
    qid = client.post("/api/questions/import", json={"question_text": "quiz pending"}).json()["id"]
    async def fail(*args):
        raise RuntimeError("internal details")
    monkeypatch.setattr(appmod, "judge", fail)
    response = client.post("/api/quiz/submit", json={"items": [{"question_id": qid, "user_answer": "answer"}]})
    assert response.status_code == 200
    assert response.json()["results"][0]["judge_by"] == "pending"
    assert "internal details" not in response.text
    with sessions() as db:
        sub = db.query(models.Submission).one()
        assert sub.judge_by == "pending"
        assert db.get(JudgmentRetry, sub.id) is not None


@pytest.mark.parametrize("quiz", [False, True])
def test_pending_retries_original_judgment_after_question_edit(api, monkeypatch, quiz):
    from backend import retry
    from backend.retry_models import JudgmentRetry

    client, sessions = api
    qid = client.post("/api/questions/import", json={
        "question_text": "original question", "reference_answer": "original reference",
    }).json()["id"]

    async def unavailable(*args):
        with sessions() as db:
            question = db.get(models.Question, qid)
            question.question_text = "revised question"
            question.reference_answer = "revised reference"
            db.commit()
        return None, "offline", "", "pending"

    monkeypatch.setattr(appmod, "judge", unavailable)
    item = {"question_id": qid, "user_answer": "original answer"}
    response = client.post("/api/quiz/submit" if quiz else "/api/answer",
                           json={"items": [item]} if quiz else item)
    assert response.status_code == 200
    with sessions() as db:
        queued = db.query(JudgmentRetry).one()
        sid = queued.submission_id
        queued.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()

    monkeypatch.setattr(retry, "SessionLocal", sessions)
    claim = retry._claim(sid, datetime.utcnow())
    assert (claim["question"], claim["reference"], claim["answer"]) == (
        "original question", "original reference", "original answer",
    )


@pytest.mark.parametrize("quiz", [False, True])
def test_delete_during_remote_judgment_never_recreates_learning_records(api, monkeypatch, quiz):
    from backend.idempotency import AnswerRequest
    client, sessions = api
    qid = client.post("/api/questions/import", json={"question_text": "delete during judging"}).json()["id"]
    active = []
    def dependency():
        with sessions() as db:
            active.append(db)
            yield db
    appmod.app.dependency_overrides[get_db] = dependency
    async def judge(*args):
        assert not active[-1].in_transaction(), "remote call must not retain a read transaction"
        with sessions() as db:
            appmod.delete_question(qid, db)
        return False, "wrong", "reason", "agent"
    monkeypatch.setattr(appmod, "judge", judge)
    item = {"question_id": qid, "user_answer": "answer"}
    payload = {"items": [item]} if quiz else item
    payload["request_id"] = "deleted-during-judge"
    response = client.post("/api/quiz/submit" if quiz else "/api/answer", json=payload)
    assert response.status_code == (200 if quiz else 404)
    if quiz:
        assert response.json()["results"][0]["error_reason"] == "question_missing"
    with sessions() as db:
        assert db.query(models.Submission).count() == 0
        assert db.query(models.WrongBook).count() == 0
        assert db.query(models.ReviewSchedule).count() == 0
        assert db.query(models.Activity).count() == 0
        assert db.query(AnswerRequest).count() == int(quiz)


def test_missing_single_question_releases_request_instead_of_ten_minute_conflict(api):
    from backend.idempotency import AnswerRequest
    client, sessions = api
    payload = {"question_id": 9999, "user_answer": "answer", "request_id": "missing"}
    assert client.post("/api/answer", json=payload).status_code == 404
    assert client.post("/api/answer", json=payload).status_code == 404
    with sessions() as db:
        assert db.query(AnswerRequest).count() == 0


@pytest.mark.parametrize("quiz", [False, True])
def test_known_write_failure_rolls_back_and_allows_immediate_request_retry(api, monkeypatch, quiz):
    from backend.idempotency import AnswerRequest
    client, sessions = api
    qid = client.post("/api/questions/import", json={"question_text": "write failure"}).json()["id"]
    async def judge(*args):
        return False, "wrong", "reason", "agent"
    monkeypatch.setattr(appmod, "judge", judge)
    original = appmod._persist_answer_result
    def fail_after_writes(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("failed before commit")
    monkeypatch.setattr(appmod, "_persist_answer_result", fail_after_writes)
    item = {"question_id": qid, "user_answer": "answer"}
    payload = {"items": [item]} if quiz else item
    payload["request_id"] = "write-failure"
    path = "/api/quiz/submit" if quiz else "/api/answer"
    with pytest.raises(RuntimeError, match="failed before commit"):
        client.post(path, json=payload)
    with sessions() as db:
        assert db.query(models.Submission).count() == 0
        assert db.query(models.Activity).count() == 0
        assert db.query(AnswerRequest).count() == 0
    monkeypatch.setattr(appmod, "_persist_answer_result", original)
    assert client.post(path, json=payload).status_code == 200
    with sessions() as db:
        assert db.query(models.Submission).count() == 1


def test_completed_request_cache_survives_release_and_question_deletion(api, monkeypatch):
    from backend.idempotency import AnswerRequest, release_request
    client, sessions = api
    qid = client.post("/api/questions/import", json={"question_text": "cached answer"}).json()["id"]
    calls = []
    async def judge(*args):
        calls.append(args)
        return True, "correct", "", "agent"
    monkeypatch.setattr(appmod, "judge", judge)
    payload = {"question_id": qid, "user_answer": "answer", "request_id": "successful"}
    first = client.post("/api/answer", json=payload)
    assert first.status_code == 200
    with sessions() as db:
        cached = db.query(AnswerRequest).one()
        release_request(db, (cached.key, cached.token))
    assert client.delete(f"/api/questions/{qid}").status_code == 200
    second = client.post("/api/answer", json=payload)
    assert second.status_code == 200
    assert first.json() == second.json()
    assert len(calls) == 1


@pytest.mark.parametrize("quiz", [False, True])
def test_reused_deleted_question_id_is_not_mistaken_for_original(api, monkeypatch, quiz):
    client, sessions = api
    qid = client.post("/api/questions/import", json={"question_text": "original"}).json()["id"]
    async def judge(*args):
        with sessions() as db:
            appmod.delete_question(qid, db)
            db.add(models.Question(id=qid, question_text="replacement",
                                   created_at=datetime.utcnow() + timedelta(seconds=1)))
            db.commit()
        return False, "wrong", "reason", "agent"
    monkeypatch.setattr(appmod, "judge", judge)
    item = {"question_id": qid, "user_answer": "answer"}
    response = client.post("/api/quiz/submit" if quiz else "/api/answer",
                           json={"items": [item]} if quiz else item)
    assert response.status_code == (200 if quiz else 404)
    if quiz:
        assert response.json()["results"][0]["error_reason"] == "question_missing"
    with sessions() as db:
        assert db.query(models.Submission).count() == 0
