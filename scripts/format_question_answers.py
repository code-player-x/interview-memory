#!/usr/bin/env python3
"""Reformat existing local SQLite answers without reimporting the question bank.

Usage: python scripts/format_question_answers.py --database data/interview_memory.db
Add --write after inspecting the dry run. A SQLite backup is made before updates.
Only reference_answer on platform=questions_v2 changes; IDs and learning data stay.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "crawler" / "questions_v2"))
from answer_structure import AGENT_ANSWER, AGENT_TITLE, structure_answer  # noqa: E402


def format_database(path: Path, *, write: bool = False) -> dict:
    path = path.resolve(strict=True)
    with sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=30) as conn:
        updates = []
        rows = conn.execute(
            "SELECT id, question_text, reference_answer FROM questions WHERE platform = ?",
            ("questions_v2",),
        ).fetchall()
        for qid, title, old in rows:
            if not old:
                continue
            new = structure_answer(AGENT_ANSWER if title == AGENT_TITLE else old)
            if new != old:
                updates.append((new, qid, old))
        report = {"scanned": len(rows), "changed": len(updates), "written": False, "backup": None}
        if not write or not updates:
            return report
        backup_dir = path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        descriptor, backup = tempfile.mkstemp(prefix="before-answer-layout-", suffix=".db", dir=backup_dir)
        os.close(descriptor)
        with sqlite3.connect(backup) as destination:
            conn.backup(destination)
        report["backup"] = backup
        # Optimistic guard also protects an answer edited after the initial read.
        with conn:
            for new, qid, old in updates:
                result = conn.execute(
                    "UPDATE questions SET reference_answer = ? WHERE id = ? AND reference_answer = ?",
                    (new, qid, old),
                )
                if result.rowcount != 1:
                    raise RuntimeError(f"Question {qid} changed concurrently; all updates rolled back. Backup: {backup}")
        report["written"] = True
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--write", action="store_true", help="Apply changes after creating a backup")
    args = parser.parse_args()
    print(format_database(args.database, write=args.write))


if __name__ == "__main__":
    main()
