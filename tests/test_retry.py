"""离线验证判题重试的事务、进程竞争、失败退避与历史 pending 回填。"""
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models, retry
from backend.db import Base
from backend.retry_models import JudgmentRetry


@pytest.fixture
def database(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "retry.db").as_posix()
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(retry, "SessionLocal", sessions)
    monkeypatch.setattr(retry, "has_remote_judge", lambda: True)
    yield sessions, url
    engine.dispose()


def pending(database, *, queued=True):
    sessions, _ = database
    day = date.today() - timedelta(days=3)
    with sessions() as db:
        q = models.Question(question_text="question", reference_answer="reference",
                            created_at=datetime.utcnow() - timedelta(days=4))
        db.add(q)
        db.flush()
        sub = models.Submission(question_id=q.id, user_answer="answer", judge_by="pending",
                                submitted_at=datetime.utcnow() - timedelta(days=3))
        db.add(sub)
        db.add(models.Activity(day=day, answered=1, correct=0, wrong=0))
        db.flush()
        if queued:
            retry.enqueue_pending(db, sub, activity_day=day)
            db.query(JudgmentRetry).update({"next_attempt_at": datetime.utcnow() - timedelta(seconds=1)})
        db.commit()
        return sub.id, q.id, day


@pytest.mark.parametrize("correct", [True, False])
def test_retry_updates_original_day_once_without_duplicate_submission(database, monkeypatch, correct):
    sid, qid, day = pending(database)

    async def judge(*_args):
        return correct, "recovered", "wrong reason" if not correct else "", "agent"

    monkeypatch.setattr(retry, "judge", judge)
    assert retry.run_pending_retries() == 1
    assert retry.run_pending_retries() == 0
    with database[0]() as db:
        sub = db.get(models.Submission, sid)
        assert sub.is_correct is correct
        assert sub.judge_by == "agent"
        assert db.query(models.Submission).count() == 1
        assert db.query(JudgmentRetry).count() == 0
        activity = db.get(models.Activity, day)
        assert activity.answered == 1
        assert activity.correct == int(correct)
        assert activity.wrong == int(not correct)
        assert db.query(models.Activity).count() == 1
        assert db.query(models.WrongBook).count() == int(not correct)
        assert db.query(models.ReviewSchedule).count() == int(not correct)


def test_old_pending_is_backfilled_without_recounting(database, monkeypatch):
    sid, _qid, _day = pending(database, queued=False)
    assert retry.run_pending_retries() == 0  # 回填后留出首次重试间隔
    with database[0]() as db:
        queued = db.get(JudgmentRetry, sid)
        assert queued is not None
        assert queued.attempts == 0
        assert db.query(models.Submission).count() == 1
        assert db.query(models.Activity).one().answered == 1


def test_no_remote_configuration_leaves_pending_untouched(database, monkeypatch):
    sid, _qid, _day = pending(database)
    monkeypatch.setattr(retry, "has_remote_judge", lambda: False)

    async def forbidden(*_args):
        pytest.fail("must not call heuristic or a remote service")

    monkeypatch.setattr(retry, "judge", forbidden)
    assert retry.run_pending_retries() == 0
    with database[0]() as db:
        assert db.get(JudgmentRetry, sid).attempts == 0
        assert db.get(models.Submission, sid).judge_by == "pending"


@pytest.mark.parametrize("result", [
    (None, "offline", "judge_error", "pending"), (True, "heuristic", "", "heuristic"),
])
def test_failure_and_heuristic_do_not_resolve_pending(database, monkeypatch, result):
    sid, _qid, _day = pending(database)

    async def judge(*_args):
        return result

    monkeypatch.setattr(retry, "judge", judge)
    before = datetime.utcnow()
    assert retry.run_pending_retries() == 0
    with database[0]() as db:
        row = db.get(JudgmentRetry, sid)
        assert row.attempts == 1
        assert row.claim_token is None
        assert row.lease_until is None
        assert row.next_attempt_at >= before + timedelta(seconds=60)
        assert db.get(models.Submission, sid).is_correct is None
        assert db.query(models.Activity).one().answered == 1


