"""后台调度器：每日复习提醒邮件推送（艾宾浩斯）。

- 优先用 APScheduler（BackgroundScheduler）注册 daily_review 定时任务；
- 若未安装 apscheduler 或启动失败，返回 _NullScheduler（no-op），保证 app 不崩；
- 邮件发送依赖环境变量 SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS，未配置则静默跳过；
- daily_review 内部任何异常都被吞掉，避免影响主进程。
"""
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

from .db import SessionLocal
from . import models


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


def _send_review_email(to_email: str, due_count: int):
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASS")
    if not (host and user and pwd):
        return  # 未配置 SMTP，跳过
    port = int(os.getenv("SMTP_PORT", "465"))
    msg = MIMEText(
        f"你有 {due_count} 道题待复习（艾宾浩斯遗忘曲线）。打开应用完成今日复习，巩固长期记忆。",
        "plain", "utf-8",
    )
    msg["Subject"] = "面试八股文 · 今日复习提醒"
    msg["From"] = user
    msg["To"] = to_email
    try:
        with smtplib.SMTP_SSL(host, port) as s:
            s.login(user, pwd)
            s.sendmail(user, [to_email], msg.as_string())
    except Exception:
        pass


def _daily_review():
    db = SessionLocal()
    try:
        s = db.query(models.Settings).first()
        if not s or not s.email:
            return
        due = db.query(models.ReviewSchedule).filter(
            models.ReviewSchedule.status == "pending",
            models.ReviewSchedule.next_review_at <= datetime.utcnow(),
        ).count()
        if due > 0:
            _send_review_email(s.email, due)
    except Exception:
        pass
    finally:
        db.close()


def start_scheduler():
    """启动后台调度器，返回 scheduler 对象（供 app.py 调用 reschedule_job）。"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return _NullScheduler()
    try:
        sched = BackgroundScheduler()
        # 默认 09:00 推送；app.py 更新设置时会 reschedule_job 调整
        sched.add_job(_daily_review, "cron", hour=9, minute=0, id="daily_review")
        sched.start()
        return sched
    except Exception:
        return _NullScheduler()
