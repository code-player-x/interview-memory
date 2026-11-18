"""持久化 pending 判题重试：短事务领取、事务外远端请求、幂等落库。

每分钟最多处理 10 条，失败按 1/2/4/.../60 分钟退避；领取租约 120 秒，
进程崩溃后可恢复。结果、统计及错题副作用在同一个事务中提交。
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError

from . import models
from .db import SessionLocal
from .judge import has_remote_judge, judge
from .learning import _ensure_review_schedule, _update_wrong_book
from .retry_models import JudgmentRetry

log = logging.getLogger(__name__)
RETRY_BATCH_SIZE = 10
LEASE_SECONDS = 120


def enqueue_pending(db, submission, activity_day=None, judge_input=None):
    """调用方的提交事务内入队，不另增答题次数；旧数据按服务器本地日回填。"""
    submitted_at = submission.submitted_at or datetime.utcnow()
    activity_day = activity_day or submitted_at.replace(tzinfo=timezone.utc).astimezone().date()
    question_text, reference_answer = judge_input or (None, None)
    try:
        with db.begin_nested():
            db.add(JudgmentRetry(
                submission_id=submission.id, activity_day=activity_day,
                question_text=question_text, reference_answer=reference_answer,
                attempts=0, next_attempt_at=datetime.utcnow() + timedelta(minutes=1),
            ))
            db.flush()
    except IntegrityError:
        # 另一进程已回填同一条提交。
        pass


def _backfill_pending():
    with SessionLocal() as db:
        # 保留历史作答，终止已删除题目的 pending，防止每轮回填同一孤儿。
        db.query(models.Submission).filter(
            models.Submission.judge_by == "pending",
            ~models.Submission.question_id.in_(db.query(models.Question.id)),
        ).update({"judge_by": "cancelled", "explanation": "题目已删除，已停止判题"}, synchronize_session=False)
        db.query(JudgmentRetry).filter(~JudgmentRetry.submission_id.in_(
            db.query(models.Submission.id).filter(models.Submission.judge_by == "pending")
        )).delete(synchronize_session=False)
        rows = (db.query(models.Submission).outerjoin(
            JudgmentRetry, JudgmentRetry.submission_id == models.Submission.id,
        ).filter(
            models.Submission.judge_by == "pending", models.Submission.is_correct.is_(None),
            JudgmentRetry.submission_id.is_(None),
        ).order_by(models.Submission.id).limit(RETRY_BATCH_SIZE).all())
        for submission in rows:
            enqueue_pending(db, submission)
        db.commit()


def _claim(submission_id, now):
    """条件 UPDATE 是跨 worker 的领取闸门；提交后才发请求，不长占数据库锁。"""
    token = uuid.uuid4().hex
    with SessionLocal() as db:
        changed = (db.query(JudgmentRetry).filter(
            JudgmentRetry.submission_id == submission_id,
            JudgmentRetry.next_attempt_at <= now,
            or_(JudgmentRetry.lease_until.is_(None), JudgmentRetry.lease_until <= now),
        ).update({
            "claim_token": token, "lease_until": now + timedelta(seconds=LEASE_SECONDS),
            "attempts": JudgmentRetry.attempts + 1,
        }, synchronize_session=False))
        if not changed:
            return None
        row = (db.query(models.Submission, models.Question, JudgmentRetry).join(
            models.Question, models.Question.id == models.Submission.question_id,
        ).join(JudgmentRetry, JudgmentRetry.submission_id == models.Submission.id).filter(
            models.Submission.id == submission_id,
            models.Submission.judge_by == "pending", models.Submission.is_correct.is_(None),
        ).first())
        if row is None:
            db.query(models.Submission).filter(
                models.Submission.id == submission_id, models.Submission.judge_by == "pending",
                ~models.Submission.question_id.in_(db.query(models.Question.id)),
            ).update({"judge_by": "cancelled", "explanation": "题目已删除，已停止判题"}, synchronize_session=False)
            db.query(JudgmentRetry).filter_by(submission_id=submission_id).delete()
            db.commit()
            return None
        submission, question, retry = row
        # SQLite 可复用被删除的最大题号。历史记录只有在题目确实早于作答时
        # 才能用当前内容补快照；已保存的快照也不能写到一个已知的替代题上。
        dated = question.created_at is not None and submission.submitted_at is not None
        if ((dated and question.created_at > submission.submitted_at)
                or (not dated and retry.question_text is None)):
            submission.judge_by = "cancelled"
            submission.explanation = "无法确认历史作答对应的原题，已停止判题"
            db.delete(retry)
            db.commit()
            return None
        # 旧队列缺少原题快照，首次领取时固定当前内容，后续重试沿用。
        if retry.question_text is None:
            retry.question_text = question.question_text
            retry.reference_answer = question.reference_answer or ""
        data = {
            "id": submission_id, "token": token, "attempts": retry.attempts,
            "question_created_at": question.created_at,
            "question": retry.question_text, "reference": retry.reference_answer or "",
            "answer": submission.user_answer or "",
        }
        db.commit()
        return data


def _defer(claim, now):
    delay = min(60 * 2 ** min(claim["attempts"] - 1, 6), 3600)
    with SessionLocal() as db:
        db.query(JudgmentRetry).filter_by(
            submission_id=claim["id"], claim_token=claim["token"],
        ).update({
            "next_attempt_at": now + timedelta(seconds=delay),
            "claim_token": None, "lease_until": None,
        }, synchronize_session=False)
        db.commit()


def _complete(claim, result, now):
    is_correct, explanation, error_reason, source = result
    # pending 只允许真实远端恢复，不可因移除了凭据而用启发式改写历史结果。
    if not isinstance(is_correct, bool) or source not in {"agent", "llm"}:
        _defer(claim, now)
        return False
    with SessionLocal() as db:
        submission = db.get(models.Submission, claim["id"])
        # 与删题路径采用相同锁顺序：先锁题，再锁队列/提交。
        exists = submission is not None and db.query(models.Question).filter_by(
            id=submission.question_id,
        ).update({"id": models.Question.id}, synchronize_session=False)
        current = (db.query(models.Question.created_at).filter_by(id=submission.question_id)
                   .with_for_update().one()) if exists else None
        # 锁定仍属于本次领取的队列行，过期 worker 不能覆盖新领取者。
        owned = db.query(JudgmentRetry).filter_by(
            submission_id=claim["id"], claim_token=claim["token"],
        ).update({"lease_until": now}, synchronize_session=False)
        if not owned:
            return False
        retry = db.query(JudgmentRetry).filter_by(submission_id=claim["id"]).one()
        if current is None or current.created_at != claim["question_created_at"]:
            db.query(models.Submission).filter_by(id=claim["id"], judge_by="pending").update(
                {"judge_by": "cancelled", "explanation": "题目已删除，已停止判题"}, synchronize_session=False)
            db.delete(retry)
            db.commit()
            return False
        changed = db.query(models.Submission).filter(
            models.Submission.id == claim["id"], models.Submission.judge_by == "pending",
            models.Submission.is_correct.is_(None),
        ).update({"is_correct": is_correct, "explanation": explanation, "judge_by": source},
                 synchronize_session=False)
        if changed:
            # 原提交已计入 answered；仅补充当时日期的正误计数。
            field = models.Activity.correct if is_correct else models.Activity.wrong
            db.query(models.Activity).filter_by(day=retry.activity_day).update(
                {field: func.coalesce(field, 0) + 1}, synchronize_session=False,
            )
            if is_correct is False:
                # 晚到的旧错只更新历史次数和首错时间，保留近期掌握状态。
                wrong_at = submission.submitted_at or now
                first_wrong_at = models.WrongBook.first_wrong_at
                newer = db.query(models.WrongBook).filter(
                    models.WrongBook.question_id == submission.question_id,
                    models.WrongBook.updated_at > wrong_at,
                ).update({
                    "wrong_count": func.coalesce(models.WrongBook.wrong_count, 1) + 1,
                    "first_wrong_at": case((or_(first_wrong_at.is_(None), first_wrong_at > wrong_at),
                                            wrong_at), else_=first_wrong_at),
                }, synchronize_session=False)
                if not newer:
                    _update_wrong_book(db, submission.question_id, submission.user_answer,
                                       error_reason, wrong_at)
                    _ensure_review_schedule(db, submission.question_id, now)
        db.delete(retry)
        db.commit()
        return bool(changed)


def run_pending_retries():
    """APScheduler 同步入口，返回本轮实际完成数；无远端配置时保持队列不变。"""
    if not has_remote_judge():
        return 0
    try:
        _backfill_pending()
        now = datetime.utcnow()
        with SessionLocal() as db:
            ids = [row[0] for row in db.query(JudgmentRetry.submission_id).filter(
                JudgmentRetry.next_attempt_at <= now,
                or_(JudgmentRetry.lease_until.is_(None), JudgmentRetry.lease_until <= now),
            ).order_by(JudgmentRetry.next_attempt_at, JudgmentRetry.submission_id)
                .limit(RETRY_BATCH_SIZE).all()]
        completed = 0
        for submission_id in ids:
            claim = _claim(submission_id, datetime.utcnow())
            if claim is None:
                continue
            try:
                result = asyncio.run(judge(claim["question"], claim["reference"], claim["answer"]))
                completed += int(_complete(claim, result, datetime.utcnow()))
            except Exception:
                log.exception("Pending judgment retry failed for submission %s", submission_id)
                _defer(claim, datetime.utcnow())
        return completed
    except Exception:
        log.exception("Pending judgment retry batch failed")
        return 0
