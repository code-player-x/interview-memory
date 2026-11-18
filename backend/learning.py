"""作答与后台重试共用的错题、复习状态写入；调用方负责事务。"""
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from . import models
from .ebbinghaus import get_steps, next_review_for_stage


def _update_wrong_book(db: Session, question_id: int, user_answer: str, error_reason: str, now: datetime):
    """原子创建或更新错题本；唯一索引和 savepoint 覆盖首写竞争。"""
    values = {
        # 历史 NULL 表示至少已经记录过一次，不应在下一次答错时退回为 1。
        "wrong_count": func.coalesce(models.WrongBook.wrong_count, 1) + 1,
        "last_user_answer": user_answer,
        "error_reason": error_reason or models.WrongBook.error_reason,
        "mastery": "reviewing",
        "updated_at": now,
        "first_wrong_at": func.coalesce(models.WrongBook.first_wrong_at, now),
    }
    updated = (db.query(models.WrongBook)
               .filter(models.WrongBook.question_id == question_id)
               .update(values, synchronize_session=False))
    if updated:
        return

    try:
        with db.begin_nested():
            db.add(models.WrongBook(
                question_id=question_id,
                first_wrong_at=now,
                wrong_count=1,
                last_user_answer=user_answer,
                error_reason=error_reason or "",
                mastery="learning",
                updated_at=now,
            ))
            db.flush()
    except IntegrityError:
        # 另一个请求刚好插入同题行，保持其首错时间并给它原子加一。
        (db.query(models.WrongBook)
           .filter(models.WrongBook.question_id == question_id)
           .update(values, synchronize_session=False))


def _ensure_review_schedule(db: Session, question_id: int, now: datetime):
    """首次答错建计划，已掌握后再答错重新进入复习，保留累计复习次数。"""
    existing = (db.query(models.ReviewSchedule)
            .filter(models.ReviewSchedule.question_id == question_id)
            .first())
    if existing and existing.status != "done":
        return
    # 这里不能调用会 commit 的 get_settings，作答的全部副作用必须保持同事务。
    setting = db.query(models.Settings.ebbinghaus_steps).first()
    steps = get_steps(setting[0] if setting else "")
    next_review_at = next_review_for_stage(1, steps, base=now)
    if existing:
        (db.query(models.ReviewSchedule)
           .filter(models.ReviewSchedule.question_id == question_id,
                   models.ReviewSchedule.status == "done")
           .update({"stage": 1, "status": "pending", "next_review_at": next_review_at},
                   synchronize_session=False))
        return
    try:
        with db.begin_nested():
            db.add(models.ReviewSchedule(
                question_id=question_id,
                stage=1,
                next_review_at=next_review_at,
                review_count=0,
                status="pending",
            ))
            db.flush()
    except IntegrityError:
        # 竞争者已成功创建，无需覆盖已有的阶段或下次复习时间。
        pass
