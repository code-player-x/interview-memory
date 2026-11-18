"""Verify the legacy MySQL TEXT migration and large quiz replay through FastAPI.

Set MYSQL_CAPACITY_TEST_URL to the SQLAlchemy URL of a disposable, empty
MySQL database with strict SQL mode and run python scripts/verify_mysql_capacity.py.
The populated database is left in place for inspection.
"""
import json
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, make_url
from sqlalchemy.exc import DataError


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify(url):
    setup = create_engine(url)
    try:
        with setup.begin() as conn:
            version, product, mode = conn.exec_driver_sql(
                "SELECT VERSION(), @@version_comment, @@SESSION.sql_mode"
            ).one()
            check("mariadb" not in (version + product).lower(), "Use MySQL for this check")
            check({"STRICT_ALL_TABLES", "STRICT_TRANS_TABLES"} & set(mode.split(",")),
                  "Enable MySQL strict SQL mode for the legacy negative control")
            check(conn.exec_driver_sql("SELECT COUNT(*) FROM information_schema.tables "
                                       "WHERE table_schema=DATABASE()").scalar_one() == 0,
                  "The selected database must be empty")
            conn.exec_driver_sql("""
                CREATE TABLE answer_requests (
                    `key` VARCHAR(64) PRIMARY KEY, fingerprint VARCHAR(64) NOT NULL,
                    token VARCHAR(32) NOT NULL, lease_until DATETIME NOT NULL, response TEXT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            conn.exec_driver_sql("INSERT INTO answer_requests VALUES "
                                 "('legacy', 'f', 't', UTC_TIMESTAMP(), 'legacy-response')")
            try:
                conn.exec_driver_sql("UPDATE answer_requests SET response=REPEAT('x',65537) "
                                     "WHERE `key`='legacy'")
            except DataError as exc:
                if exc.orig.args[0] != 1406:
                    raise
            else:
                raise RuntimeError("Legacy TEXT unexpectedly accepted 65,537 bytes")
    finally:
        setup.dispose()

    os.environ.update(DATABASE_URL=url, PYTHON_DOTENV_DISABLED="1", SCHEDULER_ENABLED="0",
                      APP_AUTH_USER="", APP_AUTH_PASSWORD="", AGENT_JUDGE_URL="", LLM_MODEL="",
                      LLM_BASE_URL="", LLM_API_KEY="", OPENAI_MODEL="", OPENAI_BASE_URL="",
                      OPENAI_API_KEY="", STORAGE_BACKEND="local", MAX_QUIZ_ITEMS="50")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import backend.app as appmod
    from backend.db import engine

    capacity_changes = []

    @event.listens_for(engine, "before_cursor_execute")
    def observe_migration(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("ALTER TABLE ANSWER_REQUESTS"):
            capacity_changes.append(statement)

    def check_migration():
        with engine.connect() as conn:
            kind = conn.exec_driver_sql(
                "SELECT DATA_TYPE FROM information_schema.columns WHERE table_schema=DATABASE() "
                "AND table_name='answer_requests' AND column_name='response'"
            ).scalar_one()
            check(kind.lower() == "longtext", f"Expected LONGTEXT, found {kind}")
            check(conn.exec_driver_sql("SELECT response FROM answer_requests WHERE `key`='legacy'")
                  .scalar_one() == "legacy-response", "Migration changed the preexisting row")

    def check_persistence(report):
        with engine.connect() as conn:
            cached, size = conn.exec_driver_sql(
                "SELECT response, OCTET_LENGTH(response) FROM answer_requests WHERE `key` <> 'legacy'"
            ).one()
            check(size > 65536 and json.loads(cached) == report, "Cached report is incomplete")
            saved = conn.exec_driver_sql("SELECT id FROM submissions ORDER BY id").scalars().all()
            expected = [row["submission_id"] for row in report["results"]]
            check(len(saved) == 50 and sorted(expected) == saved, "Unexpected submission IDs/count")
            activity = conn.exec_driver_sql("SELECT SUM(answered), SUM(correct), SUM(wrong) FROM activity").one()
            check(tuple(activity) == (50, 50, 0), f"Unexpected activity totals: {activity}")
            return size

    try:
        reference = "模型缓存" * 150
        with TestClient(appmod.app) as client:
            check_migration()
            check(len(capacity_changes) == 1, "Expected one widening of the legacy response column")
            ids = []
            for index in range(50):
                reply = client.post("/api/questions/import", json={
                    "question_text": f"MySQL capacity question {index + 1}", "reference_answer": reference,
                })
                reply.raise_for_status()
                ids.append(reply.json()["id"])
            payload = {"request_id": "mysql-capacity-replay",
                       "items": [{"question_id": qid, "user_answer": "模型缓存"} for qid in ids]}
            with patch.object(appmod, "judge", new=AsyncMock(wraps=appmod.judge)) as judge:
                first = client.post("/api/quiz/submit", json=payload)
                first.raise_for_status()
                check(judge.await_count == 50, "First submission must grade every item once")
            report = first.json()
            results = report["results"]
            check(len(first.content) > 65536 and [row["question_id"] for row in results] == ids
                  and all(row["reference_answer"] == reference and row["is_correct"] is True for row in results),
                  "HTTP report is incomplete or too small")
            size = check_persistence(report)

        engine.dispose()
        with TestClient(appmod.app) as client:
            check_migration()
            check(len(capacity_changes) == 1, "Second startup repeated the capacity migration")
            with patch.object(appmod, "judge", new=AsyncMock()) as judge:
                replay = client.post("/api/quiz/submit", json=payload)
                replay.raise_for_status()
                judge.assert_not_awaited()
            check(replay.content == first.content, "Replayed HTTP response differs")
            check(check_persistence(report) == size, "Replay changed cache size")
    finally:
        event.remove(engine, "before_cursor_execute", observe_migration)
        engine.dispose()

    print(f"MySQL {version} ({product}): TEXT rejected 65,537 bytes with error 1406; "
          f"LONGTEXT cache {size:,} bytes, HTTP report {len(first.content):,} bytes. "
          "Identical replay after restart; 50 submissions, 50 correct, 0 extra judgments.")


if __name__ == "__main__":
    target = os.environ.get("MYSQL_CAPACITY_TEST_URL")
    if not target:
        sys.exit("Set MYSQL_CAPACITY_TEST_URL to a disposable empty MySQL database.")
    parsed = make_url(target)
    if (parsed.get_backend_name() != "mysql" or not parsed.database or
            parsed.database.lower() in {"mysql", "sys", "performance_schema", "information_schema"}):
        sys.exit("Select a disposable empty MySQL database.")
    verify(target)
