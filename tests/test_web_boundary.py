from io import BytesIO
import json
import os
import subprocess
import sys

from fastapi.testclient import TestClient
from PIL import Image

from backend import app as api, storage
from backend.web_boundary import WebBoundary


def test_actual_upload_validates_bytes_and_serves_safe_type(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "LOCAL_DIR", str(tmp_path))
    monkeypatch.setattr(storage, "_backend", None)
    png = BytesIO()
    Image.new("RGB", (2, 2)).save(png, format="PNG")
    with TestClient(api.app) as client:
        def upload(name, content):
            return client.post("/api/images/upload", files={"file": (name, content, "text/plain")})
        assert upload("bad.jpg", png.getvalue()).status_code == 415
        assert upload("bad.svg", b"<svg/>").status_code == 415
        assert upload("large.png", bytes(8 * 1024 * 1024 + 1)).status_code == 413
        result = upload("ok.png", png.getvalue())
        assert result.status_code == 200
        assert (tmp_path / result.json()["filename"]).read_bytes() == png.getvalue()


def test_web_import_uses_configured_root(tmp_path, monkeypatch):
    root = tmp_path / "imports"
    root.mkdir()
    monkeypatch.setattr(api, "IMPORT_DIR", root)
    with TestClient(api.app) as client:
        def load(name):
            return client.post("/api/questions/import-batch", json={"path": name})
        assert load(str(tmp_path / "outside.json")).status_code == 400
        (root / "bank.json").write_text('{"questions":[]}')
        assert load("bank.json").status_code == 200
        assert load("missing.json").status_code == 404
        name = "batch-atomicity-and-duplicate-test"
        rows = [{"question": name}, {"question": name + " "}, {"question": name + "-bad", "key_points": 3}]
        bank = root / "bank.json"
        bank.write_text(json.dumps({"questions": rows}))
        assert load("bank.json").status_code == 422
        assert client.get("/api/questions", params={"keyword": name}).json()["total"] == 0
        bank.write_text(json.dumps({"questions": rows[:2]}))
        assert load("bank.json").json() == {"imported": 1, "skipped": 1, "total": 2, "path": "bank.json"}
        assert load("bank.json").json()["imported"] == 0


def test_auth_protects_ui_and_api_and_checks_write_origin(monkeypatch):
    with monkeypatch.context() as config:
        config.setenv("APP_AUTH_USER", "test")
        config.setenv("APP_AUTH_PASSWORD", "test-password")
        app = WebBoundary(api.app, origins=[])
    with TestClient(app) as client:
        for path in ["/", "/admin/", "/api/questions"]:
            assert client.get(path).status_code == 401
        client.auth = ("test", "test-password")
        assert client.get("/api/admin/jobs").status_code == 200
        assert client.post("/api/questions/import", headers={"Origin": "https://other.example"},
                           json={"question_text": "cross origin"}).status_code == 403


def test_import_and_lifespan_have_distinct_side_effects(tmp_path):
    database = tmp_path / "lifespan.db"
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + str(database), "SCHEDULER_ENABLED": "1"}
    code = """
import pathlib, sys
from backend.app import app
from fastapi.testclient import TestClient
database = pathlib.Path(sys.argv[1])
assert not database.exists()
with TestClient(app) as client:
    assert database.is_file()
    status = client.get('/api/admin/jobs').json()
    assert status['scheduler'] == 'running'
    assert set(status['next_runs']) == {'daily_review', 'pending_judgments'}
    worker = app.state.scheduler
assert not worker.running and app.state.scheduler is None
"""
    subprocess.run([sys.executable, "-c", code, str(database)], env=env, check=True, timeout=45)
