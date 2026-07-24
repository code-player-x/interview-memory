#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""图片存储抽象层。

设计目标：把「保存图片字节 -> 得到可访问 URL」这一步从具体存储后端解耦，
让题库图片既能在本地零运维跑（默认），也能一键切到对象存储（S3 兼容：
AWS S3 / 阿里云 OSS / 腾讯云 COS / MinIO / Cloudflare R2）。

切换方式：环境变量 STORAGE_BACKEND=local(默认) | s3

- 本地模式：存 data/images/<uuid><ext>，返回相对 URL /data/images/<file>
  （由 backend/app.py 的 StaticFiles 挂载提供同源访问）。
- S3 模式：用 boto3 上传到桶，返回绝对 URL（自定义域名优先，否则 endpoint 直链）。
  前端 renderMarkdown 的 _safeUrl 已放行 https:，故绝对 URL 可直接 <img src> 渲染。
"""
import os
import uuid
import mimetypes
from abc import ABC, abstractmethod

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DIR = os.path.join(BASE_DIR, "data", "images")


def _safe_ext(filename: str, fallback: str = ".bin") -> str:
    _, ext = os.path.splitext(filename or "")
    return ext.lower() if ext else fallback


def _gen_name(filename: str) -> str:
    return uuid.uuid4().hex + _safe_ext(filename)


class StorageBackend(ABC):
    """图片存储后端统一契约。"""

    @abstractmethod
    def save(self, data: bytes, filename: str, content_type: str = None) -> str:
        """保存图片字节，返回可访问 URL（前端直接用于 <img src>）。"""

    @abstractmethod
    def url_for(self, filename: str) -> str:
        """给定已保存的文件名，返回可访问 URL（用于展示已有图片）。"""


class LocalStorageBackend(StorageBackend):
    def __init__(self):
        os.makedirs(LOCAL_DIR, exist_ok=True)

    def save(self, data: bytes, filename: str, content_type: str = None) -> str:
        name = _gen_name(filename)
        dest = os.path.join(LOCAL_DIR, name)
        with open(dest, "wb") as f:
            f.write(data)
        return self.url_for(name)

    def url_for(self, filename: str) -> str:
        return "/data/images/" + filename


class S3StorageBackend(StorageBackend):
    def __init__(self):
        import boto3  # 仅在 S3 模式下需要，避免本地模式强依赖

        self.bucket = os.environ["S3_BUCKET"]
        self.endpoint = os.environ.get("S3_ENDPOINT")  # 兼容 OSS/COS/MinIO/R2
        self.region = os.environ.get("S3_REGION", "auto")
        self.public_base = os.environ.get("S3_PUBLIC_URL")  # 可选：自定义域名/CDN
        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint or None,
            region_name=self.region,
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
        )

    def save(self, data: bytes, filename: str, content_type: str = None) -> str:
        name = _gen_name(filename)
        extra = {}
        if content_type:
            extra["ContentType"] = content_type
        elif _safe_ext(filename) in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"):
            guessed = mimetypes.guess_type(name)[0]
            if guessed:
                extra["ContentType"] = guessed
        self.client.put_object(Bucket=self.bucket, Key=name, Body=data, **extra)
        return self.url_for(name)

    def url_for(self, filename: str) -> str:
        if self.public_base:
            return self.public_base.rstrip("/") + "/" + filename
        if self.endpoint:
            # MinIO / R2 风格：endpoint/bucket/key
            return f"{self.endpoint.rstrip('/')}/{self.bucket}/{filename}"
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{filename}"


_backend = None


def get_storage() -> StorageBackend:
    """返回全局存储后端单例，按 STORAGE_BACKEND 环境变量切换。"""
    global _backend
    if _backend is not None:
        return _backend
    kind = os.environ.get("STORAGE_BACKEND", "local").lower()
    if kind == "s3":
        _backend = S3StorageBackend()
    else:
        _backend = LocalStorageBackend()
    return _backend
