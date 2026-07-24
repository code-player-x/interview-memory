"""ArticleRewriteMiddleware 回归测试：覆盖 lianglianglee .md 实为 HTML 的嗅探重写。

运行：pytest tests/test_article_rewrite.py -q

前置：tests/conftest.py 已准备好临时 book dir 并设置 ARTICLES_BOOK_DIR 环境变量。
"""
import os

import pytest
from fastapi.testclient import TestClient

# conftest.py 已设置 ARTICLES_BOOK_DIR/DATABASE_URL
import backend.app as appmod  # noqa: E402
from backend.db import engine, Base  # noqa: E402


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(appmod.app) as c:
        yield c
    try:
        appmod.scheduler.shutdown(wait=False)
    except Exception:
        pass
    engine.dispose()


def test_md_as_html_is_rendered_and_paths_rewritten(client):
    """lianglianglee 的 .md 实际是 HTML：必须强制 text/html 并重写绝对路径。"""
    url = "/articles/MySQL/04%20%E7%B4%A2%E5%BC%95.md"
    r = client.get(url)
    assert r.status_code == 200, r.text[:200]
    ctype = r.headers.get("content-type", "").lower()
    assert "text/html" in ctype, f"应被强制为 text/html，实际: {ctype}"
    body = r.text
    assert "/articles/static/index.css" in body, "CSS 绝对路径未重写"
    assert 'href="/articles/"' in body, "根路径未重写为 /articles/"
    assert "/articles/%E4%B8%93%E6%A0%8F" in body or "/articles/专栏" in body, "专栏路径未重写"
    assert "<html" in body or "<!DOCTYPE" in body


def test_real_markdown_passthrough(client):
    """真·纯文本 .md 不是 HTML：不应该被强行改写 MIME / 路径，避免误伤。"""
    r = client.get("/articles/README.md")
    assert r.status_code == 200
    assert "# 这是普通 markdown" in r.text
    ctype = r.headers.get("content-type", "").lower()
    assert "text/html" not in ctype


def test_root_redirects_to_articles(client):
    """/articles 应重定向到 /articles/，避免 iframe(src=/articles) 404。"""
    r = client.get("/articles", follow_redirects=False)
    assert r.status_code in (307, 308)
    assert r.headers.get("location", "").endswith("/articles/")


def test_html_passthrough_still_rewritten(client):
    """真正的 .html 文件：原始 content-type 是 text/html，路径重写仍生效。"""
    fake_book = os.environ["ARTICLES_BOOK_DIR"]
    with open(os.path.join(fake_book, "page.html"), "w", encoding="utf-8") as f:
        f.write('<html><body><img src="/static/x.png"></body></html>')
    try:
        r = client.get("/articles/page.html")
        assert r.status_code == 200
        assert "/articles/static/x.png" in r.text
    finally:
        try:
            os.remove(os.path.join(fake_book, "page.html"))
        except OSError:
            pass


def test_rewritten_response_disables_caching(client):
    """改写后的响应必须带 no-store，避免浏览器缓存 iframe 拿到旧版源码。"""
    fake_book = os.environ["ARTICLES_BOOK_DIR"]
    md_path = os.path.join(fake_book, "Go", "x.md")
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html><html><body>ok</body></html>")
    try:
        r = client.get("/articles/Go/x.md")
        assert r.status_code == 200
        cc = r.headers.get("cache-control", "")
        assert "no-store" in cc
        assert r.headers.get("pragma", "").lower() == "no-cache"
        # content-type 头不能带错（MIME 重写后必须用 media_type）
        assert "text/html" in r.headers.get("content-type", "").lower()
    finally:
        try:
            os.remove(md_path)
        except OSError:
            pass


def _get_injected_style(body: str) -> str:
    import re
    m = re.search(r"<style data-interview-memory='fullwidth'>(.*?)</style>", body)
    return m.group(1) if m else ""


def test_fullwidth_css_injected_for_iframe(client):
    """iframe 嵌入适配：必须注入全宽 CSS，用 margin-left 避让 fixed 侧栏，绝不隐藏侧栏。"""
    fake_book = os.environ["ARTICLES_BOOK_DIR"]
    md_path = os.path.join(fake_book, "Go", "wide.md")
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html><html><head><title>x</title></head>"
                "<body><div class='book-content'>正文</div>"
                "<div class='book-sidebar'>菜单</div></body></html>")
    try:
        r = client.get("/articles/Go/wide.md")
        assert r.status_code == 200
        body = r.text
        # 1. 全宽 CSS 必须注入
        assert "data-interview-memory='fullwidth'" in body
        css = _get_injected_style(body)
        assert css, "injected <style> not found"
        # 2. 用 margin-left:12rem 精确避让侧栏（而非 padding 内缩覆盖侧栏）
        assert "margin-left:12rem!important" in css
        assert "max-width:none!important" in css
        # 3. 绝不能隐藏侧栏 / 用 padding 内缩把内容压到侧栏上
        assert "padding-left:13rem" not in css, "旧的内缩 hack 不应再出现"
        assert ".book-sidebar" not in css or (
            "display:none" not in css and "translateX(-100%)" not in css
            and "opacity:0" not in css
        ), "注入的 CSS 不能隐藏左侧菜单"
        # 4. 侧栏 DOM 必须原样保留
        assert "book-sidebar" in body and "菜单" in body
        # 5. body 内文要保留
        assert "正文" in body
    finally:
        try:
            os.remove(md_path)
        except OSError:
            pass


def test_fullwidth_css_injected_before_real_head_end(client):
    """lianglianglee 真实 HTML 有嵌套 <head><head> 结构：注入必须落在真正的 </head>（body 前）。"""
    fake_book = os.environ["ARTICLES_BOOK_DIR"]
    md_path = os.path.join(fake_book, "Go", "nested.md")
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        # 嵌套 head（外层 + 内层），body 在最后一个 </head> 之后
        f.write("<!DOCTYPE html><html><head>\n<head>\n<title>x</title>\n"
                "</head>\n<body><div class='book-content'>正文</div></body></html>")
    try:
        r = client.get("/articles/Go/nested.md")
        assert r.status_code == 200
        body = r.text
        css_pos = body.find("data-interview-memory='fullwidth'")
        body_pos = body.find("<body")
        assert 0 <= css_pos < body_pos, "CSS 必须插在 <body> 之前（真正的 head 闭合处）"
        # 内层的 <head> 开标签位置应早于 CSS，说明插在嵌套结构里也对
        assert body.find("<head") < css_pos
    finally:
        try:
            os.remove(md_path)
        except OSError:
            pass


def test_fullwidth_css_injected_when_no_head_tag(client):
    """兜底：HTML 没 </head> 时也要注入（防止崩溃），且同样不藏侧栏。"""
    fake_book = os.environ["ARTICLES_BOOK_DIR"]
    md_path = os.path.join(fake_book, "Go", "nohead.md")
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        # 不写 <head>，看是否会出错
        f.write("<!DOCTYPE html><html><body>hi</body></html>")
    try:
        r = client.get("/articles/Go/nohead.md")
        assert r.status_code == 200
        assert "data-interview-memory='fullwidth'" in r.text
    finally:
        try:
            os.remove(md_path)
        except OSError:
            pass