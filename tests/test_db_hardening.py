"""SQLite 启动兼容性与历史 schema 迁移回归测试。"""
import json
import os
import sqlite3
import subprocess
import sys


PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _init_database_in_child(db_path):
    """隔离导入 backend.db，因为它在模块加载时读取 DATABASE_URL。"""
    code = """
import json
from backend.db import engine, init_db

init_db()
with engine.connect() as connection:
    print(json.dumps({
        'journal_mode': connection.exec_driver_sql('PRAGMA journal_mode').scalar(),
        'busy_timeout': connection.exec_driver_sql('PRAGMA busy_timeout').scalar(),
    }))
engine.dispose()
"""
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite:///" + str(db_path).replace(os.sep, "/")
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_file_sqlite_url_creates_parent_and_enables_wal_and_busy_timeout(tmp_path):
    db_path = tmp_path / "nested" / "database" / "interview_memory.db"
    result = _init_database_in_child(db_path)
    assert db_path.exists()
    assert result["journal_mode"].lower() == "wal"
    assert result["busy_timeout"] == 30000


def test_memory_sqlite_keeps_memory_journal_mode_while_using_busy_timeout():
    code = """
import json
from backend.db import engine, init_db

init_db()
with engine.connect() as connection:
    print(json.dumps({
        'journal_mode': connection.exec_driver_sql('PRAGMA journal_mode').scalar(),
        'busy_timeout': connection.exec_driver_sql('PRAGMA busy_timeout').scalar(),
    }))
engine.dispose()
"""
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite:///:memory:"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    probe = json.loads(result.stdout)
    assert probe["journal_mode"].lower() == "memory"
    assert probe["busy_timeout"] == 30000


def test_legacy_sqlite_is_migrated_without_losing_duplicate_learning_counts(tmp_path):
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    try:
        # 模拟早期库：questions 尚无 keywords，且并发首错曾留下同题重复行。
        connection.executescript(
            """
            CREATE TABLE questions (
                id INTEGER PRIMARY KEY, platform VARCHAR(50), category VARCHAR(100), tags TEXT,
                difficulty INTEGER, question_text TEXT NOT NULL, reference_answer TEXT,
                created_at DATETIME, images TEXT
            );
            CREATE TABLE wrong_book (
                id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL, first_wrong_at DATETIME,
                wrong_count INTEGER, last_user_answer TEXT, error_reason TEXT,
                mastery VARCHAR(20), updated_at DATETIME
            );
            CREATE TABLE review_schedule (
                id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL, stage INTEGER,
                next_review_at DATETIME, last_reviewed_at DATETIME, review_count INTEGER,
                status VARCHAR(20)
            );
            """
        )
        connection.execute(
            "INSERT INTO wrong_book VALUES (1, 7, '2026-01-01 00:00:00', 1, '旧答案', '', 'learning', '2026-01-01 00:00:00')"
        )
        connection.execute(
            "INSERT INTO wrong_book VALUES (2, 7, '2026-01-02 00:00:00', 2, '新答案', '未覆盖', 'reviewing', '2026-01-02 00:00:00')"
        )
        connection.execute(
            "INSERT INTO review_schedule VALUES (1, 7, 2, '2026-01-03 00:00:00', NULL, 1, 'pending')"
        )
        connection.execute(
            "INSERT INTO review_schedule VALUES (2, 7, 1, '2026-01-02 00:00:00', NULL, 0, 'pending')"
        )
        connection.commit()
    finally:
        connection.close()

    _init_database_in_child(db_path)

    connection = sqlite3.connect(db_path)
    try:
        question_columns = {row[1] for row in connection.execute("PRAGMA table_info(questions)")}
        assert "keywords" in question_columns

        wrong = connection.execute(
            "SELECT question_id, wrong_count, first_wrong_at, last_user_answer, mastery FROM wrong_book"
        ).fetchall()
        assert wrong == [(7, 3, "2026-01-01 00:00:00", "新答案", "reviewing")]

        schedule = connection.execute(
            "SELECT question_id, stage, next_review_at, review_count, status FROM review_schedule"
        ).fetchall()
        assert schedule == [(7, 1, "2026-01-02 00:00:00", 1, "pending")]

        for table in ("wrong_book", "review_schedule"):
            indexes = connection.execute(f"PRAGMA index_list({table})").fetchall()
            assert any(
                index[2]
                and [column[2] for column in connection.execute(
                    f'PRAGMA index_info("{index[1]}")'
                ).fetchall()] == ["question_id"]
                for index in indexes
            )
    finally:
        connection.close()
