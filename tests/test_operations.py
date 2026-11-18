"""离线运维测试：全部使用临时数据库和配图，不访问线上数据或远端模型。"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

from scripts import sqlite_target as targets
from scripts.backup_data import create_snapshot, restore_snapshot, verify_snapshot

ROOT = Path(__file__).resolve().parents[1]


def test_target_priority_env_file_and_explicit_path(tmp_path, monkeypatch):
    monkeypatch.setattr(targets, "ROOT", tmp_path)
    (tmp_path / ".env").write_text("DATABASE_URL=sqlite:///from-file.db\n", encoding="utf-8")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert Path(targets.sqlite_target()).name == "from-file.db"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///from-env.db")
    assert Path(targets.sqlite_target()).name == "from-env.db"
    assert Path(targets.sqlite_target(tmp_path / "explicit.db")).name == "explicit.db"
    (tmp_path / ".env").write_text("DATABASE_URL=postgresql://localhost/not-connected\n", encoding="utf-8")
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValueError, match="仅支持 SQLite"):
        targets.sqlite_target()


def test_snapshot_restores_wal_and_images_and_rejects_tampering(tmp_path):
    source = tmp_path / "source.db"
    images = tmp_path / "images"
    images.mkdir()
    (images / "diagram.png").write_bytes(b"original-image")
    db = sqlite3.connect(source)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
        db.execute("CREATE TABLE questions (id INTEGER PRIMARY KEY, images TEXT)")
        db.execute("INSERT INTO questions VALUES (1, '/data/images/diagram.png')")
        db.commit()
        snapshot = tmp_path / "snapshot"
        create_snapshot(source, images, snapshot)
        verify_snapshot(snapshot)
        restored = tmp_path / "restored"
        restore_snapshot(snapshot, restored)
        assert (restored / "images/diagram.png").read_bytes() == b"original-image"
        restored_db = sqlite3.connect(restored / "interview_memory.db")
        try:
            assert restored_db.execute("SELECT images FROM questions").fetchone()[0] == "/data/images/diagram.png"
        finally:
            restored_db.close()
        with pytest.raises(FileExistsError):
            restore_snapshot(snapshot, restored)
        (snapshot / "images/diagram.png").write_bytes(b"changed")
        with pytest.raises(ValueError, match="校验失败"):
            restore_snapshot(snapshot, tmp_path / "bad-restore")
        assert not (tmp_path / "bad-restore").exists()
    finally:
        db.close()


def test_snapshot_checks_top_level_image_link_before_resolving(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "images").mkdir()
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == Path("images") or original(path))
    with pytest.raises(ValueError, match="图片目录不能是链接"):
        create_snapshot(tmp_path / "source.db", Path("images"), tmp_path / "snapshot")
    assert not (tmp_path / "snapshot").exists()


def test_snapshot_requires_image_directory_and_cleans_failed_output(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE sample(id INTEGER)")
    db.close()
    images = tmp_path / "images"
    output = tmp_path / "backup"
    with pytest.raises(NotADirectoryError):
        create_snapshot(source, images, output)
    images.mkdir()
    create_snapshot(source, images, output)
    (output / "images").rmdir()
    with pytest.raises(ValueError, match="图片目录"):
        restore_snapshot(output, tmp_path / "restore")
    assert not (tmp_path / "restore").exists()
    (images / "picture").write_bytes(b"temp")

    def fail_copy(*args):
        raise OSError("copy failed")

    monkeypatch.setattr(shutil, "copy2", fail_copy)
    with pytest.raises(OSError, match="copy failed"):
        create_snapshot(source, images, tmp_path / "failed-backup")
    assert not (tmp_path / "failed-backup").exists()


@pytest.mark.parametrize("filename", [
    "add_rubric_bplustree.py", "sync_bplustree_practice.py", "repair_answer_downgrade.py",
])
def test_historical_maintenance_rejects_external_database_before_io(tmp_path, filename):
    command = [sys.executable, str(ROOT / "crawler/scripts" / filename), "--apply"]
    if filename.startswith("repair"):
        command += ["--backup", str(tmp_path / "missing.db")]
    env = dict(os.environ, DATABASE_URL="postgresql://localhost/not-used", PYTHONIOENCODING="utf-8")
    result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, encoding="utf-8", timeout=30)
    assert result.returncode == 2
    assert "仅支持 SQLite" in result.stderr


def test_historical_merge_checks_question_identity_before_changing_files(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("merge_test", ROOT / "crawler/scripts/sync_bplustree_practice.py")
    merge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(merge)
    bank = tmp_path / "bank.json"
    bank.write_text(json.dumps({"items": [{"id": "q0490", "content": "merged", "sub_questions": "part2"}]}))
    original = bank.read_bytes()
    database = tmp_path / "custom.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE questions (id INTEGER PRIMARY KEY, question_text TEXT, reference_answer TEXT)")
        db.execute("INSERT INTO questions VALUES (609, 'unrelated question', '')")
    db.close()
    monkeypatch.setattr(merge, "BANK", bank)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + database.as_posix())
    monkeypatch.setattr(sys, "argv", ["sync", "--apply"])
    with pytest.raises(SystemExit):
        merge.main()
    assert bank.read_bytes() == original
    assert not list(tmp_path.glob("*.bak_*"))
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT question_text FROM questions").fetchone()[0] == "unrelated question"
    db.close()


def test_crawler_import_previews_blank_and_duplicate_rows_as_skipped(tmp_path):
    target = tmp_path / "selected.db"
    with sqlite3.connect(target) as db:
        db.execute("CREATE TABLE questions(question_text TEXT)")
        db.execute("INSERT INTO questions VALUES ('existing')")
    db.close()
    source = tmp_path / "questions.json"
    source.write_text(json.dumps({"questions": [{"question": q} for q in ("existing", "new", "new", "", None)]}))
    env = dict(os.environ, DATABASE_URL="sqlite:///" + target.as_posix(), PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "crawler/scripts/import_to_interview_memory.py"),
                             "--dry-run", "--json", str(source)], cwd=tmp_path, env=env, capture_output=True,
                            encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "将新增: 1, 将跳过(已存在): 4" in result.stdout
    assert not list(tmp_path.glob("*.bak_*"))


def test_curated_replacement_rejects_empty_input_and_preserves_other_sources(tmp_path):
    source = tmp_path / "questions"
    source.mkdir()
    batch = source / "go.jsonl"
    target = tmp_path / "selected.db"
    command = [sys.executable, str(ROOT / "scripts/import_questions_v2.py"), "--source", str(source), "--replace"]
    env = dict(os.environ, DATABASE_URL="sqlite:///" + target.as_posix(), PYTHONIOENCODING="utf-8")

    def run():
        return subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, encoding="utf-8", timeout=30)

    batch.write_text(json.dumps({"title": "old", "answer": "old answer"}), encoding="utf-8")
    assert run().returncode == 0
    batch.write_text("\n", encoding="utf-8")
    rejected = run()
    assert rejected.returncode != 0 and "源文件没有题目" in rejected.stderr
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT question_text FROM questions").fetchall() == [("old",)]
        db.execute("UPDATE questions SET platform = 'custom'")
    db.close()
    batch.write_text("\n".join(json.dumps({"title": title, "answer": "answer"}) for title in ("old", "new")), encoding="utf-8")
    assert run().returncode == 0
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT platform, question_text FROM questions ORDER BY id").fetchall() == [
            ("custom", "old"), ("questions_v2", "new"),
        ]
    db.close()


def test_sync_dry_run_forwards_same_target_without_fill_or_persistent_output(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("sync_test", ROOT / "crawler/sync.py")
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    bank = tmp_path / "bank.json"
    bank.write_text('{"items": []}', encoding="utf-8")
    target = tmp_path / "selected.db"
    target.touch()
    monkeypatch.setattr(sync, "BANK", bank)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + target.as_posix())
    monkeypatch.setattr(sys, "argv", ["sync", "--dry-run", "--with-fill"])
    calls = []
    monkeypatch.setattr(sync, "run", lambda *args: calls.append(args))
    sync.main()
    assert [call[0].name for call in calls] == ["convert_to_interview_memory.py", "import_to_interview_memory.py"]
    assert calls[0][calls[0].index("--target-db") + 1] == str(target)
    assert calls[1][calls[1].index("--db") + 1] == str(target)
    assert "--dry-run" in calls[1]
    assert not Path(calls[0][calls[0].index("--out") + 1]).parent.exists()


def test_converter_reads_selected_db_and_refuses_missing_baseline(tmp_path):
    source = tmp_path / "selected.db"
    db = sqlite3.connect(source)
    db.execute("CREATE TABLE questions (question_text TEXT)")
    db.execute("INSERT INTO questions VALUES ('explain hash maps')")
    db.commit()
    db.close()
    bank = tmp_path / "bank.json"
    bank.write_text(json.dumps({"items": [
        {"content": "explain hash maps", "answer": {}},
        {"content": "goroutine scheduling model", "answer": {}},
    ]}), encoding="utf-8")
    output = tmp_path / "converted.json"
    command = [sys.executable, str(ROOT / "crawler/scripts/convert_to_interview_memory.py"),
               "--bank", str(bank), "--out", str(output)]
    env = dict(os.environ, DATABASE_URL="sqlite:///" + source.as_posix(), PYTHONIOENCODING="utf-8")
    result = subprocess.run(command, env=env, cwd=ROOT, capture_output=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [item["question"] for item in json.loads(output.read_text(encoding="utf-8"))["questions"]] == ["goroutine scheduling model"]
    bad_output = tmp_path / "bad.json"
    result = subprocess.run(command[:-1] + [str(bad_output), "--target-db", str(tmp_path / "missing.db")], env=env, cwd=ROOT, capture_output=True, encoding="utf-8", timeout=30)
    assert result.returncode != 0
    assert not bad_output.exists()


def test_sync_imports_its_own_conversion_when_another_run_publishes(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("sync_race_test", ROOT / "crawler/sync.py")
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    database = tmp_path / "practice.db"
    bank = tmp_path / "bank.json"
    bank.write_text('{"items":[]}')
    database.touch()
    shared = tmp_path / "output" / "questions.json"
    monkeypatch.setattr(sync, "BANK", bank)
    monkeypatch.setattr(sync, "OUT", shared)
    monkeypatch.setattr(sys, "argv", ["sync", "--db", str(database)])

    def run(script, *args):
        if script.name.startswith("convert"):
            Path(args[args.index("--out") + 1]).write_text("selected")
            shared.write_text("other")
        else:
            assert Path(args[args.index("--json") + 1]).read_text() == "selected"

    monkeypatch.setattr(sync, "run", run)
    sync.main()
    assert shared.read_text() == "selected"


@pytest.mark.parametrize("filename", ["extract_keywords.py", "extract_keywords_heuristic.py"])
def test_keyword_dry_run_does_not_migrate_legacy_db(tmp_path, filename):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in (filename, "sqlite_target.py"):
        shutil.copy2(ROOT / "scripts" / name, scripts / name)
    source = tmp_path / "legacy.db"
    db = sqlite3.connect(source)
    db.execute("CREATE TABLE questions (id INTEGER PRIMARY KEY, question_text TEXT, reference_answer TEXT)")
    db.commit()
    db.close()
    before = source.read_bytes()
    env = dict(os.environ, DATABASE_URL="sqlite:///" + source.as_posix(), PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, str(scripts / filename), "--dry-run"], env=env, cwd=tmp_path, capture_output=True, encoding="utf-8", timeout=30)
    assert result.returncode != 0
    assert "预演不会迁移" in result.stderr
    assert source.read_bytes() == before
