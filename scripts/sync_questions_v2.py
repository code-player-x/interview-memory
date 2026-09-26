#!/usr/bin/env python3
"""Backed-up, in-place synchronization of the reviewed corpus to local SQLite.

Default is a read-only plan. --write updates existing IDs and adds missing rows.
--prune also removes obsolete questions_v2 rows, but refuses if they have any
question_id references. Never changes learning records or other platforms.
The source-ID side table is ignored by older app versions, so no app schema
upgrade is needed. A complete SQLite backup is produced before every change.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import sqlite3
import tempfile

try:
    from .import_questions_v2 import DEFAULT_SOURCE, load_questions
except ImportError:
    from import_questions_v2 import DEFAULT_SOURCE, load_questions

MAP_TABLE = "question_source_map"
DELETE_TRIGGER = "question_source_map_on_question_delete"
FIELDS = ("platform", "category", "tags", "difficulty", "question_text", "reference_answer", "keywords")


def historical_titles(source: Path) -> dict[str, set[str]]:
    aliases = defaultdict(set)
    for archive in sorted((source.parent / "review_archive").glob("*.jsonl")):
        for line in archive.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)["item"]
            aliases[item["id"]].add(item["title"].strip())
    return aliases


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sync_database(path: Path, source: Path = DEFAULT_SOURCE, *, write: bool = False, prune: bool = False) -> dict:
    questions = {item["source_id"]: item for item in load_questions(source, with_source_id=True)}
    aliases = historical_titles(source)
    path = path.resolve(strict=True)
    uri = path.as_uri()
    conn = sqlite3.connect(uri + ("?mode=rw" if write else "?mode=ro"), uri=True, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    backup = None
    try:
        # Prevent an answer/note edit between planning, reference checks and write.
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        schema_updates = int(MAP_TABLE not in tables) + int(DELETE_TRIGGER not in triggers)
        rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM questions WHERE platform='questions_v2'")}
        mappings = dict(conn.execute(f"SELECT source_id, question_id FROM {MAP_TABLE}")) if MAP_TABLE in tables else {}
        owners = {qid: sid for sid, qid in mappings.items()}
        assignments = {}
        used = set()
        for sid in questions:
            if sid in mappings and mappings[sid] in rows:
                assignments[sid] = mappings[sid]
                used.add(mappings[sid])
            elif sid in mappings and conn.execute("SELECT 1 FROM questions WHERE id=?", (mappings[sid],)).fetchone():
                raise ValueError(f"源 ID {sid} 对应题目的平台已改变，拒绝覆盖")

        # Exact current titles take precedence over historical aliases globally.
        for historical in (False, True):
            proposals = {}
            for sid, item in questions.items():
                if sid in assignments:
                    continue
                titles = aliases.get(sid, set()) if historical else {item["question_text"]}
                candidates = [qid for qid, row in rows.items() if qid not in used
                              and (qid not in owners or owners[qid] == sid)
                              and row["question_text"] in titles]
                if len(candidates) > 1:
                    raise ValueError(f"源 ID {sid} 匹配多个数据库题目 {candidates}，需人工确认")
                if candidates:
                    qid = candidates[0]
                    if qid in proposals:
                        raise ValueError(f"数据库题目 {qid} 匹配多个源 ID，需人工确认")
                    proposals[qid] = sid
            for qid, sid in proposals.items():
                assignments[sid] = qid
                used.add(qid)

        obsolete = sorted(set(rows) - used)
        referenced = defaultdict(set)
        for table in tables - {"questions", MAP_TABLE}:
            columns = {r[1] for r in conn.execute(f"PRAGMA table_info({_quote(table)})")}
            if "question_id" in columns:
                for (qid,) in conn.execute(f"SELECT DISTINCT question_id FROM {_quote(table)}"):
                    if qid in obsolete:
                        referenced[qid].add(table)
        updates = [sid for sid, qid in assignments.items()
                   if any(rows[qid].get(field) != questions[sid][field] for field in FIELDS)]
        additions = sorted(set(questions) - set(assignments))
        map_changes = sum(mappings.get(sid) != qid for sid, qid in assignments.items())
        report = {
            "source_count": len(questions), "matched": len(assignments),
            "updated": len(updates), "added": len(additions),
            "obsolete_ids": obsolete, "pruned": len(obsolete) if prune else 0,
            "blocked_references": {str(qid): sorted(names) for qid, names in referenced.items()},
            "mapping_updates": map_changes, "written": False, "backup": None,
            "schema_updates": schema_updates,
        }
        if not write:
            return report
        if prune and referenced:
            raise ValueError(f"拒绝删除有关联学习记录的旧题：{report['blocked_references']}")
        if not (updates or additions or map_changes or schema_updates or (prune and obsolete)):
            return report

        backup_dir = path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        fd, backup = tempfile.mkstemp(prefix="before-corpus-sync-", suffix=".db", dir=backup_dir)
        os.close(fd)
        # A separate read connection snapshots the pre-write DB while this
        # connection holds the reserved write lock; backing up it would block.
        with sqlite3.connect(uri + "?mode=ro", uri=True) as reader, sqlite3.connect(backup) as destination:
            reader.backup(destination)
        conn.execute(f"CREATE TABLE IF NOT EXISTS {MAP_TABLE} (source_id TEXT PRIMARY KEY, question_id INTEGER NOT NULL UNIQUE)")
        # Legacy app deletes and --replace must also detach source identity.
        # Otherwise SQLite could reuse a row ID and map it to the wrong source.
        conn.execute(f"CREATE TRIGGER IF NOT EXISTS {DELETE_TRIGGER} AFTER DELETE ON questions "
                     f"BEGIN DELETE FROM {MAP_TABLE} WHERE question_id=OLD.id; END")
        setters = ", ".join(f"{field}=?" for field in FIELDS)
        for sid in updates:
            conn.execute(f"UPDATE questions SET {setters} WHERE id=?",
                         tuple(questions[sid][field] for field in FIELDS) + (assignments[sid],))
        # Insert before prune to avoid reusing the IDs of retired questions.
        for sid in additions:
            result = conn.execute(
                f"INSERT INTO questions ({', '.join(FIELDS)}, created_at) VALUES ({', '.join('?' for _ in FIELDS)}, CURRENT_TIMESTAMP)",
                tuple(questions[sid][field] for field in FIELDS),
            )
            assignments[sid] = result.lastrowid
        if prune:
            for qid in obsolete:
                conn.execute(f"DELETE FROM {MAP_TABLE} WHERE question_id=?", (qid,))
                conn.execute("DELETE FROM questions WHERE id=? AND platform='questions_v2'", (qid,))
        # Discard dangling mappings left by normal question deletion.
        conn.execute(f"DELETE FROM {MAP_TABLE} WHERE question_id NOT IN (SELECT id FROM questions)")
        for sid, qid in assignments.items():
            conn.execute(f"INSERT INTO {MAP_TABLE} (source_id,question_id) VALUES (?,?) ON CONFLICT(source_id) DO UPDATE SET question_id=excluded.question_id", (sid, qid))
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("同步后的 SQLite 完整性检查失败")
        conn.commit()
        report.update(written=True, backup=backup)
        return report
    except Exception as exc:
        conn.rollback()
        if backup:
            raise RuntimeError(f"同步失败，已回滚；原库备份：{backup}") from exc
        raise
    finally:
        if conn.in_transaction:
            conn.rollback()
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--write", action="store_true", help="备份后原位更新；默认只预览")
    parser.add_argument("--prune", action="store_true", help="清理不再属于源题库且无学习记录的旧题")
    args = parser.parse_args()
    print(json.dumps(sync_database(args.database, args.source, write=args.write, prune=args.prune), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
