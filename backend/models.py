"""SQLAlchemy 表模型：与 interview_memory.db 真实 schema 严格对齐。
类名 = 表名 CamelCase；字段名 = 列名；类型按 PRAGMA table_info 推断。
所有字段 nullable 与默认值对齐原库，保证 app.py 的读写与现有数据兼容。
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Boolean
from sqlalchemy.sql import func as sqlfunc
from .db import Base


class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True)
    platform = Column(String(50))
    category = Column(String(100))
    tags = Column(Text)
    difficulty = Column(Integer)
    question_text = Column(Text, nullable=False)
    reference_answer = Column(Text)
    created_at = Column(DateTime)
    images = Column(Text, default="")
    keywords = Column(Text, default="")


class WrongBook(Base):
    __tablename__ = "wrong_book"
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, nullable=False)
    first_wrong_at = Column(DateTime)
    wrong_count = Column(Integer)
    last_user_answer = Column(Text)
    error_reason = Column(Text)
    mastery = Column(String(20))
    updated_at = Column(DateTime)


class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, nullable=False)
    user_answer = Column(Text)
    is_correct = Column(Boolean)
    judge_by = Column(String(20))
    explanation = Column(Text)
    submitted_at = Column(DateTime)


class ReviewSchedule(Base):
    __tablename__ = "review_schedule"
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, nullable=False)
    stage = Column(Integer)
    next_review_at = Column(DateTime)
    last_reviewed_at = Column(DateTime)
    review_count = Column(Integer)
    status = Column(String(20))


class Activity(Base):
    __tablename__ = "activity"
    day = Column(Date, primary_key=True, nullable=False)
    answered = Column(Integer)
    correct = Column(Integer)
    wrong = Column(Integer)


class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, nullable=False)
    email = Column(String(200))
    push_time = Column(String(10))
    ebbinghaus_steps = Column(Text)
    app_base_url = Column(String(200))


class CategoryMeta(Base):
    __tablename__ = "category_meta"
    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String(100), nullable=False)
    icon = Column(String(20))
    description = Column(String(200))


class InterviewExp(Base):
    __tablename__ = "interview_exp"
    id = Column(Integer, primary_key=True, nullable=False)
    company = Column(String(100))
    role = Column(String(100))
    position = Column(String(100))
    offer_result = Column(String(100))
    content = Column(Text)
    questions = Column(Text)
    created_at = Column(DateTime)


class GrowthGoal(Base):
    __tablename__ = "growth_goals"
    id = Column(Integer, primary_key=True, nullable=False)
    month = Column(String(7), nullable=False)
    target = Column(Integer)
    created_at = Column(DateTime)


class FocusSession(Base):
    __tablename__ = "focus_sessions"
    id = Column(Integer, primary_key=True, nullable=False)
    todo_id = Column(Integer)
    kind = Column(String(10))
    minutes = Column(Integer)
    actual_minutes = Column(Integer)
    completed = Column(Boolean)
    started_at = Column(DateTime)
    ended_at = Column(DateTime)


class Todo(Base):
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True)
    title = Column(String(300), nullable=False)
    note = Column(Text)
    category = Column(String(100))
    priority = Column(Integer)
    due_date = Column(Date)
    done = Column(Boolean)
    done_at = Column(DateTime)
    created_at = Column(DateTime)
    order_no = Column(Integer)
    deleted = Column(Boolean)


class QuestionNote(Base):
    """个人笔记（一题可多条；单人系统，按时间倒序展示）。

    - question_id 不建强外键，避免删题时级联误删笔记（保留用户的心血）。
      删除题目时由 app.py 显式清理对应 notes。
    - created_at/updated_at 由 SQLAlchemy 端 server_default + onupdate 维护。
    """
    __tablename__ = "question_notes"
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=sqlfunc.now())
    updated_at = Column(DateTime, server_default=sqlfunc.now(), onupdate=sqlfunc.now())
