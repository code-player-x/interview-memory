"""Synchronization preserves IDs and learning data, with rollback and retry proof."""
import sqlite3
from pathlib import Path

import pytest

from scripts import sync_questions_v2 as sync


@pytest.fixture
def corpus_db(tmp_path, monkeypatch):
    path = tmp_path / "library.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE questions (id INTEGER PRIMARY KEY, platform TEXT, category TEXT, tags TEXT,
                difficulty INTEGER, question_text TEXT, reference_answer TEXT, keywords TEXT,
                created_at TEXT, images TEXT);
            CREATE TABLE question_notes (question_id INTEGER, content TEXT);
            CREATE TABLE submissions (question_id INTEGER, user_answer TEXT);
            CREATE TABLE wrong_book (question_id INTEGER, mastery TEXT);
            CREATE TABLE review_schedule (question_id INTEGER, stage INTEGER);
            INSERT INTO questions VALUES (10,'questions_v2','旧类','原标签',2,'原题','旧答案','旧考点','2020-01-01','保留图片');
            INSERT INTO questions VALUES (20,'questions_v2','旧类','',2,'淘汰题','归档答案','','2020-01-02','');
            INSERT INTO questions VALUES (30,'manual','自定义','',3,'手工题','手工答案','','2020-01-03','');
            INSERT INTO question_notes VALUES (10,'笔记');
            INSERT INTO submissions VALUES (10,'历史回答');
            INSERT INTO wrong_book VALUES (10,'reviewing');
            INSERT INTO review_schedule VALUES (10,3);
        """)
    desired = [{"source_id": "q1", "platform": "questions_v2", "category": "新类", "tags": "新标签",
                "difficulty": 2, "question_text": "原题", "reference_answer": "新答案", "keywords": "新考点"}]
    monkeypatch.setattr(sync, "load_questions", lambda *a, **k: iter(desired))
    monkeypatch.setattr(sync, "historical_titles", lambda _: {})
    return path, desired


def snapshot(path):
    with sqlite3.connect(path) as conn:
        return list(conn.iterdump())


def test_sync_backup_in_place_and_source_id_rename_are_idempotent(corpus_db):
    path, desired = corpus_db
    before = snapshot(path)
    plan = sync.sync_database(path, prune=True)
    assert not plan["written"] and plan["updated"] == 1 and plan["pruned"] == 1
    assert snapshot(path) == before
    assert not (path.parent / "backups").exists()
    desired.append({**desired[0], "source_id": "q2", "question_text": "新增题"})
    report = sync.sync_database(path, write=True, prune=True)
    assert report["written"] and snapshot(Path(report["backup"])) == before
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT reference_answer,images,created_at FROM questions WHERE id=10").fetchone() == ("新答案", "保留图片", "2020-01-01")
        assert conn.execute("SELECT reference_answer FROM questions WHERE id=30").fetchone() == ("手工答案",)
        assert conn.execute("SELECT id FROM questions WHERE question_text='新增题'").fetchone()[0] > 30
        assert conn.execute("SELECT * FROM question_notes").fetchall() == [(10, "笔记")]
        assert conn.execute("SELECT * FROM submissions").fetchall() == [(10, "历史回答")]
        assert conn.execute("SELECT * FROM wrong_book").fetchall() == [(10, "reviewing")]
        assert conn.execute("SELECT * FROM review_schedule").fetchall() == [(10, 3)]
    desired[0]["question_text"] = "新的独立题面"
    assert sync.sync_database(path, write=True, prune=True)["updated"] == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT id FROM questions WHERE question_text='新的独立题面'").fetchone() == (10,)
    unchanged = snapshot(path)
    assert not sync.sync_database(path, write=True, prune=True)["written"]
    assert snapshot(path) == unchanged


def test_sync_refuses_to_delete_referenced_old_question(corpus_db):
    path, _ = corpus_db
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO question_notes VALUES (20, '旧题也有笔记')")
    before = snapshot(path)
    assert sync.sync_database(path, prune=True)["blocked_references"] == {"20": ["question_notes"]}
    with pytest.raises(ValueError, match="关联学习记录"):
        sync.sync_database(path, write=True, prune=True)
    assert snapshot(path) == before
    # Non-destructive updates can still proceed without prune.
    assert sync.sync_database(path, write=True)["written"]
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM questions WHERE id=20").fetchone()[0] == 1


def test_historical_title_bootstrap_preserves_question_id(corpus_db, monkeypatch):
    path, desired = corpus_db
    desired[0]["question_text"] = "新题面"
    monkeypatch.setattr(sync, "historical_titles", lambda _: {"q1": {"原题"}})
    report = sync.sync_database(path, write=True)
    assert report["added"] == 0 and report["matched"] == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT question_text FROM questions WHERE id=10").fetchone() == ("新题面",)


def test_ambiguous_titles_fail_without_writes(corpus_db):
    path, _ = corpus_db
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO questions (id,platform,question_text) VALUES (40,'questions_v2','原题')")
    before = snapshot(path)
    with pytest.raises(ValueError, match="匹配多个数据库题目"):
        sync.sync_database(path, write=True)
    assert snapshot(path) == before


def test_partial_failure_rolls_back_all_updates_and_keeps_backup(corpus_db):
    path, desired = corpus_db
    desired.append({**desired[0], "source_id": "q2", "question_text": "explode"})
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TRIGGER fail_new BEFORE INSERT ON questions WHEN NEW.question_text='explode' BEGIN SELECT RAISE(ABORT,'test failure'); END")
    before = snapshot(path)
    with pytest.raises(RuntimeError, match="已回滚"):
        sync.sync_database(path, write=True, prune=True)
    assert snapshot(path) == before
    backups = list((path.parent / "backups").glob("*.db"))
    assert len(backups) == 1 and snapshot(backups[0]) == before


def test_legacy_delete_detaches_mapping_before_sqlite_reuses_id(corpus_db):
    path, desired = corpus_db
    sync.sync_database(path, write=True, prune=True)
    with sqlite3.connect(path) as conn:
        # Simulate the old app/--replace deletion path, which knows no map table.
        conn.execute("DELETE FROM questions WHERE id=10")
        assert conn.execute("SELECT * FROM question_source_map WHERE source_id='q1'").fetchall() == []
        conn.execute("INSERT INTO questions (id,platform,question_text,reference_answer) VALUES (10,'manual','不同的手工题','不应被同步覆盖')")
    report = sync.sync_database(path, write=True)
    assert report["added"] == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT reference_answer FROM questions WHERE id=10").fetchone() == ("不应被同步覆盖",)
        assert conn.execute("SELECT question_id FROM question_source_map WHERE source_id='q1'").fetchone()[0] != 10
