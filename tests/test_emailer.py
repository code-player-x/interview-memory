"""固定复习邮件的模板与无配置降级测试。"""
from backend import emailer
import pytest


def test_render_review_email_contains_question_and_reference_answer():
    body = emailer.render_review_email(
        [{
            "category": "并发",
            "question_text": "volatile 的作用？",
            "reference_answer": "保证可见性与有序性",
            "last_user_answer": "不会",
            "first_wrong_at": "2026-09-19",
            "wrong_count": 2,
        }],
        "http://localhost:8000/",
    )
    assert "volatile" in body
    assert "保证可见性与有序性" in body
    assert "http://localhost:8000/" in body


def test_send_review_email_without_smtp_configuration_is_safe(monkeypatch):
    for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_PASS"):
        monkeypatch.delenv(key, raising=False)
    assert emailer.send_review_email("reader@example.com", []) is False


@pytest.mark.parametrize("use_ssl", ["1", "0"])
def test_smtp_uses_bounded_network_timeout(monkeypatch, use_ssl):
    monkeypatch.setenv("SMTP_HOST", "smtp.invalid")
    monkeypatch.setenv("SMTP_USER", "test@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "test-only-placeholder")
    monkeypatch.setenv("SMTP_USE_SSL", use_ssl)
    opened = []

    class FakeSMTP:
        def __init__(self, host, port, *, timeout):
            opened.append((host, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, *args):
            pass

        def starttls(self):
            pass

        def sendmail(self, *args):
            pass

    monkeypatch.setattr(emailer.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(emailer.smtplib, "SMTP", FakeSMTP)
    assert emailer.send_review_email("reader@example.com", []) is True
    assert opened == [("smtp.invalid", 30)]
