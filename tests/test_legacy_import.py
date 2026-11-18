"""历史导入入口必须遵循数据库配置，并在状态合并不明确时保守拒绝。"""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.sqlite_target import sqlite_target


def load_dedup():
    spec = importlib.util.spec_from_file_location("legacy_dedup", ROOT / "crawler/scripts/dedup_sync_practice.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sqlite_target_honors_config_and_explicit_override(tmp_path, monkeypatch):
    target = tmp_path / "custom.db"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + target.as_posix())
    assert Path(sqlite_target()) == target
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    with pytest.raises(ValueError, match="仅支持 SQLite"):
        sqlite_target()
    assert Path(sqlite_target(target)) == target


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:", "sqlite:///file:test.db?uri=true"])
def test_sqlite_target_rejects_non_file_configuration(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(ValueError, match="普通 SQLite 文件"):
        sqlite_target()


def test_legacy_imports_use_configured_database_and_remain_idempotent(tmp_path):
    target = tmp_path / "configured.db"
    env = dict(os.environ, DATABASE_URL="sqlite:///" + target.as_posix(), PYTHONIOENCODING="utf-8")
    # 子进程避免 backend.db 的模块缓存令测试错用 API 测试库。
    code = """
from scripts.import_feishu_wiki import import_items
from scripts.import_mianshiya_pdf import import_pairs
items = [('Go', 'wiki question', 'first answer', 'tag'),
         ('Go', 'wiki question', 'duplicate ![img](https://example.com/a.png)', 'tag')]
assert import_items(items, update=True) == (1, 0, 1)
assert import_items(items) == (0, 2, 0)
assert import_pairs([('PDF question', 'answer'), ('PDF question', 'second answer')])[:3] == (1, 1, 1)
assert import_pairs([('PDF question', 'answer')])[:3] == (0, 1, 2)
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    db = sqlite3.connect(target)
    try:
        rows = db.execute("SELECT question_text, reference_answer, images FROM questions ORDER BY id").fetchall()
        assert len(rows) == 2
        assert rows[0][:2] == ("wiki question", "first answer")
        assert json.loads(rows[0][2]) == ["https://example.com/a.png"]
    finally:
        db.close()


def test_feishu_image_import_preserves_html_images_and_downloads_once(monkeypatch):
    from io import BytesIO
    from PIL import Image
    from scripts import import_feishu_wiki as importer

    downloaded = []
    saved = []

    picture = BytesIO()
    Image.new("RGB", (1, 1)).save(picture, "PNG")

    def download(url):
        downloaded.append(url)
        return picture.getvalue()

    class Storage:
        def save(self, data, filename, content_type):
            saved.append(filename)
            return "/data/images/" + filename

    monkeypatch.setattr(importer, "_download", download)
    monkeypatch.setattr(importer, "get_storage", lambda: Storage())
    text = importer.clean_answer('<img src="https://example.com/a.png"> ![B](https://example.com/b.png)')
    result, urls = importer._resolve_images(text)
    assert downloaded == ["https://example.com/a.png", "https://example.com/b.png"]
    assert saved == ["a.png", "b.png"]
    assert urls == ["/data/images/a.png", "/data/images/b.png"]
    assert "![图片](/data/images/a.png)" in result


def test_feishu_image_download_limits_cookie_to_trusted_https(monkeypatch):
    import httpx
    from scripts import import_feishu_wiki as importer

    seen = []

    def respond(request):
        seen.append((request.url.host, request.headers.get("Cookie")))
        if request.url.host == "docs.feishu.cn":
            return httpx.Response(302, headers={"Location": "https://assets.example/diagram"})
        return httpx.Response(200, content=b"picture")

    monkeypatch.setenv("FEISHU_IMG_COOKIE", "example=value")
    with httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=True) as client:
        def stream(method, url, headers, **kwargs):
            return client.stream(method, url, headers=headers)

        monkeypatch.setattr(importer.httpx, "stream", stream)
        assert importer._download("https://docs.feishu.cn/diagram") == b"picture"
        assert importer._download("https://assets.example/diagram") == b"picture"
        assert importer._download("file:///missing") is None
    assert seen == [("docs.feishu.cn", "example=value"), ("assets.example", None), ("assets.example", None)]


def test_feishu_image_download_keeps_unrecognized_content_out_of_storage(monkeypatch):
    from scripts import import_feishu_wiki as importer

    monkeypatch.setattr(importer, "get_storage", lambda: object())
    monkeypatch.setattr(importer, "_download", lambda url: b"example text")
    text = "![diagram](https://assets.example/diagram.png)"
    assert importer._resolve_images(text) == (text, ["https://assets.example/diagram.png"])


@pytest.fixture
def progress_db():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE questions (id INTEGER PRIMARY KEY);
        INSERT INTO questions VALUES (1), (2), (3);
        CREATE TABLE wrong_book (question_id INTEGER UNIQUE);
        CREATE TABLE review_schedule (question_id INTEGER UNIQUE);
    """)
    yield db
    db.close()


@pytest.mark.parametrize("table", ["wrong_book", "review_schedule"])
def test_dedup_refuses_colliding_progress_without_writing(progress_db, table):
    progress_db.executemany(f"INSERT INTO {table} VALUES (?)", [(1,), (3,)])
    progress_db.commit()
    before = list(progress_db.iterdump())
    with pytest.raises(ValueError, match="多条学习状态"):
        load_dedup().validate_reassignment(progress_db, {1: 2, 2: 3})
    assert list(progress_db.iterdump()) == before


def test_dedup_resolves_chain_and_rejects_cycles_or_missing_targets(progress_db):
    validate = load_dedup().validate_reassignment
    progress_db.execute("INSERT INTO wrong_book VALUES (1)")
    assert validate(progress_db, {1: 2, 2: 3}) == {1: 3, 2: 3}
    with pytest.raises(ValueError, match="循环"):
        validate(progress_db, {1: 2, 2: 1})
    with pytest.raises(ValueError, match="已发生变化"):
        validate(progress_db, {1: 99})


def test_sqlite_import_cli_rejects_other_backend_before_reading_files(tmp_path):
    env = dict(os.environ, DATABASE_URL="postgresql://localhost/test", PYTHONIOENCODING="utf-8")
    result = subprocess.run([
        sys.executable, str(ROOT / "crawler/scripts/import_to_interview_memory.py"),
        "--json", str(tmp_path / "not-present.json"),
    ], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 2
    assert "仅支持 SQLite" in result.stderr
