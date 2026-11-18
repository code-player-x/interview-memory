"""持久化判题重试队列，与历史 submissions 表兼容。"""
from sqlalchemy import Column, Date, DateTime, Integer, String, Text
from .db import Base


class JudgmentRetry(Base):
    __tablename__ = "judgment_retries"

    submission_id = Column(Integer, primary_key=True)
    activity_day = Column(Date, nullable=False)
    question_text = Column(Text)
    reference_answer = Column(Text)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=False, index=True)
    claim_token = Column(String(32))
    lease_until = Column(DateTime)
