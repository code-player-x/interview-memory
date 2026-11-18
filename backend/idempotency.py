"""可选请求幂等：跨 worker 领取，响应与学习状态同事务落库。"""
import asyncio
import hashlib
import json
import uuid
import logging
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .db import Base

LEASE_DURATION = timedelta(minutes=10)
RENEW_INTERVAL_SECONDS = 60


class AnswerRequest(Base):
    __tablename__ = "answer_requests"
    key = Column(String(64), primary_key=True)
    fingerprint = Column(String(64), nullable=False)
    token = Column(String(32), nullable=False)
    lease_until = Column(DateTime, nullable=False)
    response = Column(Text().with_variant(LONGTEXT(), "mysql"))


def begin_request(db, scope, payload):
    request_id = payload.request_id
    if not request_id:
        return None, None
    content = payload.model_dump(exclude={"request_id"})
    fingerprint = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    key = hashlib.sha256((scope + ":" + request_id).encode()).hexdigest()
    token = uuid.uuid4().hex
    now = datetime.utcnow()
    try:
        with db.begin_nested():
            db.add(AnswerRequest(key=key, fingerprint=fingerprint, token=token,
                                 lease_until=now + LEASE_DURATION))
            db.flush()
        db.commit()
        return (key, token), None
    except IntegrityError:
        row = db.get(AnswerRequest, key)
        if row is None:
            # 已知失败的领取者可能恰在本次唯一冲突后释放了 key。
            db.rollback()
            return begin_request(db, scope, payload)
        if row.fingerprint != fingerprint:
            raise HTTPException(409, "request_id 已用于不同作答")
        if row.response is not None:
            return None, json.loads(row.response)
        reclaimed = db.query(AnswerRequest).filter(
            AnswerRequest.key == key, AnswerRequest.response.is_(None), AnswerRequest.lease_until <= now,
        ).update({"token": token, "lease_until": now + LEASE_DURATION}, synchronize_session=False)
        db.commit()
        if not reclaimed:
            raise HTTPException(409, "该次作答仍在处理中，请稍后重试")
        return (key, token), None


def _renew_request(engine, claim):
    key, token = claim
    with Session(engine) as db:
        changed = db.query(AnswerRequest).filter_by(key=key, token=token, response=None).update(
            {"lease_until": datetime.utcnow() + LEASE_DURATION}, synchronize_session=False,
        )
        db.commit()
        return bool(changed)


async def judge_with_lease(db, claim, grading):
    """远端判题期间以独立短事务续租；进程退出后，其他 worker 仍可接管。"""
    if claim is None:
        return await grading
    engine = db.get_bind()
    work = asyncio.ensure_future(grading)
    try:
        while not work.done():
            done, _ = await asyncio.wait({work}, timeout=RENEW_INTERVAL_SECONDS)
            if not done:
                try:
                    owned = await asyncio.to_thread(_renew_request, engine, claim)
                except SQLAlchemyError:
                    logging.getLogger(__name__).exception("Unable to renew answer request")
                    continue
                if not owned:
                    raise HTTPException(409, "该次作答已由其他请求接管，请重试获取结果")
        return work.result()
    finally:
        if not work.done():
            work.cancel()
            await asyncio.gather(work, return_exceptions=True)


def finish_request(db, claim, response):
    if claim is None:
        return
    key, token = claim
    changed = db.query(AnswerRequest).filter_by(key=key, token=token, response=None).update(
        {"response": json.dumps(response, ensure_ascii=False)}, synchronize_session=False,
    )
    if not changed:
        db.rollback()
        raise HTTPException(409, "该次作答已由其他请求接管，请重试获取结果")


def release_request(db, claim):
    """已知失败先回滚学习状态，再只释放本 worker 未完成的领取。

    提交结果不确定时若成功缓存已存在则保留，不能把已完成请求变成新作答。
    释放本身遇到数据库故障时保留租约恢复，不掩盖原异常。
    """
    db.rollback()
    if claim is None:
        return
    key, token = claim
    try:
        db.query(AnswerRequest).filter_by(key=key, token=token, response=None).delete(synchronize_session=False)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logging.getLogger(__name__).exception("Unable to release failed answer request")
