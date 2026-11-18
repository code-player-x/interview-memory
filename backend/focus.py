"""专注记录兼容：focus 使用本地时间，历史 pomodoro 使用 UTC。"""
from datetime import timezone
from sqlalchemy import and_, or_
from . import models

FOCUS_KINDS = ("focus", "pomodoro")


def completed_focus(db, start, end):
    utc_start = start.astimezone(timezone.utc).replace(tzinfo=None)
    utc_end = end.astimezone(timezone.utc).replace(tzinfo=None)
    return db.query(models.FocusSession).filter(
        models.FocusSession.completed.is_(True),
        or_(
            and_(models.FocusSession.kind == "focus", models.FocusSession.started_at >= start,
                 models.FocusSession.started_at <= end),
            and_(models.FocusSession.kind == "pomodoro", models.FocusSession.started_at >= utc_start,
                 models.FocusSession.started_at <= utc_end),
        ),
    )


def local_started_at(session):
    if session.kind == "pomodoro" and session.started_at:
        return session.started_at.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    return session.started_at
