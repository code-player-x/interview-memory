"""Read-only health information. No answers, recipient addresses or credentials."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .db import get_db
from .models import Submission
from .retry_models import JudgmentRetry
from .scheduler_models import DailyReviewDelivery

router = APIRouter()


@router.get("/api/admin/jobs", summary="后台任务状态")
def job_status(request: Request, db: Session = Depends(get_db)):
    worker = getattr(request.app.state, "scheduler", None)
    running = bool(getattr(worker, "running", False))
    count, oldest = db.query(func.count(JudgmentRetry.submission_id),
                             func.min(JudgmentRetry.next_attempt_at)).one()
    delivery = db.query(DailyReviewDelivery).order_by(DailyReviewDelivery.claimed_at.desc()).first()
    pending, oldest_pending = db.query(func.count(Submission.id), func.min(Submission.submitted_at)).filter(
        Submission.is_correct.is_(None), Submission.judge_by == "pending"
    ).one()
    return {
        "scheduler": "running" if running else ("unavailable" if worker is not None else "disabled"),
        "last_worker_events": getattr(worker, "last_events", {}),
        "next_runs": {job.id: job.next_run_time for job in worker.get_jobs()} if running else {},
        "queued_judgments": count, "oldest_scheduled_retry_utc": oldest,
        "pending_submissions": pending, "oldest_pending_submission_utc": oldest_pending,
        "latest_delivery": {"day": delivery.delivery_day, "status": delivery.status,
                            "items": delivery.item_count} if delivery else None,
    }
