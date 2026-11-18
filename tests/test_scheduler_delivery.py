"""Daily mail claims: independent processes, restarts, failure ambiguity and settings.

All databases live under pytest's temporary directory and SMTP is always stubbed.
"""
import multiprocessing
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend import models, scheduler
from backend.db import Base
from backend.scheduler_models import DailyReviewDelivery

NOW = datetime(2026, 11, 18, 9, 5, tzinfo=timezone(timedelta(hours=8)))


@pytest.fixture
def delivery_db(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "delivery.db").replace("\\", "/")
    engine = create_engine(url, connect_args={"timeout": 15})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add(models.Settings(id=1, email="reader@example.com", push_time="09:00",
                               app_base_url="http://localhost:8000"))
        question = models.Question(question_text="How does a lock work?", category="Concurrency",
                                   reference_answer="Mutual exclusion")
        db.add(question)
        db.flush()
        db.add(models.ReviewSchedule(question_id=question.id, status="pending", stage=1,
                                     next_review_at=datetime(2026, 11, 17)))
        db.commit()
    monkeypatch.setattr(scheduler, "SessionLocal", sessions)
    monkeypatch.setattr(scheduler, "_smtp_configured", lambda: True)
    yield url, sessions
    engine.dispose()


def _delivery_worker(url, barrier, results):
    # A fresh SQLAlchemy engine/session per process exercises database ownership,
    # not a shared Python lock or an in-memory test-only connection.
    engine = create_engine(url, connect_args={"timeout": 15})
    scheduler.SessionLocal = sessionmaker(bind=engine)
    scheduler._smtp_configured = lambda: True

    def send(*args):
        results.put("smtp")
        return True

    scheduler.send_review_email = send
    barrier.wait(timeout=20)
    results.put(scheduler.run_daily_review(now=NOW, respect_schedule=True))
    engine.dispose()


def test_independent_workers_send_once(delivery_db):
    url, sessions = delivery_db
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    barrier = context.Barrier(3)
    workers = [context.Process(target=_delivery_worker, args=(url, barrier, results)) for _ in range(3)]
    for worker in workers:
        worker.start()
    try:
        for worker in workers:
            worker.join(timeout=30)
            assert not worker.is_alive(), "scheduler worker did not complete"
            assert worker.exitcode == 0
        messages = [results.get(timeout=5) for _ in range(4)]
        assert messages.count("smtp") == 1
        assert sorted(value for value in messages if value != "smtp") == [0, 0, 1]
        with sessions() as db:
            claim = db.query(DailyReviewDelivery).one()
            assert claim.status == "sent"
            assert claim.delivery_day == NOW.date()
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
        results.close()


def test_restart_keeps_claim_and_next_local_day_is_independent(delivery_db, monkeypatch):
    _, sessions = delivery_db
    sent = []
    monkeypatch.setattr(scheduler, "send_review_email", lambda *args: sent.append(args) or True)
    assert scheduler.run_daily_review(now=NOW) == 1
    # New sessions simulate a restarted worker; no process-global deduplication.
    monkeypatch.setattr(scheduler, "SessionLocal", sessionmaker(bind=sessions.kw["bind"]))
    assert scheduler.run_daily_review(now=NOW + timedelta(hours=3)) == 0
    assert scheduler.run_daily_review(now=NOW + timedelta(days=1)) == 1
    assert len(sent) == 2


@pytest.mark.parametrize("raises", [False, True])
def test_uncertain_smtp_result_is_not_automatically_retried(delivery_db, monkeypatch, raises):
    _, sessions = delivery_db
    attempts = []

    def send(*args):
        attempts.append(args)
        if raises:
            raise OSError("connection lost after SMTP acceptance")
        return False

    monkeypatch.setattr(scheduler, "send_review_email", send)
    assert scheduler.run_daily_review(now=NOW) == 0
    assert scheduler.run_daily_review(now=NOW + timedelta(minutes=1)) == 0
    assert len(attempts) == 1
    with sessions() as db:
        assert db.query(DailyReviewDelivery).one().status == "unknown"


def test_crash_after_claim_does_not_send_again(delivery_db, monkeypatch):
    _, sessions = delivery_db

    def crash(*args):
        raise SystemExit("simulated process exit before delivery confirmation")

    monkeypatch.setattr(scheduler, "send_review_email", crash)
    with pytest.raises(SystemExit):
        scheduler.run_daily_review(now=NOW)
    with sessions() as db:
        assert db.query(DailyReviewDelivery).one().status == "claimed"
    attempts = []
    monkeypatch.setattr(scheduler, "send_review_email", lambda *args: attempts.append(args) or True)
    assert scheduler.run_daily_review(now=NOW) == 0
    assert not attempts


def test_schedule_updates_are_read_by_existing_worker(delivery_db, monkeypatch):
    _, sessions = delivery_db
    sent = []
    monkeypatch.setattr(scheduler, "send_review_email", lambda *args: sent.append(args) or True)
    with sessions() as db:
        db.query(models.Settings).one().push_time = "11:00"
        db.commit()
    assert scheduler.run_daily_review(now=NOW, respect_schedule=True) == 0
    with sessions() as db:
        assert db.query(DailyReviewDelivery).count() == 0
        db.query(models.Settings).one().push_time = "09:00"
        db.commit()
    assert scheduler.run_daily_review(now=NOW, respect_schedule=True) == 1
    assert len(sent) == 1


def test_no_configuration_or_no_due_items_does_not_consume_daily_claim(delivery_db, monkeypatch):
    _, sessions = delivery_db
    monkeypatch.setattr(scheduler, "_smtp_configured", lambda: False)
    assert scheduler.run_daily_review(now=NOW) == 0
    monkeypatch.setattr(scheduler, "_smtp_configured", lambda: True)
    with sessions() as db:
        db.query(models.ReviewSchedule).one().next_review_at = datetime(2026, 11, 19)
        db.commit()
    assert scheduler.run_daily_review(now=NOW) == 0
    with sessions() as db:
        assert db.query(DailyReviewDelivery).count() == 0


def test_failed_confirmation_commit_keeps_claim_after_smtp_accepts(delivery_db, monkeypatch):
    _, sessions = delivery_db
    sent = []
    monkeypatch.setattr(scheduler, "send_review_email", lambda *args: sent.append(args) or True)
    original_commit = Session.commit
    commits = 0

    def commit(db):
        nonlocal commits
        commits += 1
        if commits == 2:
            raise RuntimeError("database unavailable after successful SMTP send")
        return original_commit(db)

    monkeypatch.setattr(Session, "commit", commit)
    assert scheduler.run_daily_review(now=NOW) == 0
    assert scheduler.run_daily_review(now=NOW) == 0
    assert len(sent) == 1
    with sessions() as db:
        assert db.query(DailyReviewDelivery).one().status == "claimed"


def test_scheduler_registers_polling_and_pending_retry_jobs(monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler
    from backend.retry import run_pending_retries

    # Keep APScheduler's real trigger/job validation, but never start its thread.
    monkeypatch.setattr(BackgroundScheduler, "start", lambda self: None)
    instance = scheduler.start_scheduler()
    mail = instance.get_job("daily_review")
    retries = instance.get_job("pending_judgments")
    assert mail.func is scheduler._daily_review
    assert retries.func is run_pending_retries
    for job in (mail, retries):
        assert job.trigger.interval.total_seconds() == 60
        assert job.max_instances == 1
        assert job.coalesce is True
