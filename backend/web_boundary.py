"""HTTP protections shared by API routes, static pages and optional articles."""
import base64
import binascii
import os
import secrets
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMPORT_BYTES = 16 * 1024 * 1024
_IMAGE_FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".gif": "GIF", ".webp": "WEBP", ".bmp": "BMP"}


def validate_image(content, filename):
    expected = _IMAGE_FORMATS.get(Path(filename or "").suffix.lower())
    if not expected:
        raise HTTPException(415, "请选择 PNG、JPEG、GIF、WebP 或 BMP 图片")
    try:
        with Image.open(BytesIO(content), formats=[expected]) as image:
            if image.width * image.height > 24_000_000:
                raise HTTPException(413, "图片像素过多")
            image.verify()
        with Image.open(BytesIO(content), formats=[expected]) as image:
            image.load()
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise HTTPException(415, "图片内容无效或与扩展名不符") from exc
    return Image.MIME[expected]


class WebBoundary:
    def __init__(self, app, origins):
        self.app = app
        self.origins = set(origins)
        user = os.getenv("APP_AUTH_USER", "")
        password = os.getenv("APP_AUTH_PASSWORD", "")
        if bool(user) != bool(password):
            raise ValueError("APP_AUTH_USER 和 APP_AUTH_PASSWORD 必须同时配置")
        self.credentials = (user + ":" + password).encode() if password else None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        path = scope["path"]
        method = scope["method"]
        if self.credentials and method != "OPTIONS":
            scheme, _, value = headers.get("authorization", "").partition(" ")
            try:
                supplied = base64.b64decode(value, validate=True)
            except (ValueError, binascii.Error):
                supplied = b""
            if scheme.lower() != "basic" or not secrets.compare_digest(supplied, self.credentials):
                return await PlainTextResponse("需要登录", 401, headers={"WWW-Authenticate": 'Basic realm="Interview Memory", charset="UTF-8"'})(scope, receive, send)
        origin = headers.get("origin")
        own_origin = scope["scheme"] + "://" + headers.get("host", "")
        if method not in {"GET", "HEAD", "OPTIONS"}:
            if (origin and origin != own_origin and origin not in self.origins) or (
                not origin and headers.get("sec-fetch-site") == "cross-site"
            ):
                return await PlainTextResponse("不允许此来源的写请求", 403)(scope, receive, send)
        # Bound the multipart body before Starlette spools the upload to disk.
        if path.rstrip("/") == "/api/images/upload" and method == "POST":
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > MAX_IMAGE_BYTES + 65536:
                    return await PlainTextResponse("上传内容过大", 413)(scope, receive, send)
                body.extend(chunk)
                if not message.get("more_body"):
                    break
            original_receive = receive
            async def receive_body():
                nonlocal body
                if body is None:
                    return await original_receive()
                data, body = bytes(body), None
                return {"type": "http.request", "body": data, "more_body": False}
            receive = receive_body

        async def send_headers(message):
            if message["type"] == "http.response.start":
                response = MutableHeaders(scope=message)
                response["X-Content-Type-Options"] = "nosniff"
                if path.startswith(("/articles/", "/data/images/")):
                    response["Content-Security-Policy"] = "sandbox allow-same-origin; script-src 'none'; object-src 'none'; form-action 'none'"
            await send(message)
        await self.app(scope, receive, send_headers)
