"""后台调度器：每日复习提醒邮件推送（艾宾浩斯）。

- 优先用 APScheduler（BackgroundScheduler）注册 daily_review 定时任务；
- 若未安装 apscheduler 或启动失败，返回 _NullScheduler（no-op），保证 app 不崩；
- 邮件发送由 emailer 固定模板处理，依赖 SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD；
- daily_review 内部任何异常都被吞掉，避免影响主进程。
"""
from datetime import datetime

from .db import SessionLocal
from . import models
from .emailer import send_review_email


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


def run_daily_review() -> int:
    """发送当天到期题目的固定模板邮件，成功发送时返回题目数。"""
    db = SessionLocal()
    try:
        s = db.query(models.Settings).first()
        if not s or not s.email:
            return 0
        rows = db.query(models.ReviewSchedule, models.WrongBook, models.Question).join(
            models.Question, models.ReviewSchedule.question_id == models.Question.id
        ).outerjoin(
            models.WrongBook, models.WrongBook.question_id == models.ReviewSchedule.question_id
        ).filter(
            models.ReviewSchedule.status == "pending",
            models.ReviewSchedule.next_review_at <= datetime.utcnow(),
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
        return len(items) if send_review_email(s.email, items, base_url) else 0
    except Exception:
        return 0
    finally:
        db.close()


def _daily_review():
    """APScheduler 入口：异常由 run_daily_review 吞掉，不影响主进程。"""
    run_daily_review()


def _configured_push_time() -> tuple[int, int]:
    """读取持久化推送时间；旧库/异常配置安全回退到 09:00。"""
    db = SessionLocal()
    try:
        setting = db.query(models.Settings.push_time).first()
        raw = (setting[0] if setting else "09:00") or "09:00"
        hour_text, minute_text = str(raw).strip().split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (TypeError, ValueError):
        pass
    finally:
        db.close()
    return 9, 0


def start_scheduler():
    """启动后台调度器，返回 scheduler 对象（供 app.py 调用 reschedule_job）。"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return _NullScheduler()
    try:
        sched = BackgroundScheduler()
        # 进程重启后从持久化设置恢复；更新接口仍会即时 reschedule。
        hour, minute = _configured_push_time()
        sched.add_job(_daily_review, "cron", hour=hour, minute=minute, id="daily_review")
        sched.start()
        return sched
    except Exception:
        return _NullScheduler()
