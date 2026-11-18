"""后台调度器：每日复习提醒邮件推送（艾宾浩斯）。

- 优先用 APScheduler（BackgroundScheduler）注册 daily_review 定时任务；
- 若未安装 apscheduler 或启动失败，返回 _NullScheduler（no-op），保证 app 不崩；
- 邮件发送由 emailer 固定模板处理，依赖 SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD；
- 每分钟读取持久化推送时间，各 worker 通过数据库唯一领取避免重复邮件。
- SMTP 结果不确定或进程崩溃时不自动重发，避免已被 SMTP 接收的邮件重复。
"""
import hashlib
import logging
import os
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from .db import SessionLocal
from . import models
from .emailer import send_review_email
from .scheduler_models import DailyReviewDelivery

logger = logging.getLogger(__name__)


def _local_now() -> datetime:
    """Match the host/container timezone used by the existing schedule and email."""
    return datetime.now().astimezone()


def _smtp_configured() -> bool:
    # Do not consume today's claim if SMTP has not been configured yet.
    return all((os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"),
                os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS")))


def _parse_push_time(raw) -> tuple[int, int]:
    try:
        hour_text, minute_text = str(raw or "09:00").strip().split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (TypeError, ValueError):
        pass
    return 9, 0


class _NullScheduler:
    """APScheduler 不可用时的安全占位，提供 app.py 所需的全部方法（no-op）。"""

    def start(self, *a, **k):
        pass

    def shutdown(self, *a, **k):
        pass

    def add_job(self, *a, **k):
        pass

    def reschedule_job(self, *a, **k):
        pass

    def get_job(self, *a, **k):
        return None


def run_daily_review(*, respect_schedule: bool = False, now: datetime = None) -> int:
    """Try one daily email; return the question count only for a confirmed send.

    Scheduled invocations check the current persisted push time on every poll.
    Direct/manual invocations may bypass the time, but share the same daily claim.
    A claimed or unknown attempt is intentionally not retried: SMTP acceptance
    and recording success cannot be made atomic. The next local day has a new key.
    """
    local_now = now or _local_now()
    if local_now.tzinfo is None:
        local_now = local_now.astimezone()
    utc_now = local_now.astimezone(timezone.utc).replace(tzinfo=None)
    db = SessionLocal()
    claim = None
    try:
        s = db.query(models.Settings).first()
        if not s or not s.email or not _smtp_configured():
            return 0
        if respect_schedule and (local_now.hour, local_now.minute) < _parse_push_time(s.push_time):
            return 0
        recipient = s.email.strip()
        if not recipient:
            return 0
        delivery_key = hashlib.sha256(
            (local_now.date().isoformat() + "\n" + recipient.casefold()).encode("utf-8")
        ).hexdigest()
        # Fast path only: the unique insert below is the actual atomic claim.
        if db.get(DailyReviewDelivery, delivery_key) is not None:
            return 0
        rows = db.query(models.ReviewSchedule, models.WrongBook, models.Question).join(
            models.Question, models.ReviewSchedule.question_id == models.Question.id
        ).outerjoin(
            models.WrongBook, models.WrongBook.question_id == models.ReviewSchedule.question_id
        ).filter(
            models.ReviewSchedule.status == "pending",
            models.ReviewSchedule.next_review_at <= utc_now,
        ).order_by(models.ReviewSchedule.next_review_at).all()
        items = [
            {
                "category": question.category,
                "question_text": question.question_text,
                "reference_answer": question.reference_answer,
                "last_user_answer": wrong.last_user_answer if wrong else "",
                "first_wrong_at": wrong.first_wrong_at if wrong else None,
                "wrong_count": wrong.wrong_count if wrong else 1,
            }
            for _schedule, wrong, question in rows
        ]
        if not items:
            return 0
        base_url = (s.app_base_url or "http://localhost:8000").rstrip("/")
        claim = DailyReviewDelivery(
            delivery_key=delivery_key, delivery_day=local_now.date(),
            status="claimed", item_count=len(items), claimed_at=utc_now,
        )
        db.add(claim)
        try:
            db.commit()
        except IntegrityError:
            # Another process won. Rollback before returning to keep the session usable.
            db.rollback()
            return 0
        try:
            sent = send_review_email(recipient, items, base_url)
        except Exception:
            sent = False
            logger.exception("Daily review SMTP attempt raised an error")
        claim.status = "sent" if sent else "unknown"
        claim.finished_at = datetime.utcnow()
        db.commit()
        if not sent:
            logger.warning("Daily review SMTP outcome unconfirmed; daily claim retained to prevent duplicates")
        return len(items) if sent else 0
    except Exception:
        # A committed claim remains durable if recording the result fails.
        db.rollback()
        logger.exception("Daily review delivery task failed")
        return 0
    finally:
        db.close()


def _daily_review():
    """APScheduler 入口：异常由 run_daily_review 吞掉，不影响主进程。"""
    run_daily_review(respect_schedule=True)


def _configured_push_time() -> tuple[int, int]:
    """读取持久化推送时间；旧库/异常配置安全回退到 09:00。"""
    db = SessionLocal()
    try:
        setting = db.query(models.Settings.push_time).first()
        return _parse_push_time(setting[0] if setting else "09:00")
    finally:
        db.close()


def start_scheduler():
    """Start polling jobs; workers consult persisted settings instead of stale cron state."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return _NullScheduler()
    try:
        sched = BackgroundScheduler()
        from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
        sched.last_events = {}
        def remember(event):
            # Replace the dictionary so concurrent status reads see a stable snapshot.
            outcome = {EVENT_JOB_EXECUTED: "returned", EVENT_JOB_ERROR: "error",
                       EVENT_JOB_MISSED: "missed"}[event.code]
            sched.last_events = {**sched.last_events, event.job_id: {
                "at": datetime.now(timezone.utc).isoformat(), "outcome": outcome}}
        sched.add_listener(remember, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED)
        from .retry import run_pending_retries
        sched.add_job(_daily_review, "interval", seconds=60, id="daily_review",
                      max_instances=1, coalesce=True)
        sched.add_job(run_pending_retries, "interval", seconds=60, id="pending_judgments",
                      max_instances=1, coalesce=True)
        sched.start()
        return sched
    except Exception:
        logger.exception("Background scheduler failed to start")
        return _NullScheduler()
