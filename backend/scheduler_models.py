"""Durable, cross-worker claims for daily email delivery attempts.

SMTP cannot participate in the database transaction. A committed claim is never
reclaimed automatically, including after a crash: the server might have already
accepted the message. This gives at-most-once attempts per recipient/local day,
not a promise of exactly-once delivery.
"""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Integer, String

from .db import Base


class DailyReviewDelivery(Base):
    __tablename__ = "daily_review_deliveries"

    # Hash includes the recipient and date; uniqueness is enforced by the DB,
    # not an in-process lock, so independent workers compete safely.
    delivery_key = Column(String(64), primary_key=True)
    delivery_day = Column(Date, nullable=False)
    status = Column(String(16), nullable=False, default="claimed")
    item_count = Column(Integer, nullable=False)
    claimed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime)
