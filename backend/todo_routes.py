"""待办清单 + 番茄专注 API（挂载到 /api/todos）。

- 待办：列表 / 新建 / 更新 / 软删除（deleted=True）。
- 番茄专注：start 创建 FocusSession，stop 结算 actual_minutes（供成长中心统计）。
后端 app.py 通过 app.include_router(todo_router) 挂载。
"""
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .db import get_db
from . import models

router = APIRouter(prefix="/api/todos", tags=["todos"])


class TodoIn(BaseModel):
    title: str
    note: str = ""
    category: str = ""
    priority: int = 1
    due_date: Optional[str] = None  # YYYY-MM-DD


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    note: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[int] = None
    due_date: Optional[str] = None
    done: Optional[bool] = None


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _todo_out(t: models.Todo) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "note": t.note or "",
        "category": t.category or "",
        "priority": t.priority,
        "due_date": t.due_date.isoformat() if t.due_date else "",
        "done": bool(t.done),
        "done_at": t.done_at.isoformat() if t.done_at else "",
        "created_at": t.created_at.isoformat() if t.created_at else "",
        "order_no": t.order_no,
        "deleted": bool(t.deleted),
    }


@router.get("")
def list_todos(done: Optional[bool] = None, db: Session = Depends(get_db)):
    q = db.query(models.Todo).filter(models.Todo.deleted == False)
    if done is not None:
        q = q.filter(models.Todo.done == done)
    rows = q.order_by(models.Todo.order_no, models.Todo.id).all()
    return [_todo_out(t) for t in rows]


@router.post("")
def create_todo(p: TodoIn, db: Session = Depends(get_db)):
    max_no = db.query(models.Todo.order_no).order_by(models.Todo.order_no.desc()).first()
    order_no = (max_no[0] + 1) if max_no and max_no[0] is not None else 0
    t = models.Todo(
        title=p.title,
        note=p.note,
        category=p.category,
        priority=p.priority,
        due_date=_parse_date(p.due_date),
        done=False,
        order_no=order_no,
        created_at=datetime.utcnow(),
        deleted=False,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _todo_out(t)


@router.put("/{tid}")
def update_todo(tid: int, p: TodoUpdate, db: Session = Depends(get_db)):
    t = db.query(models.Todo).filter(models.Todo.id == tid, models.Todo.deleted == False).first()
    if not t:
        raise HTTPException(status_code=404, detail="待办不存在")
    if p.title is not None:
        t.title = p.title
    if p.note is not None:
        t.note = p.note
    if p.category is not None:
        t.category = p.category
    if p.priority is not None:
        t.priority = p.priority
    if p.due_date is not None:
        t.due_date = _parse_date(p.due_date)
    if p.done is not None:
        t.done = p.done
        t.done_at = datetime.utcnow() if p.done else None
    db.commit()
    db.refresh(t)
    return _todo_out(t)


@router.delete("/{tid}")
def delete_todo(tid: int, db: Session = Depends(get_db)):
    t = db.query(models.Todo).filter(models.Todo.id == tid, models.Todo.deleted == False).first()
    if not t:
        raise HTTPException(status_code=404, detail="待办不存在")
    t.deleted = True
    db.commit()
    return {"status": "deleted", "id": tid}


@router.post("/{tid}/focus/start")
def focus_start(tid: int, minutes: int = 25, db: Session = Depends(get_db)):
    t = db.query(models.Todo).filter(models.Todo.id == tid, models.Todo.deleted == False).first()
    if not t:
        raise HTTPException(status_code=404, detail="待办不存在")
    fs = models.FocusSession(
        todo_id=tid,
        kind="pomodoro",
        minutes=minutes,
        started_at=datetime.utcnow(),
        completed=False,
    )
    db.add(fs)
    db.commit()
    db.refresh(fs)
    return {"id": fs.id, "started_at": fs.started_at.isoformat() if fs.started_at else ""}


@router.post("/{tid}/focus/stop")
def focus_stop(tid: int, session_id: int = None, db: Session = Depends(get_db)):
    q = db.query(models.FocusSession).filter(
        models.FocusSession.todo_id == tid, models.FocusSession.completed == False
    )
    if session_id:
        q = q.filter(models.FocusSession.id == session_id)
    fs = q.order_by(models.FocusSession.id.desc()).first()
    if not fs:
        raise HTTPException(status_code=404, detail="无进行中的专注会话")
    fs.ended_at = datetime.utcnow()
    fs.actual_minutes = (
        int((fs.ended_at - fs.started_at).total_seconds() // 60) if fs.started_at else 0
    )
    fs.completed = True
    db.commit()
    return {"id": fs.id, "actual_minutes": fs.actual_minutes}
