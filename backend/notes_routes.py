"""Per-question study notes."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import models
from .db import get_db

router = APIRouter()


class NoteIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class NoteOut(BaseModel):
    id: int
    question_id: int
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ==================== 个人笔记（一题多条，单人系统） ====================
def _note_to_out(n):
    return NoteOut(
        id=n.id, question_id=n.question_id, content=n.content,
        created_at=n.created_at.isoformat() if n.created_at else None,
        updated_at=n.updated_at.isoformat() if n.updated_at else None,
    )


@router.get("/api/questions/{qid}/notes", response_model=List[NoteOut], summary="列出某题所有笔记（按时间倒序）")
def list_notes(qid: int, db: Session = Depends(get_db)):
    if not db.query(models.Question.id).filter(models.Question.id == qid).first():
        raise HTTPException(status_code=404, detail="题目不存在")
    rows = (db.query(models.QuestionNote)
              .filter(models.QuestionNote.question_id == qid)
              .order_by(models.QuestionNote.created_at.desc(),
                        models.QuestionNote.id.desc())
              .all())
    return [_note_to_out(r) for r in rows]


@router.post("/api/questions/{qid}/notes", response_model=NoteOut, summary="新增一条笔记")
def create_note(qid: int, payload: NoteIn, db: Session = Depends(get_db)):
    # 与删题共用题目行写锁，防止检查后被删除而留下孤立笔记。
    if not db.query(models.Question).filter_by(id=qid).update(
            {"id": models.Question.id}, synchronize_session=False):
        raise HTTPException(status_code=404, detail="题目不存在")
    n = models.QuestionNote(question_id=qid, content=payload.content)
    db.add(n)
    db.flush()
    result = _note_to_out(n)
    db.commit()
    return result


@router.put("/api/questions/{qid}/notes/{note_id}", response_model=NoteOut, summary="更新一条笔记")
def update_note(qid: int, note_id: int, payload: NoteIn, db: Session = Depends(get_db)):
    notes = db.query(models.QuestionNote).filter_by(id=note_id, question_id=qid)
    if not notes.update({"content": payload.content}, synchronize_session=False):
        raise HTTPException(status_code=404, detail="笔记不存在")
    result = _note_to_out(notes.populate_existing().one())
    db.commit()
    return result


@router.delete("/api/questions/{qid}/notes/{note_id}", summary="删除一条笔记")
def delete_note(qid: int, note_id: int, db: Session = Depends(get_db)):
    deleted = db.query(models.QuestionNote).filter_by(id=note_id, question_id=qid).delete(
        synchronize_session=False)
    if not deleted:
        raise HTTPException(status_code=404, detail="笔记不存在")
    db.commit()
    return {"ok": True}
