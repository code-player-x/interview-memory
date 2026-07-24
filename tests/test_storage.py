#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""图片存储抽象层 + 导入脚本图片处理的单元测试。

不依赖 FastAPI / boto3（仅验证本地模式与解析逻辑），保证：
- 本地存储后端能落盘并返回正确 URL；
- get_storage 工厂按环境变量切换；
- 导入脚本不再丢弃图片 markdown（修复此前删 <img> / 清 URL 的 bug）；
- extract_images 对绝对 https URL（S3 模式）兼容。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from storage import LocalStorageBackend, get_storage  # noqa: E402
import import_feishu_wiki as imp  # noqa: E402


def test_local_save_returns_url_and_persists(tmp_path, monkeypatch):
    monkeypatch.setattr("storage.LOCAL_DIR", str(tmp_path))
    backend = LocalStorageBackend()
    data = b"\x89PNG fake image bytes"
    url = backend.save(data, "pic.png")
    assert url.startswith("/data/images/")
    name = url.rsplit("/", 1)[-1]
    assert (tmp_path / name).read_bytes() == data
    # url_for 与 save 返回的片段一致
    assert backend.url_for(name) == url


def test_get_storage_default_local(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.setattr("storage._backend", None)
    b = get_storage()
    assert isinstance(b, LocalStorageBackend)


def test_extract_img_urls_abs_https():
    text = "架构图 ![架构](https://bucket.oss-cn.com/a.png) 与本地 ![b](/data/images/x.jpg)"
    urls = imp._extract_img_urls(text)
    assert "https://bucket.oss-cn.com/a.png" in urls
    assert "/data/images/x.jpg" in urls


def test_clean_answer_keeps_image_markdown(monkeypatch):
    # 不开 download-images：图片 markdown 应保留且 URL 不被清空（修复删图 bug）
    line = "示例图 ![示例](https://x.com/y.png) 结束"
    out = imp.clean_answer(line)
    assert "![示例]" in out
    assert "https://x.com/y.png" in out


def test_clean_answer_strips_plain_link_url():
    # 普通链接（非图片）的 URL 仍应被清空，且不影响图片
    text = "见 [官网](https://example.com) 与图 ![图](https://img.com/p.png)"
    out = imp.clean_answer(text)
    assert "官网" in out
    assert "https://example.com" not in out
    assert "https://img.com/p.png" in out  # 图片 URL 保留