def test_two_processes_only_one_can_claim(database):
    sid, _qid, _day = pending(database)
    env = os.environ.copy()
    env["DATABASE_URL"] = database[1]
    code = (
        "import json; from datetime import datetime; from backend.retry import _claim; "
        f"print(json.dumps(bool(_claim({sid}, datetime.utcnow()))))"
    )
    workers = [subprocess.Popen([sys.executable, "-c", code], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
               for _ in range(2)]
    results = []
    for worker in workers:
        out, err = worker.communicate(timeout=20)
        assert worker.returncode == 0, err
        results.append(json.loads(out))
    assert sorted(results) == [False, True]


def test_expired_claim_recovers_and_stale_worker_cannot_commit(database):
    sid, _qid, day = pending(database)
    now = datetime.utcnow()
    first = retry._claim(sid, now)
    second = retry._claim(sid, now + timedelta(seconds=retry.LEASE_SECONDS + 1))
    assert first and second and first["token"] != second["token"]
    assert retry._complete(first, (False, "old", "wrong", "agent"), now) is False
    assert retry._complete(second, (True, "new", "", "agent"), now) is True
    assert retry._complete(second, (True, "duplicate", "", "agent"), now) is False
    with database[0]() as db:
        assert db.get(models.Activity, day).correct == 1
        assert db.get(models.Activity, day).wrong == 0


def test_legacy_queue_keeps_first_available_question_snapshot(database):
    sid, qid, _day = pending(database)
    now = datetime.utcnow()
    initial = retry._claim(sid, now)
    with database[0]() as db:
        question = db.get(models.Question, qid)
        question.question_text = "new question"
        question.reference_answer = "new answer"
        db.commit()
    subsequent = retry._claim(sid, now + timedelta(seconds=retry.LEASE_SECONDS + 1))
    assert subsequent["question"] == initial["question"] == "question"
    assert subsequent["reference"] == initial["reference"] == "reference"


@pytest.mark.parametrize("replace_after_claim", [False, True])
def test_legacy_pending_cannot_grade_a_reused_question_id(database, replace_after_claim):
    sid, qid, day = pending(database, queued=False)
    retry._backfill_pending()
    now = datetime.utcnow() + timedelta(minutes=2)
    claim = retry._claim(sid, now) if replace_after_claim else None
    with database[0]() as db:
        # An older writer deleted the question without cancelling historical submissions.
        db.query(models.Question).filter_by(id=qid).delete()
        replacement = models.Question(question_text="unrelated replacement")
        db.add(replacement)
        db.commit()
        assert replacement.id == qid
    if replace_after_claim:
        assert not retry._complete(claim, (False, "wrong", "bad", "agent"), now)
    else:
        assert retry._claim(sid, now) is None
    with database[0]() as db:
        assert db.get(models.Submission, sid).judge_by == "cancelled"
        assert db.get(JudgmentRetry, sid) is None
        assert db.get(models.Activity, day).wrong == 0
        assert db.query(models.WrongBook).count() == db.query(models.ReviewSchedule).count() == 0


def test_legacy_pending_without_identity_dates_is_cancelled(database):
    sid, qid, _day = pending(database)
    with database[0]() as db:
        db.get(models.Question, qid).created_at = None
        db.commit()
    assert retry._claim(sid, datetime.utcnow()) is None
    with database[0]() as db:
        assert db.get(models.Submission, sid).judge_by == "cancelled"
        assert db.get(JudgmentRetry, sid) is None


def test_failure_during_side_effects_rolls_back_result_and_counters(database, monkeypatch):
    sid, _qid, day = pending(database)
    claim = retry._claim(sid, datetime.utcnow())

    def fail(*_args):
        raise RuntimeError("simulated database error")

    monkeypatch.setattr(retry, "_ensure_review_schedule", fail)
    with pytest.raises(RuntimeError):
        retry._complete(claim, (False, "wrong", "reason", "agent"), datetime.utcnow())
    with database[0]() as db:
        assert db.get(models.Submission, sid).judge_by == "pending"
        assert db.get(models.Activity, day).wrong == 0
        assert db.query(models.WrongBook).count() == 0
        assert db.get(JudgmentRetry, sid).claim_token == claim["token"]


def test_late_wrong_result_preserves_more_recent_mastery(database):
    sid, qid, day = pending(database)
    with database[0]() as db:
        db.add(models.WrongBook(question_id=qid, wrong_count=2, mastery="mastered",
                                last_user_answer="new answer", first_wrong_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()))
        db.commit()
    claim = retry._claim(sid, datetime.utcnow())
    assert retry._complete(claim, (False, "old wrong", "old reason", "agent"), datetime.utcnow())
    with database[0]() as db:
        wrong = db.query(models.WrongBook).one()
        assert wrong.wrong_count == 3
        assert wrong.mastery == "mastered"
        assert wrong.last_user_answer == "new answer"
        assert wrong.first_wrong_at == db.get(models.Submission, sid).submitted_at
        assert db.query(models.ReviewSchedule).count() == 0


def test_submission_and_retry_queue_commit_together(database):
    import backend.app as appmod

    sessions, _ = database
    with sessions() as db:
        question = models.Question(question_text="question", reference_answer="answer")
        db.add(question)
        db.commit()
        appmod._persist_answer_result(db, question, "answer", None, "offline", "judge_error", "pending")
        db.commit()
        submission = db.query(models.Submission).one()
        assert db.get(JudgmentRetry, submission.id) is not None
        assert db.query(models.Activity).one().answered == 1
        assert db.query(models.WrongBook).count() == 0


def test_two_processes_initialize_new_queue_tables(tmp_path):
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite:///" + (tmp_path / "startup.db").as_posix()
    code = "from backend.db import init_db; init_db()"
    workers = [subprocess.Popen([sys.executable, "-c", code], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
               for _ in range(2)]
    for worker in workers:
        _out, err = worker.communicate(timeout=30)
        assert worker.returncode == 0, err


@pytest.mark.parametrize("claimed", [False, True])
def test_deleted_question_terminates_retry_without_losing_history(database, claimed):
    import backend.app as appmod
    sid, qid, day = pending(database)
    claim = retry._claim(sid, datetime.utcnow()) if claimed else None
    with database[0]() as db:
        appmod.delete_question(qid, db)
    if claimed:
        assert not retry._complete(claim, (False, "late", "wrong", "agent"), datetime.utcnow())
    retry._backfill_pending()
    retry._backfill_pending()
    with database[0]() as db:
        assert db.get(models.Submission, sid).judge_by == "cancelled"
        assert db.query(JudgmentRetry).count() == 0
        assert db.query(models.WrongBook).count() == 0
        assert db.query(models.ReviewSchedule).count() == 0
        assert db.get(models.Activity, day).answered == 1
        assert db.get(models.Activity, day).wrong == 0


def test_legacy_orphan_pending_becomes_terminal(database):
    sid, qid, _day = pending(database, queued=False)
    with database[0]() as db:
        db.query(models.Question).filter_by(id=qid).delete()
        db.commit()
    retry._backfill_pending()
    retry._backfill_pending()
    with database[0]() as db:
        assert db.get(models.Submission, sid).judge_by == "cancelled"
        assert db.query(JudgmentRetry).count() == 0


def test_concurrent_delete_and_retry_leave_no_orphan_learning_state(database):
    import backend.app as appmod
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    sid, qid, _day = pending(database)
    claim = retry._claim(sid, datetime.utcnow())
    barrier = Barrier(2)
    def remove():
        barrier.wait(timeout=5)
        with database[0]() as db:
            appmod.delete_question(qid, db)
    def complete():
        barrier.wait(timeout=5)
        return retry._complete(claim, (False, "late", "wrong", "agent"), datetime.utcnow())
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = [workers.submit(remove), workers.submit(complete)]
        for result in results:
            result.result(timeout=20)
    with database[0]() as db:
        assert db.get(models.Question, qid) is None
        assert db.get(models.Submission, sid) is not None
        assert db.query(JudgmentRetry).count() == 0
        assert db.query(models.WrongBook).count() == 0
        assert db.query(models.ReviewSchedule).count() == 0
