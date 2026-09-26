"""FastAPI 入口：接口 + 静态托管 + 启动调度器。

职责边界：
- 仅「判题」依赖 Agent（/api/answer 内调用 judge）；
- 题库导入、热力图、错题本、艾宾浩斯调度、邮件发送均由本软件完成。
"""
import os
import re
import json
import uuid
import sys
import random
from datetime import datetime, timedelta, date
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from fpdf import FPDF

from .db import init_db, get_db, Base
from . import models
from .judge import judge
from .scheduler import start_scheduler
from .ebbinghaus import get_steps, next_review_for_stage, advance_stage, is_mastered
from .todo_routes import router as todo_router
from .storage import get_storage

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
BANK_PATH = os.path.join(BASE_DIR, "..", "Claw", "题库", "agent_interview_bank.json")
DEFAULT_APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")


def _csv_env(name: str) -> list[str]:
    """读取逗号分隔环境变量，空值代表不开启对应跨域能力。"""
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """读取安全上限；错误环境值回退默认，避免启动时被无效配置打断。"""
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


MAX_QUIZ_ITEMS = _bounded_env_int("MAX_QUIZ_ITEMS", 50, 1, 200)
MAX_CONCURRENT_JUDGES = _bounded_env_int("MAX_CONCURRENT_JUDGES", 8, 1, 32)

app = FastAPI(
    title="面试八股文长期记忆训练系统",
    version="1.1.0",
    description="GitHub 风格热力图 + 错题本 + 艾宾浩斯邮件推送 + 多标签题库筛选 + LLM 判题",
)

_CORS_ALLOW_ORIGINS = _csv_env("CORS_ALLOW_ORIGINS")
if _CORS_ALLOW_ORIGINS:
    # 单服务同源访问不需要 CORS。只有明确配置的前端来源才被允许，避免默认把
    # 题库、学习记录和管理接口暴露给任意网页。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ALLOW_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )


# ----------------------------- 技术文章摘抄（lianglianglee 静态站 · 单服务融合） -----------------------------
# 硬约束：book/ 目录内容严禁修改。文章站 index.html 全部使用绝对路径（/static、/专栏、/文章、
# /PDF、/恋爱必修课、/极客时间、/），无法挂到子路径（否则 404），也不能改 HTML。
# 解决方案：把文章站挂载在 /articles 子路径，并用中间件把「响应正文里」的绝对路径改写为
# /articles/...。磁盘文件零改动，且不再需要单独启动 Gin。
ARTICLES_BOOK_DIR = os.getenv(
    "ARTICLES_BOOK_DIR", os.path.join(BASE_DIR, "articles_book")
).strip()
ARTICLES_PREFIX = "/articles"
ARTICLES_AVAILABLE = bool(ARTICLES_BOOK_DIR and os.path.isdir(ARTICLES_BOOK_DIR))
ARTICLES_UNAVAILABLE_MESSAGE = "技术文章资源未配置；请设置 ARTICLES_BOOK_DIR 指向 book 目录。"
# 兜底约束正文内可能过宽的元素（img/table/pre/svg/video/canvas），避免撑爆 iframe 视口产生横滚
# max-width:100% + height:auto 让原生超宽的流程图/表格按父容器自适应缩小
# box-sizing:border-box 让 padding 不外溢
_ART_BOOKCONTENT_INLINE_STYLE_RE = re.compile(
    r'(<div class="book-content")\s+style="[^"]*\bmax-width\b[^"]*"',
    re.IGNORECASE,
)
# 文章站实际使用的绝对路径前缀（对 book/ 全量扫描所得；明文 + URL 编码两种都覆盖）
_ART_ABS_PREFIXES = [
    "/static", "/专栏", "/文章", "/PDF", "/恋爱必修课", "/极客时间",
    "/%e4%b8%93%e6%a0%8f", "/%e6%96%87%e7%ab%a8",
    "/%e6%81%8b%e7%88%b1%e5%bf%85%e4%bf%ae%e8%af%be", "/%e6%9e%81%e5%ae%a2%e6%97%b6%e9%97%b4",
]
_ART_ABS_RE = re.compile("|".join(re.escape(p) for p in _ART_ABS_PREFIXES), re.IGNORECASE)
# 根路径链接（href="/"、src="/"、action="/"）→ /articles
_ART_ROOT_ATTR_RE = re.compile(r'(?i)(href|src|action)=("|\')/(\2)')
# lianglianglee 备份站「.md 实为 HTML」嗅探标记：取 body 头部前 512 字节判断
_ART_HTML_SNIFF = (
    b"<!doctype", b"<html", b"<head", b"<body",
)
# iframe 嵌入适配样式：注入到 <head> 末尾，覆盖 lianglianglee 模板硬编码的
# .book-content { max-width: 960px; margin: 0 auto }，让正文铺满可用宽度。
# 关键点（按优先级）：
#   1. 用 `html body .book-content` 提升 specificity，确保稳赢内联 style。
#   2. 同时设 `max-width:none !important` + `width:100% !important`，覆盖内联 `max-width:960px`。
#   3. `.book-content` 的 margin-left 必须为 0：外侧 `.off-canvas-content` 已用
#      margin-left:12rem 给固定侧栏让位，若这里再加 12rem 会变成「双重 margin」，
#      内容被右推并顶出视口 → 父级 overflow-x:auto 切出横向滚动条（历史 bug 根因）。
#   4. `box-sizing:border-box` + padding 两侧对称，避免外溢。
#   5. `.off-canvas-content` 加 overflow-x:hidden 兜底，杜绝内部横向滚动条。
#   6. 窄屏（<=820px）缩小间距；侧栏仍保留，避免 iframe 中的文章导航不可达。
_ART_FULLWIDTH_CSS = (
    "<style data-interview-memory='fullwidth'>"
    # 正文容器：铺满父级（off-canvas-content 已让出侧栏宽度），不再右移
    "html body .book-content{"
    "max-width:none!important;width:100%!important;"
    "margin-left:0!important;margin-right:0!important;"
    "margin-top:0!important;margin-bottom:0!important;"
    "padding-left:0.75rem!important;padding-right:0.75rem!important;"
    "box-sizing:border-box!important;"
    "overflow-x:hidden!important;overflow-y:auto!important;"
    "}"
    # 父级：保留对固定侧栏的 12rem 让位，纵向可滚，横向 hidden 兜底
    "html body .off-canvas-content{margin-left:12rem!important;overflow-y:auto!important;overflow-x:hidden!important;padding-left:1rem!important;padding-right:1rem!important;}"
    # body 自身去掉横向 hidden，确保代码块过长能横滚而不是被静默切掉
    "html body{overflow-x:auto!important;}"
    # 兜底约束正文内可能过宽的元素：流程图/表格/代码块/图片/视频/canvas
    # 让它们自适应缩小到父容器宽度，不撑爆布局（产生 iframe 横滚）
    ".book-content img,.book-content video,.book-content canvas,"
    ".book-content svg,.book-content table,.book-content pre{"
    "max-width:100%!important;height:auto!important;box-sizing:border-box!important;"
    "}"
    ".book-content pre{overflow-x:auto!important;}"
    # 窄屏（<=820px）：缩小正文间距，但不隐藏文章自身的侧栏
    "@media (max-width:820px){"
    "html body .off-canvas-content{margin-left:0!important;padding-left:0.5rem!important;padding-right:0.5rem!important;}"
    "html body .book-content{padding-left:0!important;padding-right:0!important;}"
    "}"
    "</style>"
)


class ArticleRewriteMiddleware(BaseHTTPMiddleware):
    """挂载在 /articles 子路径下的文章站专用中间件。

    两件事：
      1. 路径重写：把响应正文里的绝对路径（/static、/专栏、/文章、href="/" 等）改写为 /articles/...
         —— 因为 book/ 目录里的 HTML 用了根绝对路径，无法直接挂到子路径，必须改响应不改磁盘。
      2. lianglianglee 备份站里的 .md 文件其实是 HTML，但 Starlette StaticFiles 按扩展名返回
         text/plain / text/x-markdown，浏览器会按纯文本把源码显示出来。这里嗅探头部强制
         改为 text/html 并一并执行路径重写，让 iframe 真正渲染文章内容。
    """

    def __init__(self, app):
        super().__init__(app)

    @staticmethod
    def _is_rewritable_text(ctype: str) -> bool:
        c = ctype.lower()
        return (
            "text/html" in c
            or "text/css" in c
            or "javascript" in c
            or "text/plain" in c
            or "text/markdown" in c
            or "text/x-markdown" in c
            or "application/xhtml" in c
        )

    @staticmethod
    def _strip_content_length(headers):
        return {k: v for k, v in headers.items() if k.lower() != "content-length"}

    @staticmethod
    def _strip_content_type(headers):
        """剥掉 content-type：让 media_type 参数接管，避免被原响应带错。"""
        return {k: v for k, v in headers.items() if k.lower() != "content-type"}

    async def dispatch(self, request, call_next):
        if not request.url.path.startswith(ARTICLES_PREFIX):
            return await call_next(request)

        response = await call_next(request)
        ctype = (response.headers.get("content-type", "") or "").lower()
        if not self._is_rewritable_text(ctype):
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # 嗅探：body 头部像 HTML（常见 lianglianglee .md 备份）→ 强制改 text/html
        needs_html = "text/html" not in ctype
        if needs_html:
            head = body[:512].lstrip().lower()
            if any(head.startswith(tag) for tag in _ART_HTML_SNIFF):
                ctype = "text/html; charset=utf-8"
                needs_html = False

        # 真正需要重写的只有 HTML/CSS/JS；其他（真·纯文本、XML 等）原样透传
        if needs_html and "text/css" not in ctype and "javascript" not in ctype:
            headers = self._strip_content_length(response.headers)
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.headers.get("content-type"),
            )

        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            headers = self._strip_content_length(response.headers)
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.headers.get("content-type"),
            )

        # 1) 绝对路径前缀 → /articles/前缀
        text = _ART_ABS_RE.sub(lambda m: ARTICLES_PREFIX + m.group(0), text)
        # 2) 根路径属性值 "/" → "/articles/"（补尾斜杠，否则站内根链接点击 404）
        text = _ART_ROOT_ATTR_RE.sub(r"\1=\2" + ARTICLES_PREFIX + "/" + r"\2", text)
        # 3) 删除 .book-content 上的 inline style（CSS !important 压不过 inline，必须删）
        #    仅匹配含 max-width 的情况，不会误伤其他合法 inline style
        text = _ART_BOOKCONTENT_INLINE_STYLE_RE.sub(r"\1", text)
        # 3) iframe 适配：注入 CSS 覆盖 lianglianglee 模板的 max-width:960px。
        #    命中最后一个 </head>（lianglianglee 有嵌套 <head><head> 结构，插在真正的
        #    head 闭合前才干净），兜底没 </head> 就插到 <body> 前。
        head_end = text.rfind("</head>")
        if head_end != -1:
            text = text[:head_end] + _ART_FULLWIDTH_CSS + text[head_end:]
        else:
            text = _ART_FULLWIDTH_CSS + text
        new_body = text.encode("utf-8")
        headers = self._strip_content_length(response.headers)
        headers = self._strip_content_type(headers)
        # 浏览器缓存控制：HTML 经常被改写，必须禁用中间缓存避免拿旧版
        headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        headers["Pragma"] = "no-cache"
        headers["Expires"] = "0"
        resp = Response(
            content=new_body,
            status_code=response.status_code,
            headers=headers,
            media_type=ctype,
        )
        return resp


app.add_middleware(ArticleRewriteMiddleware)


init_db()

scheduler = start_scheduler()


# ----------------------------- Pydantic 模型 -----------------------------
class QuestionImport(BaseModel):
    platform: str = ""
    category: str = ""
    tags: str = ""  # 逗号分隔的多标签
    question_text: str
    reference_answer: str = ""
    difficulty: int = 1


class QuestionImportBatch(BaseModel):
    path: Optional[str] = None  # 若为空，使用默认题库路径


class AnswerIn(BaseModel):
    question_id: int
    user_answer: str


class ReviewFeedback(BaseModel):
    remembered: bool = True


class SettingsIn(BaseModel):
    email: str = ""
    push_time: str = "09:00"
    ebbinghaus_steps: str = "1,2,4,7,15,30,60"
    app_base_url: str = DEFAULT_APP_BASE_URL


class QuestionOut(BaseModel):
    id: int
    platform: str
    category: str
    tags: str
    difficulty: int
    question_text: str
    keywords: str = ""  # 重点关键词，逗号分隔（用于前端高亮）
    images: str = ""  # JSON 数组：附件图片 URL（由 reference_answer 内 markdown 推导，亦可显式覆盖）


class QuestionDetailOut(QuestionOut):
    reference_answer: str


class CategoryDetailOut(BaseModel):
    name: str
    count: int
    icon: str
    description: str


class QuestionUpdate(BaseModel):
    platform: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    difficulty: Optional[int] = None
    question_text: Optional[str] = None
    reference_answer: Optional[str] = None
    keywords: Optional[str] = None  # 重点关键词，逗号分隔
    images: Optional[str] = None  # 显式覆盖；为 None 时按 reference_answer 内 ![alt](url) 重新推导


class NoteIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class NoteOut(BaseModel):
    id: int
    question_id: int
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AnswerOut(BaseModel):
    is_correct: Optional[bool]
    explanation: str
    error_reason: str
    source: str
    reference_answer: str


class QuizSubmitItem(BaseModel):
    question_id: int
    user_answer: str = ""


class QuizSubmitIn(BaseModel):
    items: List[QuizSubmitItem]


class QuizResultItem(BaseModel):
    question_id: int
    is_correct: Optional[bool] = None
    explanation: str = ""
    error_reason: str = ""
    judge_by: str = ""
    reference_answer: str = ""
    user_answer: str = ""


class QuizSubmitOut(BaseModel):
    results: List[QuizResultItem]


class InterviewExpIn(BaseModel):
    company: str
    role: str = ""
    position: str = ""
    offer_result: str = ""
    content: str
    questions: str = ""


class InterviewExpOut(BaseModel):
    id: int
    company: str
    role: str
    position: str
    offer_result: str
    content: str
    questions: str
    created_at: str


# ----------------------------- 工具函数 -----------------------------
_DEFAULT_SETTINGS = {
    "email": "",
    "push_time": "09:00",
    "ebbinghaus_steps": "1,2,4,7,15,30,60",
    "app_base_url": DEFAULT_APP_BASE_URL,
}


def get_settings(db: Session) -> models.Settings:
    s = db.query(models.Settings).first()
    if not s:
        s = models.Settings(**_DEFAULT_SETTINGS)
        db.add(s)
        db.commit()
        db.refresh(s)
        return s

    # 兼容旧库：早期 Settings 列没有数据库默认值，已有行可能留下 NULL。
    # 仅补齐 NULL，不覆盖用户已保存的任何非空配置。
    changed = False
    for field, default in _DEFAULT_SETTINGS.items():
        if getattr(s, field) is None:
            setattr(s, field, default)
            changed = True
    if changed:
        db.commit()
        db.refresh(s)
    return s


def _tag_filter(query, tags: str):
    """多标签筛选：逗号分隔、全部精确 token 匹配（AND）。"""
    if not tags:
        return query
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    if not tag_list:
        return query
    for tag in tag_list:
        # ``tags`` 是逗号分隔的 token。不能用 ``%tag%``：它会把 JVM 命中
        # JVM调优，也会把前端分类/题干里的普通词误当标签。
        # 存量数据会忽略标签内的普通空格；查询 token 要按同一规则标准化。
        # LIKE 的转义值只能用于 LIKE，不能拿来与原始 token 做等值比较。
        normalized_tag = tag.replace(" ", "")
        escaped_like = normalized_tag.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        normalized = func.replace(func.coalesce(models.Question.tags, ""), " ", "")
        query = query.filter(
            (normalized == normalized_tag)
            | normalized.like(escaped_like + ",%", escape="\\")
            | normalized.like("%," + escaped_like + ",%", escape="\\")
            | normalized.like("%," + escaped_like, escape="\\")
        )
    return query


_PUSH_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _validated_schedule_settings(payload: SettingsIn) -> tuple[str, str]:
    """验证设置输入，并返回标准化的 (HH:MM, steps)；失败时绝不改数据库。"""
    push_time = (payload.push_time or "").strip()
    if not _PUSH_TIME_RE.fullmatch(push_time):
        raise HTTPException(status_code=422, detail="push_time 必须是 HH:MM（00:00–23:59）")

    raw_parts = (payload.ebbinghaus_steps or "").split(",")
    parts = [part.strip() for part in raw_parts]
    if not parts or any(not part for part in parts):
        raise HTTPException(status_code=422, detail="ebbinghaus_steps 必须是逗号分隔的正整数")
    try:
        steps = [int(part) for part in parts]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="ebbinghaus_steps 必须是逗号分隔的正整数") from exc
    if any(step <= 0 for step in steps) or any(a >= b for a, b in zip(steps, steps[1:])):
        raise HTTPException(status_code=422, detail="ebbinghaus_steps 必须为严格递增的正整数")
    return push_time, ",".join(str(step) for step in steps)


def _increment_activity(db: Session, is_correct: Optional[bool], day: Optional[date] = None):
    """原子增加当天热力图计数，避免并发请求读改写导致丢计数。"""
    activity_day = day or date.today()
    values = {
        "answered": func.coalesce(models.Activity.answered, 0) + 1,
    }
    if is_correct is True:
        values["correct"] = func.coalesce(models.Activity.correct, 0) + 1
    elif is_correct is False:
        values["wrong"] = func.coalesce(models.Activity.wrong, 0) + 1

    updated = (db.query(models.Activity)
               .filter(models.Activity.day == activity_day)
               .update(values, synchronize_session=False))
    if updated:
        return

    try:
        # 唯一主键保证两个首答请求不会各自插入一行；竞争失败者回退到原子 UPDATE。
        with db.begin_nested():
            db.add(models.Activity(
                day=activity_day,
                answered=1,
                correct=1 if is_correct is True else 0,
                wrong=1 if is_correct is False else 0,
            ))
            db.flush()
    except IntegrityError:
        (db.query(models.Activity)
           .filter(models.Activity.day == activity_day)
           .update(values, synchronize_session=False))


def _update_wrong_book(db: Session, question_id: int, user_answer: str, error_reason: str, now: datetime):
    """原子创建或更新错题本；唯一索引和 savepoint 覆盖首写竞争。"""
    values = {
        # 历史 NULL 表示至少已经记录过一次，不应在下一次答错时退回为 1。
        "wrong_count": func.coalesce(models.WrongBook.wrong_count, 1) + 1,
        "last_user_answer": user_answer,
        "error_reason": error_reason or models.WrongBook.error_reason,
        "mastery": "reviewing",
        "updated_at": now,
        "first_wrong_at": func.coalesce(models.WrongBook.first_wrong_at, now),
    }
    updated = (db.query(models.WrongBook)
               .filter(models.WrongBook.question_id == question_id)
               .update(values, synchronize_session=False))
    if updated:
        return

    try:
        with db.begin_nested():
            db.add(models.WrongBook(
                question_id=question_id,
                first_wrong_at=now,
                wrong_count=1,
                last_user_answer=user_answer,
                error_reason=error_reason or "",
                mastery="learning",
                updated_at=now,
            ))
            db.flush()
    except IntegrityError:
        # 另一个请求刚好插入同题行，保持其首错时间并给它原子加一。
        (db.query(models.WrongBook)
           .filter(models.WrongBook.question_id == question_id)
           .update(values, synchronize_session=False))


def _ensure_review_schedule(db: Session, question_id: int, now: datetime):
    """只在首次答错时建计划；唯一约束防止并发请求生成重复计划。"""
    if (db.query(models.ReviewSchedule.id)
            .filter(models.ReviewSchedule.question_id == question_id)
            .first()):
        return
    try:
        with db.begin_nested():
            db.add(models.ReviewSchedule(
                question_id=question_id,
                stage=1,
                next_review_at=now + timedelta(days=1),
                review_count=0,
                status="pending",
            ))
            db.flush()
    except IntegrityError:
        # 竞争者已成功创建，无需覆盖已有的阶段或下次复习时间。
        pass


def _persist_answer_result(
    db: Session,
    question: models.Question,
    user_answer: str,
    is_correct: Optional[bool],
    explanation: str,
    error_reason: str,
    source: str,
):
    """写入一次作答及其所有本地副作用；调用方统一在最后 commit。"""
    now = datetime.utcnow()
    db.add(models.Submission(
        question_id=question.id,
        user_answer=user_answer,
        is_correct=is_correct,
        judge_by=source,
        explanation=explanation,
        submitted_at=now,
    ))
    _increment_activity(db, is_correct)
    if is_correct is False:
        _update_wrong_book(db, question.id, user_answer, error_reason or "", now)
        _ensure_review_schedule(db, question.id, now)


# 分类 -> emoji 图标映射（面试鸭风格的大分类卡片）
_CATEGORY_ICONS = {
    # 精确匹配优先
    "concurrenthashmap": "🔀",
    "算法手撕": "✍️",
    "工程与并发": "⚙️",
    "记忆与上下文": "🧠",
    "java": "☕", "python": "🐍", "go": "🐹", "golang": "🐹", "c++": "➕", "c#": "♯",
    "javascript": "🟨", "js": "🟨", "typescript": "📘", "ts": "📘",
    "前端": "💻", "frontend": "💻", "vue": "🟩", "react": "⚛️", "angular": "🅰️",
    "mysql": "🐬", "redis": "🔴", "kafka": "📨", "rabbitmq": "🐰", "rocketmq": "🚀",
    "mongodb": "🍃", "mongo": "🍃", "elasticsearch": "🔎", "es": "🔎", "clickhouse": "🏠",
    "spring": "🌱", "springboot": "🥾", "springcloud": "☁️", "spring cloud": "☁️",
    "mybatis": "🟦", "netty": "🕸️", "nginx": "🟩", "tomcat": "🐈", "dubbo": "🦅",
    "git": "🌿", "docker": "🐳", "kubernetes": "☸️", "k8s": "☸️", "linux": "🐧",
    "操作系统": "🖥️", "os": "🖥️", "计算机网络": "🌐", "网络": "🌐", "network": "🌐",
    "算法": "📐", "数据结构": "🌲", "设计模式": "🎨", "手写": "✍️", "手撕": "✍️",
    "jvm": "☕", "并发": "🧵", "多线程": "🧵", "线程": "🧵", "锁": "🔒",
    "分布式": "🌐", "微服务": "🧩", "消息队列": "📨", "mq": "📨",
    "后端": "⚙️", "backend": "⚙️", "服务端": "🖧",
    "场景题": "🎭", "系统设计": "🏗️", "架构": "🏗️", "system design": "🏗️",
    "智力题": "🧩", "puzzle": "🧩", "数学题": "🔢",
    "ai": "🤖", "agent": "🤖", "llm": "🧠", "大模型": "🧠", "rag": "🔍",
    "智能体": "👥", "多智能体": "👥", "提示工程": "💡", "prompt": "💡",
    "推理": "🧠", "模型": "🔧", "微调": "🔧", "向量": "🧬", "检索": "🔍",
    "安全": "🛡️", "对齐": "🛡️", "工具": "🛠️", "调用": "🛠️",
    "运维": "🚀", "devops": "🚀", "sre": "🚀", "测试": "🧪", "qa": "🧪",
    "hr": "💼", "behavioral": "💼", "面经": "📝", "校招": "🎓", "社招": "💼",
    "评估": "📊", "观测": "📊", "监控": "📊", "日志": "📜",
    "记忆": "🧠", "上下文": "💬", "知识": "📚",
    "concurrent": "🧵", "hashmap": "🔀", "map": "🗺️", "hashtable": "🔀",
}


# 分类 -> 简短描述（面试鸭风格卡片副标题）
_CATEGORY_DESCRIPTIONS = {
    "java": "企业级后端开发核心语言面试题",
    "jvm": "Java 虚拟机、内存模型与 GC 面试题",
    "python": "Python 语言特性与工程实践面试题",
    "go": "Go 语言并发与工程实践面试题",
    "golang": "Go 语言并发与工程实践面试题",
    "mongodb": "文档数据库、BSON 与数据建模面试题",
    "c++": "C++ 语言与系统开发面试题",
    "mysql": "关系型数据库与 SQL 优化面试题",
    "redis": "高性能缓存与分布式锁面试题",
    "kafka": "高吞吐消息队列面试题",
    "rabbitmq": "RabbitMQ 消息队列面试题",
    "rocketmq": "RocketMQ 消息队列面试题",
    "spring": "Spring 框架核心原理面试题",
    "springboot": "Spring Boot 自动配置与实战面试题",
    "springcloud": "Spring Cloud 微服务面试题",
    "并发编程": "多线程、锁与并发容器面试题",
    "分布式": "分布式系统理论与中间件面试题",
    "操作系统": "进程线程、内存与 IO 面试题",
    "计算机网络": "TCP/IP、HTTP 与网络协议面试题",
    "算法手撕": "常考算法与数据结构手写题",
    "数据结构": "链表、树、哈希表等数据结构面试题",
    "设计模式": "常用设计模式与最佳实践",
    "场景题": "系统设计与业务场景分析题",
    "智力题": "逻辑思维与算法谜题",
    "rag与知识": "检索增强生成与知识库面试题",
    "agent架构": "LLM Agent 设计与实现面试题",
    "多智能体": "Multi-Agent 系统协作面试题",
    "提示工程": "Prompt 设计与优化面试题",
    "模型微调与对齐": "大模型微调、RLHF 与安全对齐",
    "评估与观测": "LLM 评测、监控与可观测性",
    "主流框架": "LangChain / LangGraph 等框架使用",
    "工具调用与function calling": "Function Calling 与工具链",
    "多模态与向量检索": "向量数据库与多模态 RAG",
    "工程与并发": "Go/Java 高并发工程实践",
    "安全与对齐": "AI 安全与价值对齐",
    "推理框架": "vLLM、TensorRT-LLM 等推理优化",
    "记忆与上下文": "长上下文与记忆机制",
    "后端系统设计面试题": "高并发系统设计",
    "后端场景面试题": "业务场景与技术方案",
    "ai 应用架构设计面试题": "LLM 应用、RAG、Agent 架构与算法工程面试题",
    "ai 智能体项目面试题": "AI 智能体项目设计与工程实践面试题",
    "go 基础面试题": "Go 语言基础语法与核心特性面试题",
    "go 标准库面试题": "Go 标准库、并发与底层实现面试题",
    "go 面向对象面试题": "Go 接口、类型系统与面向对象面试题",
    "java 集合面试题": "Java 集合框架与数据结构面试题",
    "java 并发面试题": "Java 多线程、JUC 与并发编程面试题",
    "java 虚拟机面试题": "JVM 内存模型、GC 与调优面试题",
    "spring 面试题": "Spring 框架核心原理与实战面试题",
    "消息队列面试题": "Kafka / RabbitMQ / RocketMQ 消息队列面试题",
    "后端经典面试题合集": "后端经典面试题与算法手撕合集",
}


def _category_icon(name: str) -> str:
    """根据分类名返回 emoji 图标，优先精确匹配，其次关键字匹配。"""
    if not name:
        return "📄"
    key = name.lower().strip()
    if key in _CATEGORY_ICONS:
        return _CATEGORY_ICONS[key]
    # 关键字命中：越长越具体的规则优先
    for k, v in sorted(_CATEGORY_ICONS.items(), key=lambda x: -len(x[0])):
        if k in key:
            return v
    return "📄"


def _category_description(name: str) -> str:
    """根据分类名返回简短描述，未命中则返回通用描述。"""
    if not name:
        return "面试题合集"
    key = name.lower().strip()
    if key in _CATEGORY_DESCRIPTIONS:
        return _CATEGORY_DESCRIPTIONS[key]
    for k, v in sorted(_CATEGORY_DESCRIPTIONS.items(), key=lambda x: -len(x[0])):
        if k in key:
            return v
    # 根据关键字兜底
    if any(k in key for k in ("面试题", "题")):
        return "精选面试题"
    return name + " 面试题"


# 参考答案中的图片 markdown 提取：![alt](url)
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")


def extract_images(text: str) -> list:
    """从参考答案 markdown 文本中提取所有图片 URL（去重保持顺序）。"""
    if not text:
        return []
    seen, out = set(), []
    for m in _IMG_RE.finditer(text):
        url = m.group(2).strip()
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _question_out(question: models.Question, include_reference_answer: bool = False) -> dict:
    """将历史可空题目列规范为前端约定的空字符串。

    早期 SQLite 行允许 platform/category/tags/images/keywords 为 NULL；直接把 ORM
    对象交给 ``QuestionOut`` 会触发 FastAPI 的响应校验 500。读取接口统一在边界
    转换，既不批量改写用户库，也保持前端字段始终为字符串。
    """
    data = {
        "id": question.id,
        "platform": question.platform or "",
        "category": question.category or "",
        "tags": question.tags or "",
        "difficulty": question.difficulty if question.difficulty is not None else 1,
        "question_text": question.question_text or "",
        "keywords": question.keywords or "",
        "images": question.images or "",
    }
    if include_reference_answer:
        data["reference_answer"] = question.reference_answer or ""
    return data


# ----------------------------- 题库导入（Agent -> 软件） -----------------------------
@app.post("/api/questions/import", response_model=QuestionOut, summary="导入单题")
def import_question(payload: QuestionImport, db: Session = Depends(get_db)):
    q = models.Question(
        platform=payload.platform,
        category=payload.category,
        tags=payload.tags,
        question_text=payload.question_text,
        reference_answer=payload.reference_answer,
        difficulty=payload.difficulty,
        created_at=datetime.utcnow(),
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _question_out(q)


@app.post("/api/questions/import-batch", summary="批量导入题库（JSON）")
def import_question_batch(payload: QuestionImportBatch, db: Session = Depends(get_db)):
    """从 JSON 题库批量导入。path 为空时使用默认 AI 面试题库。"""
    import json

    path = payload.path or BANK_PATH
    if not os.path.exists(path):
        # 尝试相对当前项目目录
        alt_path = os.path.join(BASE_DIR, "agent_interview_bank.json")
        path = alt_path if os.path.exists(alt_path) else path
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="题库文件不存在: " + path)

    with open(path, "r", encoding="utf-8") as f:
        bank = json.load(f)

    questions = bank.get("questions", [])
    imported = 0
    skipped = 0
    seen_titles = set()
    for item in questions:
        text = item.get("question", "").strip()
        if not text:
            continue
        # 去重：相同题面跳过
        exists = db.query(models.Question).filter(models.Question.question_text == text).first()
        if exists or text in seen_titles:
            skipped += 1
            continue
        seen_titles.add(text)
        # 标签：category + key_points 共同作为标签
        tag_parts = [item.get("category", "")]
        tag_parts.extend(item.get("key_points", []))
        tags = ",".join(sorted({t.strip() for t in tag_parts if t.strip()}))

        q = models.Question(
            platform=item.get("platform", ""),
            category=item.get("category", ""),
            tags=tags,
            question_text=text,
            reference_answer=item.get("reference_answer", ""),
            difficulty=int(item.get("difficulty", 2)),
            created_at=datetime.utcnow(),
        )
        db.add(q)
        imported += 1
    db.commit()
    return {"imported": imported, "skipped": skipped, "total": len(questions), "path": path}


@app.get("/api/questions", summary="题库列表")
def list_questions(
    limit: int = 50,
    offset: int = 0,
    keyword: str = "",
    category: str = "",
    difficulty: int = 0,
    level: int = 0,
    tags: str = "",
    order: str = "asc",
    db: Session = Depends(get_db),
):
    """题库列表：支持关键词搜索、分类/难度/多标签筛选、分页，返回 {total, items}。

    difficulty: 精确匹配 1~5；level: 1=简单(≤2) 2=中等(=3) 3=困难(≥4)；tags: 逗号分隔多标签。
    order: 'asc' (按 id 升序 = 按学习顺序, 默认) 或 'desc' (最新在前).
    """
    q = db.query(models.Question)
    if keyword:
        q = q.filter(
            models.Question.question_text.contains(keyword)
            | models.Question.reference_answer.contains(keyword)
        )
    if category:
        q = q.filter(models.Question.category == category)
    if difficulty:
        q = q.filter(models.Question.difficulty == difficulty)
    if level == 1:
        q = q.filter(models.Question.difficulty <= 2)
    elif level == 2:
        q = q.filter(models.Question.difficulty == 3)
    elif level == 3:
        q = q.filter(models.Question.difficulty >= 4)
    q = _tag_filter(q, tags)
    total = q.count()
    _sort = models.Question.id.asc() if order == "asc" else models.Question.id.desc()
    qs = q.order_by(_sort).offset(offset).limit(limit).all()
    return {"total": total, "items": [{
        "id": x.id, "platform": x.platform, "category": x.category,
        "tags": x.tags, "difficulty": x.difficulty, "question_text": x.question_text,
        "keywords": x.keywords or "",
        "reference_answer": x.reference_answer or ""
    } for x in qs]}


@app.get("/api/question/{qid}", response_model=QuestionDetailOut, summary="题目详情")
def get_question(qid: int, db: Session = Depends(get_db)):
    """题目详情（含参考答案，供前端「查看解析」）。"""
    q = db.query(models.Question).filter(models.Question.id == qid).first()
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    return _question_out(q, include_reference_answer=True)


# ----------------------------- 图片上传 & 题目更新（答案配图） -----------------------------
_ALLOWED_IMG = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}


@app.post("/api/images/upload", summary="上传图片（用于答案配图）")
async def upload_image(file: UploadFile = File(...)):
    """接收图片，保存到 data/images/，返回可访问 URL（/data/images/<文件名>）。"""
    original = (file.filename or "image").lower()
    ext = os.path.splitext(original)[1]
    if ext not in _ALLOWED_IMG:
        raise HTTPException(
            status_code=400,
            detail="仅支持图片格式：png / jpg / jpeg / gif / webp / svg / bmp",
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="空文件")
    # 通过存储抽象层保存：本地模式落 data/images/，S3 模式传对象存储
    storage = get_storage()
    url = storage.save(content, file.filename or "image", getattr(file, "content_type", None))
    fname = url.rsplit("/", 1)[-1]
    return {"url": url, "filename": fname}


@app.put("/api/questions/{qid}", summary="更新题目（含答案与配图）")
def update_question(qid: int, payload: QuestionUpdate, db: Session = Depends(get_db)):
    """更新题目文本/参考答案；不传 images 时由 reference_answer 内 markdown 自动推导图片列表。"""
    q = db.query(models.Question).filter(models.Question.id == qid).first()
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    if payload.platform is not None:
        q.platform = payload.platform
    if payload.category is not None:
        q.category = payload.category
    if payload.tags is not None:
        q.tags = payload.tags
    if payload.difficulty is not None:
        q.difficulty = payload.difficulty
    if payload.question_text is not None:
        q.question_text = payload.question_text
    if payload.reference_answer is not None:
        q.reference_answer = payload.reference_answer
        # 参考答案文本是唯一真相源：改写时同步重算 images 列表
        q.images = json.dumps(extract_images(payload.reference_answer), ensure_ascii=False)
    if payload.images is not None:
        q.images = payload.images
    if payload.keywords is not None:
        q.keywords = payload.keywords
    db.commit()
    db.refresh(q)
    return {
        "status": "updated", "id": qid,
        "reference_answer": q.reference_answer,
        "images": q.images or "[]",
    }


@app.get("/api/categories", summary="分类列表")
def list_categories(db: Session = Depends(get_db)):
    """去重分类列表，供前端筛选 chips。"""
    rows = db.query(models.Question.category).distinct().all()
    cats = sorted({r[0] for r in rows if r[0]})
    return cats


@app.get("/api/categories/detail", response_model=List[CategoryDetailOut], summary="分类详情列表")
def list_category_details(db: Session = Depends(get_db)):
    """分类详情：名称、题目数量、图标，供前端面试鸭风格卡片网格。"""
    rows = (
        db.query(models.Question.category, func.count(models.Question.id))
        .group_by(models.Question.category)
        .all()
    )
    return sorted(
        [{
            "name": r[0] or "未分类",
            "count": r[1],
            "icon": _category_icon(r[0]),
            "description": _category_description(r[0]),
        } for r in rows],
        key=lambda x: (-x["count"], x["name"]),
    )


@app.get("/api/tags", summary="标签列表")
def list_tags(db: Session = Depends(get_db)):
    """所有题目标签聚合（去重排序）。"""
    rows = db.query(models.Question.tags).all()
    tags = set()
    for r in rows:
        if r[0]:
            tags.update(t.strip() for t in r[0].split(",") if t.strip())
    return sorted(tags)


@app.get("/api/questions/random", summary="随机抽题")
def random_question(db: Session = Depends(get_db)):
    """取一道题用于练习（优先待复习，否则真正随机，避免始终同一题）。"""
    due = db.query(models.ReviewSchedule).filter(
        models.ReviewSchedule.status == "pending",
        models.ReviewSchedule.next_review_at <= datetime.utcnow(),
    ).order_by(func.random()).first()
    if due:
        q = db.query(models.Question).filter(models.Question.id == due.question_id).first()
    else:
        q = db.query(models.Question).order_by(func.random()).first()
    if not q:
        raise HTTPException(status_code=404, detail="题库为空，请先导入题目")
    return {"id": q.id, "category": q.category, "platform": q.platform,
            "tags": q.tags, "question_text": q.question_text}


def _practice_out(q, total, remaining, round_complete):
    return {
        "id": q.id,
        "category": q.category,
        "platform": q.platform,
        "tags": q.tags,
        "question_text": q.question_text,
        "total": total,
        "remaining": remaining,
        "round_complete": round_complete,
    }


# ----------------------------- 刷题模式（取下一题） -----------------------------
@app.get("/api/practice/next", summary="刷题模式·取下一题")
def practice_next(
    mode: str = "random",
    category: str = "",
    categories: str = "",
    seen_ids: str = "",
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """刷题模式取题。

    mode:
      - random：在本题范围内随机抽题，自动排除本轮已见过的题目；只有当范围内题目"全部刷完"后才重置，
        重置时尽量不重复刚刷到的那一道（范围>1 时）。
      - sequential：按 id 升序依次出题，到末尾后循环回到开头（开启新的一轮）。
    category: 单分类（如 "MySQL"）；categories: 逗号分隔的多分类（优先级高于 category）。
    seen_ids: random 模式下本轮已见题目 id（逗号分隔），用于去重。
    offset: sequential 模式下的序号（0 基），服务端自动对总数取模。
    """
    q = db.query(models.Question)
    cat_list = [c.strip() for c in categories.split(",") if c.strip()] if categories else []
    if cat_list:
        q = q.filter(models.Question.category.in_(cat_list))
    elif category:
        q = q.filter(models.Question.category == category)
    total = q.count()
    if total == 0:
        raise HTTPException(status_code=404, detail="该范围内没有题目，换一个分类试试")

    ordered = q.order_by(models.Question.id.asc())

    if mode == "sequential":
        idx = offset % total
        question = ordered.offset(idx).first()
        return _practice_out(question, total, total - (idx + 1), offset >= total)

    # random 模式
    seen_order = []
    for s in seen_ids.split(","):
        s = s.strip()
        if s.isdigit():
            seen_order.append(int(s))
    seen = set(seen_order)
    filter_ids = [x.id for x in ordered.with_entities(models.Question.id).all()]
    seen_in_filter = seen & set(filter_ids)
    unseen_ids = [i for i in filter_ids if i not in seen_in_filter]
    if unseen_ids:
        pick = (db.query(models.Question)
                .filter(models.Question.id.in_(unseen_ids))
                .order_by(func.random()).first())
        return _practice_out(pick, total, len(unseen_ids) - 1, False)

    # 全部刷完 -> 重置新一轮（范围>1 时尽量不重复刚刷到的那一道）
    pool = set(filter_ids)
    if len(pool) > 1 and seen_in_filter:
        last_seen = next(qid for qid in reversed(seen_order) if qid in seen_in_filter)
        pool.discard(last_seen)
    pick = (db.query(models.Question)
            .filter(models.Question.id.in_(list(pool)))
            .order_by(func.random()).first())
    return _practice_out(pick, total, total - 1, True)


# ----------------------------- 提交作答（触发判题） -----------------------------
@app.post("/api/answer", response_model=AnswerOut, summary="提交作答")
async def answer(payload: AnswerIn, db: Session = Depends(get_db)):
    q = db.query(models.Question).filter(models.Question.id == payload.question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")

    is_correct, explanation, error_reason, source = await judge(
        q.question_text, q.reference_answer, payload.user_answer
    )

    _persist_answer_result(
        db, q, payload.user_answer, is_correct, explanation, error_reason or "", source,
    )
    # 一次作答及其热力图/错题/复习副作用必须同事务落库，避免半成功状态。
    db.commit()

    return {"is_correct": is_correct, "explanation": explanation,
            "error_reason": error_reason or "", "source": source,
            "reference_answer": q.reference_answer or ""}


# ----------------------------- 智能组卷：一次性提交 -----------------------------
@app.post("/api/quiz/submit", response_model=QuizSubmitOut, summary="整卷一次性提交判题")
async def quiz_submit(payload: QuizSubmitIn, db: Session = Depends(get_db)):
    """智能组卷/模拟面试场景：把整卷题目 + 用户答案一次性提交，并发判题、串行写库。

    返回与提交顺序对齐的判题结果列表（含参考答案），前端用于整卷复盘展示。
    """
    import asyncio as _asyncio

    items = payload.items or []
    if not items:
        return {"results": []}
    if len(items) > MAX_QUIZ_ITEMS:
        raise HTTPException(
            status_code=422,
            detail=f"单次试卷最多提交 {MAX_QUIZ_ITEMS} 道题",
        )

    # 1) 一次性取出所有题目（避免 N 次单查）
    qids = [it.question_id for it in items]
    if len(set(qids)) != len(qids):
        raise HTTPException(status_code=422, detail="同一份试卷不能重复提交同一道题")
    qmap = {q.id: q for q in db.query(models.Question).filter(models.Question.id.in_(qids)).all()}

    # 2) 有上限地并发调判题（远端 LLM/Agent 为 IO 密集型，但不能把一次请求
    # 扩张成无限连接/限流压力）。
    judge_semaphore = _asyncio.Semaphore(MAX_CONCURRENT_JUDGES)

    async def _one(it):
        q = qmap.get(it.question_id)
        if not q:
            return (it, None, None, None, None)
        if not (it.user_answer or "").strip():
            return (it, q, None, None, None)
        async with judge_semaphore:
            is_correct, explanation, error_reason, source = await judge(
                q.question_text, q.reference_answer, it.user_answer
            )
        return (it, q, is_correct, (explanation, error_reason, source), None)

    judge_results = await _asyncio.gather(*[_one(it) for it in items], return_exceptions=True)

    # 3) 串行写库（SQLAlchemy session 不是 async-safe，串行避免锁竞争）
    out_results: List[QuizResultItem] = []
    for idx, res in enumerate(judge_results):
        # 判题阶段抛异常（一般是 judge() 内部问题） -> 标记为「待重试」，不阻断整卷
        if isinstance(res, Exception):
            it = items[idx]
            out_results.append(QuizResultItem(
                question_id=it.question_id, is_correct=None,
                explanation=f"判题异常：{type(res).__name__}: {str(res)[:200]}",
                error_reason="judge_exception", judge_by="pending",
                reference_answer="", user_answer=it.user_answer,
            ))
            continue
        (it, q, is_correct, judge_meta, _) = res
        if not q:
            # 题被删 / 不存在
            out_results.append(QuizResultItem(
                question_id=it.question_id, is_correct=None,
                explanation="题目不存在", error_reason="question_missing",
                judge_by="", reference_answer="", user_answer=it.user_answer,
            ))
            continue
        if judge_meta is None:
            # 空答案：跳过判题，但前端能看到「未作答」标记
            out_results.append(QuizResultItem(
                question_id=it.question_id, is_correct=None,
                explanation="未作答", error_reason="",
                judge_by="", reference_answer=q.reference_answer or "",
                user_answer=it.user_answer,
            ))
            continue

        explanation, error_reason, source = judge_meta

        _persist_answer_result(
            db, q, it.user_answer, is_correct, explanation, error_reason or "", source,
        )

        out_results.append(QuizResultItem(
            question_id=q.id, is_correct=is_correct,
            explanation=explanation or "", error_reason=error_reason or "",
            judge_by=source or "", reference_answer=q.reference_answer or "",
            user_answer=it.user_answer,
        ))

    db.commit()
    return {"results": out_results}


# ----------------------------- 热力图数据 -----------------------------
@app.get("/api/activity", summary="热力图数据")
def get_activity(db: Session = Depends(get_db)):
    rows = db.query(models.Activity).order_by(models.Activity.day).all()
    return [
        {"day": a.day.isoformat(), "answered": a.answered or 0,
         "correct": a.correct or 0, "wrong": a.wrong or 0}
        for a in rows
    ]


# ----------------------------- 错题本 -----------------------------
@app.get("/api/wrong-book", summary="错题本列表")
def get_wrong_book(
    category: str = "",
    only_reviewing: bool = False,
    error_reason: str = "",
    group_by_reason: bool = False,
    db: Session = Depends(get_db),
):
    """错题本列表；group_by_reason=true 时按错误原因聚类返回。"""
    query = db.query(models.WrongBook, models.Question).join(
        models.Question, models.WrongBook.question_id == models.Question.id
    )
    if category:
        query = query.filter(models.Question.category == category)
    if only_reviewing:
        query = query.filter(models.WrongBook.mastery != "mastered")
    if error_reason:
        query = query.filter(models.WrongBook.error_reason.contains(error_reason))

    if group_by_reason:
        rows = query.order_by(models.WrongBook.error_reason).all()
        groups = {}
        for wb, q in rows:
            key = wb.error_reason.strip() if wb.error_reason else "未归类"
            groups.setdefault(key, []).append({
                "question_id": q.id,
                "category": q.category,
                "platform": q.platform,
                "question_text": q.question_text,
                "reference_answer": q.reference_answer,
                "first_wrong_at": wb.first_wrong_at.isoformat() if wb.first_wrong_at else "",
                "wrong_count": wb.wrong_count,
                "last_user_answer": wb.last_user_answer,
                "mastery": wb.mastery,
                "error_reason": wb.error_reason,
            })
        return {"groups": [{"reason": k, "items": v} for k, v in groups.items()]}

    rows = query.order_by(models.WrongBook.wrong_count.desc()).all()
    result = []
    for wb, q in rows:
        result.append({
            "question_id": q.id,
            "category": q.category,
            "platform": q.platform,
            "question_text": q.question_text,
            "reference_answer": q.reference_answer,
            "first_wrong_at": wb.first_wrong_at.isoformat() if wb.first_wrong_at else "",
            "wrong_count": wb.wrong_count,
            "last_user_answer": wb.last_user_answer,
            "error_reason": wb.error_reason,
            "mastery": wb.mastery,
        })
    return result


@app.post("/api/wrong-book/{question_id}/master", summary="标记已掌握")
def mark_mastered(question_id: int, db: Session = Depends(get_db)):
    wb = db.query(models.WrongBook).filter(models.WrongBook.question_id == question_id).first()
    if not wb:
        raise HTTPException(status_code=404, detail="错题不存在")
    wb.mastery = "mastered"
    rs = db.query(models.ReviewSchedule).filter(models.ReviewSchedule.question_id == question_id).first()
    if rs:
        rs.status = "done"
        rs.stage = len(get_steps(get_settings(db).ebbinghaus_steps)) + 1
    db.commit()
    return {"status": "mastered"}


class PDF(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._font_path = self._find_font()
        if self._font_path:
            self.add_font("Custom", "", self._font_path)
            self.add_font("Custom", "B", self._font_path)
        self.set_margins(15, 15, 15)

    def _find_font(self):
        candidates = []
        if sys.platform == "win32":
            candidates = [
                r"C:\Windows\Fonts\simhei.ttf",
                r"C:\Windows\Fonts\simsun.ttc",
                r"C:\Windows\Fonts\msyh.ttc",
                r"C:\Windows\Fonts\msyhbd.ttc",
            ]
        elif sys.platform == "darwin":
            candidates = [
                "/System/Library/Fonts/STHeiti Medium.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
            ]
        else:
            candidates = [
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    def header(self):
        self.set_font("Custom", "B", 14)
        self.cell(0, 10, "错题本导出", new_x="LMARGIN", new_y="NEXT", align="C")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Custom", "", 9)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"第 {self.page_no()} 页", align="C")


@app.get("/api/wrong-book/export-pdf", summary="导出错题本 PDF")
def export_wrong_book_pdf(db: Session = Depends(get_db)):
    """导出当前错题本为 PDF。

    排版：每题一个分隔区块，题号 + 题目（蓝）+ 你的答案（红）+ 参考答案（黑）+
    错误原因（灰），题间画浅灰横线分页美观。
    """
    rows = db.query(models.WrongBook, models.Question).join(
        models.Question, models.WrongBook.question_id == models.Question.id
    ).order_by(models.WrongBook.wrong_count.desc(), models.WrongBook.id.desc()).all()

    pdf = PDF()
    if not pdf._font_path:
        raise HTTPException(status_code=500, detail="未找到可用的中文字体，请安装 simhei/simsun 字体")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(auto=False)  # 由我们手动控制分页，更稳
    pdf.add_page()

    w = pdf.w - pdf.l_margin - pdf.r_margin
    LINE_H = 7.5           # 行高（mm），10.5pt 中文舒适行高
    TITLE_H = 9            # 标题行高
    BLOCK_GAP = 4          # 区块间留白（mm）
    SEP_Y_OFFSET = 1.5     # 分隔线距上下区块的间距

    def ensure_space(need_mm: float):
        """剩余纵向空间不够时显式换页，避免 fpdf2 越界截断。"""
        if pdf.get_y() + need_mm > pdf.h - pdf.b_margin:
            pdf.add_page()

    def write_block(text: str, h: float = LINE_H):
        """安全写一段：用 multi_cell + 显式 new_x/new_y 自动归位，避免 write 后的 X/Y 漂移。
        multi_cell 已知在长文本时偶有越界，这里靠 ensure_space 提前换页兜底。
        """
        if not text:
            return
        ensure_space(h * 2)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(w, h, text, new_x="LMARGIN", new_y="NEXT", align="L")

    def draw_separator():
        """题间分隔线（浅灰 0.3pt）。"""
        y = pdf.get_y() + SEP_Y_OFFSET
        if y + SEP_Y_OFFSET + 1 > pdf.h - pdf.b_margin:
            return  # 接近页底就别画了，避免线落到新页
        pdf.set_draw_color(200, 200, 200)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, y, pdf.l_margin + w, y)
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.2)
        pdf.ln(BLOCK_GAP)

    for idx, (wb, q) in enumerate(rows, 1):
        # 标题行：第 N 题 · 分类 · 错误 X 次（深灰加粗）
        ensure_space(TITLE_H * 3)
        pdf.set_text_color(60, 60, 60)
        pdf.set_font("Custom", "B", 12)
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, TITLE_H, f"第 {idx} 题 · [{q.category}] · 错误 {wb.wrong_count} 次",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        # 题目（蓝色加粗）
        pdf.set_text_color(20, 60, 120)
        pdf.set_font("Custom", "B", 10.5)
        write_block("题目：" + (q.question_text or ""))

        # 你的答案（红色）
        pdf.set_text_color(180, 30, 30)
        pdf.set_font("Custom", "", 10.5)
        write_block("你的答案：" + (wb.last_user_answer or "（空）"))

        # 参考答案（黑色，10pt，避免太密）
        pdf.set_text_color(30, 30, 30)
        pdf.set_font("Custom", "", 10)
        write_block("参考答案：" + (q.reference_answer or "（暂无）"))

        # 错误原因（灰色小号）
        if wb.error_reason:
            pdf.set_text_color(120, 120, 120)
            pdf.set_font("Custom", "", 9.5)
            write_block("错误原因：" + wb.error_reason)

        # 还原默认样式 + 分隔线
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Custom", "", 10)
        draw_separator()

    out_path = os.path.join(BASE_DIR, "data", "wrong_book_export.pdf")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pdf.output(out_path)
    return {"download_url": "/data/wrong_book_export.pdf", "count": len(rows)}


@app.get("/api/wrong-book/export-md", summary="导出错题本 Markdown")
def export_wrong_book_md(
    category: str = "",
    only_reviewing: bool = False,
    group_by_reason: bool = False,
    db: Session = Depends(get_db),
):
    """导出当前错题本为 Markdown（含题目与参考答案），便于打印背诵。"""
    query = db.query(models.WrongBook, models.Question).join(
        models.Question, models.WrongBook.question_id == models.Question.id
    )
    if category:
        query = query.filter(models.Question.category == category)
    if only_reviewing:
        query = query.filter(models.WrongBook.mastery != "mastered")

    zh = {"mastered": "已掌握", "learning": "学习中", "reviewing": "复习中"}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = []

    if group_by_reason:
        rows = query.order_by(models.WrongBook.error_reason).all()
        groups: dict = {}
        for wb, q in rows:
            key = (wb.error_reason or "").strip() or "未归类"
            groups.setdefault(key, []).append((wb, q))
        lines = ["# 错题本导出（按错误原因分组）", "", f"> 共 {len(rows)} 题 · 导出时间 {now}", ""]
        for reason, items in groups.items():
            lines.append(f"## 错误原因：{reason}（{len(items)} 题）")
            lines.append("")
            for i, (wb, q) in enumerate(items, 1):
                lines += _md_item(i, q, wb, zh)
    else:
        rows = query.order_by(models.WrongBook.wrong_count.desc()).all()
        lines = ["# 错题本导出", "", f"> 共 {len(rows)} 题 · 导出时间 {now}", ""]
        for i, (wb, q) in enumerate(rows, 1):
            lines += _md_item(i, q, wb, zh)

    md = "\n".join(lines)
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=wrong_book_export.md"},
    )


def _md_item(idx: int, q, wb, zh: dict) -> list:
    out = [
        f"## {idx}. [{q.category}] {q.question_text}",
        "",
        f"- **错误次数**：{wb.wrong_count}",
        f"- **掌握状态**：{zh.get(wb.mastery, wb.mastery)}",
        f"- **你的答案**：{wb.last_user_answer or '（空）'}",
    ]
    if wb.error_reason:
        out.append(f"- **错误原因**：{wb.error_reason}")
    out += ["", "**参考答案：**", "", q.reference_answer or "（暂无参考答案）", "", "---", ""]
    return out


# ----------------------------- 待复习 & 复习反馈 -----------------------------
@app.get("/api/review/due", summary="待复习列表")
def get_due(db: Session = Depends(get_db)):
    due = db.query(models.ReviewSchedule).filter(
        models.ReviewSchedule.status == "pending",
        models.ReviewSchedule.next_review_at <= datetime.utcnow(),
    ).all()
    result = []
    for r in due:
        q = db.query(models.Question).filter(models.Question.id == r.question_id).first()
        wb = db.query(models.WrongBook).filter(models.WrongBook.question_id == r.question_id).first()
        if not q:
            continue
        result.append({
            "question_id": q.id,
            "category": q.category,
            "question_text": q.question_text,
            "reference_answer": q.reference_answer,
            "last_user_answer": wb.last_user_answer if wb else "",
            "wrong_count": wb.wrong_count if wb else 0,
        })
    return result


@app.post("/api/review/{question_id}", summary="复习反馈")
def review_feedback(question_id: int, payload: ReviewFeedback, db: Session = Depends(get_db)):
    rs = db.query(models.ReviewSchedule).filter(models.ReviewSchedule.question_id == question_id).first()
    if not rs:
        raise HTTPException(status_code=404, detail="无复习计划")
    steps = get_steps(get_settings(db).ebbinghaus_steps)

    rs.stage = advance_stage(rs.stage or 1, payload.remembered, steps)
    rs.review_count = (rs.review_count or 0) + 1
    rs.last_reviewed_at = datetime.utcnow()

    if is_mastered(rs.stage, steps):
        rs.status = "done"
        wb = db.query(models.WrongBook).filter(models.WrongBook.question_id == question_id).first()
        if wb:
            wb.mastery = "mastered"
    else:
        rs.status = "pending"
        rs.next_review_at = next_review_for_stage(rs.stage, steps, base=datetime.utcnow())
        wb = db.query(models.WrongBook).filter(models.WrongBook.question_id == question_id).first()
        if wb:
            wb.mastery = "reviewing"
    db.commit()
    return {"stage": rs.stage, "status": rs.status,
            "next_review_at": rs.next_review_at.isoformat() if rs.next_review_at else ""}


# ----------------------------- 设置 -----------------------------
@app.get("/api/settings", summary="读取设置")
def read_settings(db: Session = Depends(get_db)):
    s = get_settings(db)
    return {"email": s.email, "push_time": s.push_time,
            "ebbinghaus_steps": s.ebbinghaus_steps, "app_base_url": s.app_base_url}


@app.post("/api/settings", summary="更新设置")
def update_settings(payload: SettingsIn, db: Session = Depends(get_db)):
    # 先验证，再读取/创建 Settings 行；错误输入不会写入半截配置。
    push_time, steps = _validated_schedule_settings(payload)
    s = get_settings(db)
    s.email = payload.email
    s.push_time = push_time
    s.ebbinghaus_steps = steps
    s.app_base_url = (payload.app_base_url or DEFAULT_APP_BASE_URL).strip()
    db.commit()
    # 重启调度以应用新的推送时间
    try:
        scheduler.reschedule_job("daily_review", trigger="cron",
                                 hour=int(push_time.split(":")[0]),
                                 minute=int(push_time.split(":")[1]))
    except Exception:
        pass
    return {"status": "updated"}


# ----------------------------- 智能组卷 -----------------------------
@app.get("/api/quiz/generate", summary="智能组卷")
def quiz_generate(
    count: int = 10,
    category: str = "",
    company: str = "",
    mode: str = "weak",          # weak（薄弱优先）| mixed（混合）| random（纯随机）
    db: Session = Depends(get_db),
):
    """智能组卷：按薄弱点或目标公司生成一套题目。

    - mode=weak：优先从错题本（按错误次数降序）抽取，不足部分随机补足；
    - mode=mixed：一半薄弱题 + 一半随机；
    - mode=random：范围（分类/公司）内纯随机。
    company 命中 platform 字段（如「字节」「美团」）。
    返回题目列表（id/category/platform/tags/question_text）。
    """
    count = max(1, min(int(count), 100))
    base = db.query(models.Question)
    if category:
        base = base.filter(models.Question.category == category)
    if company:
        base = base.filter(models.Question.platform.ilike("%" + company + "%"))
    all_ids = [r[0] for r in base.with_entities(models.Question.id).all()]
    if not all_ids:
        raise HTTPException(status_code=404, detail="该范围内没有题目，换个分类或公司试试")

    weak_ids = []
    if mode in ("weak", "mixed"):
        wb = (
            db.query(models.WrongBook)
            .filter(models.WrongBook.question_id.in_(all_ids))
            .order_by(models.WrongBook.wrong_count.desc())
            .all()
        )
        weak_ids = [w.question_id for w in wb]

    if mode == "weak":
        pool = list(weak_ids)
        random.shuffle(pool)
        picked = pool[:count]
        rest = [i for i in all_ids if i not in set(picked)]
        random.shuffle(rest)
        picked += rest[: count - len(picked)]
    elif mode == "mixed":
        half = count // 2
        picked = list(weak_ids[:half])
        rest = [i for i in all_ids if i not in set(picked)]
        random.shuffle(rest)
        picked += rest[: count - len(picked)]
    else:  # random
        rest = list(all_ids)
        random.shuffle(rest)
        picked = rest[:count]

    # 去重且保留顺序
    seen = set()
    picked = [i for i in picked if not (i in seen or seen.add(i))]
    qs = db.query(models.Question).filter(models.Question.id.in_(picked)).all()
    qs.sort(key=lambda q: picked.index(q.id))
    return [
        {"id": q.id, "category": q.category, "platform": q.platform,
         "tags": q.tags, "question_text": q.question_text, "difficulty": q.difficulty}
        for q in qs
    ]


# ----------------------------- 社区面经 -----------------------------
@app.get("/api/experiences", response_model=List[InterviewExpOut], summary="面经列表")
def list_experiences(company: str = "", db: Session = Depends(get_db)):
    """面经列表（按时间倒序）；company 可模糊筛选。"""
    q = db.query(models.InterviewExp)
    if company:
        q = q.filter(models.InterviewExp.company.ilike("%" + company + "%"))
    rows = q.order_by(models.InterviewExp.created_at.desc()).all()
    return [
        {"id": e.id, "company": e.company, "role": e.role, "position": e.position,
         "offer_result": e.offer_result, "content": e.content, "questions": e.questions,
         "created_at": e.created_at.isoformat() if e.created_at else ""}
        for e in rows
    ]


@app.post("/api/experiences", response_model=InterviewExpOut, summary="添加面经")
def add_experience(payload: InterviewExpIn, db: Session = Depends(get_db)):
    """添加一条面经。"""
    if not payload.company or not payload.content:
        raise HTTPException(status_code=422, detail="公司和经历描述必填")
    e = models.InterviewExp(
        company=payload.company, role=payload.role, position=payload.position,
        offer_result=payload.offer_result, content=payload.content, questions=payload.questions,
        created_at=datetime.utcnow(),
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return {"id": e.id, "company": e.company, "role": e.role, "position": e.position,
            "offer_result": e.offer_result, "content": e.content, "questions": e.questions,
            "created_at": e.created_at.isoformat() if e.created_at else ""}


# ----------------------------- 管理后台 API（/admin） -----------------------------
# A. 题目管理：删除 / 导出 / 批量导入
@app.delete("/api/questions/{qid}", summary="删除题目")
def delete_question(qid: int, db: Session = Depends(get_db)):
    """删除题目并清理可级联数据；作答记录保留用于历史统计。"""
    q = db.query(models.Question).filter(models.Question.id == qid).first()
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    db.query(models.WrongBook).filter(models.WrongBook.question_id == qid).delete()
    db.query(models.ReviewSchedule).filter(models.ReviewSchedule.question_id == qid).delete()
    db.query(models.QuestionNote).filter(models.QuestionNote.question_id == qid).delete()
    db.delete(q)
    db.commit()
    return {"status": "deleted", "id": qid}


@app.get("/api/questions/export", summary="导出题目（JSON）")
def export_questions(
    keyword: str = "", category: str = "", difficulty: int = 0,
    tags: str = "", db: Session = Depends(get_db),
):
    """导出满足条件的题目为 JSON（供批量备份/迁移）。"""
    q = db.query(models.Question)
    if keyword:
        q = q.filter(
            models.Question.question_text.contains(keyword)
            | models.Question.reference_answer.contains(keyword)
        )
    if category:
        q = q.filter(models.Question.category == category)
    if difficulty:
        q = q.filter(models.Question.difficulty == difficulty)
    q = _tag_filter(q, tags)
    rows = q.order_by(models.Question.id).all()
    data = [{
        "platform": r.platform, "category": r.category, "tags": r.tags,
        "question_text": r.question_text, "reference_answer": r.reference_answer,
        "difficulty": r.difficulty,
    } for r in rows]
    body = json.dumps(data, ensure_ascii=False, indent=2)
    return Response(
        content=body, media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=questions_export.json"},
    )


class QuestionImportList(BaseModel):
    items: List[QuestionImport]


@app.post("/api/questions/import-json", summary="批量导入题目（JSON 数组）")
def import_questions_json(payload: QuestionImportList, db: Session = Depends(get_db)):
    """接收 {items:[{platform,category,tags,question_text,reference_answer,difficulty}]}，
    按题面去重后批量入库。"""
    imported = 0
    skipped = 0
    seen_titles = set()
    for item in payload.items:
        text = (item.question_text or "").strip()
        if not text:
            skipped += 1
            continue
        exists = db.query(models.Question).filter(
            models.Question.question_text == text).first()
        if exists or text in seen_titles:
            skipped += 1
            continue
        seen_titles.add(text)
        db.add(models.Question(
            platform=item.platform, category=item.category, tags=item.tags,
            question_text=text, reference_answer=item.reference_answer,
            difficulty=item.difficulty,
            created_at=datetime.utcnow(),
        ))
        imported += 1
    db.commit()
    return {"imported": imported, "skipped": skipped, "total": len(payload.items)}


# B. 分类管理：元数据 + 重命名 / 合并 / 删除
def _category_meta_map(db: Session) -> dict:
    """name -> {icon, description}，来自 category_meta 表（覆盖默认值）。"""
    return {m.name: {"icon": m.icon, "description": m.description}
            for m in db.query(models.CategoryMeta).all()}


@app.get("/api/categories/meta", summary="分类元数据列表（含题数）")
def list_category_meta(db: Session = Depends(get_db)):
    """合并 questions 实际分类 与 category_meta 预置分类，返回 {name, icon, description, count}。"""
    counts = dict(
        db.query(models.Question.category, func.count(models.Question.id))
        .group_by(models.Question.category).all()
    )
    meta = _category_meta_map(db)
    names = set(counts.keys()) | set(meta.keys())
    out = []
    for name in names:
        nm = name or "未分类"
        m = meta.get(name, {})
        out.append({
            "name": nm,
            "count": counts.get(name, 0),
            "icon": m.get("icon") or _category_icon(name),
            "description": m.get("description") or _category_description(name),
        })
    return sorted(out, key=lambda x: (-x["count"], x["name"]))


@app.post("/api/categories/meta", summary="新增/更新分类元数据")
def upsert_category_meta(payload: dict, db: Session = Depends(get_db)):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="分类名必填")
    m = db.query(models.CategoryMeta).filter(models.CategoryMeta.name == name).first()
    if not m:
        m = models.CategoryMeta(name=name)
        db.add(m)
    if "icon" in payload:
        m.icon = payload.get("icon") or ""
    if "description" in payload:
        m.description = payload.get("description") or ""
    db.commit()
    db.refresh(m)
    return {"status": "ok", "name": m.name, "icon": m.icon, "description": m.description}


@app.put("/api/categories/meta/{name}", summary="更新分类图标/描述")
def update_category_meta(name: str, payload: dict, db: Session = Depends(get_db)):
    m = db.query(models.CategoryMeta).filter(models.CategoryMeta.name == name).first()
    if not m:
        m = models.CategoryMeta(name=name)
        db.add(m)
    if "icon" in payload:
        m.icon = payload.get("icon") or ""
    if "description" in payload:
        m.description = payload.get("description") or ""
    db.commit()
    db.refresh(m)
    return {"status": "ok", "name": m.name, "icon": m.icon, "description": m.description}


@app.post("/api/categories/rename", summary="重命名分类")
def rename_category(payload: dict, db: Session = Depends(get_db)):
    old = (payload.get("old_name") or "").strip()
    new = (payload.get("new_name") or "").strip()
    if not old or not new:
        raise HTTPException(status_code=422, detail="old_name 与 new_name 均必填")
    db.query(models.Question).filter(models.Question.category == old).update(
        {models.Question.category: new})
    m = db.query(models.CategoryMeta).filter(models.CategoryMeta.name == old).first()
    if m:
        m.name = new
    db.commit()
    return {"status": "renamed", "old": old, "new": new}


@app.post("/api/categories/merge", summary="合并分类")
def merge_category(payload: dict, db: Session = Depends(get_db)):
    frm = (payload.get("from_name") or "").strip()
    to = (payload.get("to_name") or "").strip()
    if not frm or not to:
        raise HTTPException(status_code=422, detail="from_name 与 to_name 均必填")
    if frm == to:
        raise HTTPException(status_code=400, detail="源与目标不能相同")
    db.query(models.Question).filter(models.Question.category == frm).update(
        {models.Question.category: to})
    fm = db.query(models.CategoryMeta).filter(models.CategoryMeta.name == frm).first()
    if fm:
        tm = db.query(models.CategoryMeta).filter(models.CategoryMeta.name == to).first()
        if not tm:
            fm.name = to
        else:
            db.delete(fm)
    db.commit()
    return {"status": "merged", "from": frm, "to": to}


@app.delete("/api/categories/{name}", summary="删除分类（题目迁移到目标分类）")
def delete_category(name: str, target: str = "", db: Session = Depends(get_db)):
    """删除分类：名下题目迁移到 target（默认空串=未分类），并删除其元数据。"""
    tgt = (target or "").strip()
    if tgt == name:
        raise HTTPException(status_code=400, detail="目标分类不能与待删除分类相同")
    db.query(models.Question).filter(models.Question.category == name).update(
        {models.Question.category: tgt})
    db.query(models.CategoryMeta).filter(models.CategoryMeta.name == name).delete()
    db.commit()
    return {"status": "deleted", "name": name, "target": tgt}


# C. 面经管理 & 数据概览
@app.delete("/api/experiences/{eid}", summary="删除面经")
def delete_experience(eid: int, db: Session = Depends(get_db)):
    e = db.query(models.InterviewExp).filter(models.InterviewExp.id == eid).first()
    if not e:
        raise HTTPException(status_code=404, detail="面经不存在")
    db.delete(e)
    db.commit()
    return {"status": "deleted", "id": eid}


@app.get("/api/admin/stats", summary="管理后台统计数据")
def admin_stats(db: Session = Depends(get_db)):
    total_questions = db.query(models.Question).count()
    total_categories = db.query(models.Question.category).distinct().count()
    total_experiences = db.query(models.InterviewExp).count()
    total_submissions = db.query(models.Submission).count()
    correct = db.query(models.Submission).filter(models.Submission.is_correct == True).count()
    wrong = db.query(models.Submission).filter(models.Submission.is_correct == False).count()
    accuracy = round(correct / total_submissions * 100, 1) if total_submissions else 0.0
    wrong_book_count = db.query(models.WrongBook).count()
    review_due = db.query(models.ReviewSchedule).filter(
        models.ReviewSchedule.status == "pending",
        models.ReviewSchedule.next_review_at <= datetime.utcnow(),
    ).count()
    since = date.today() - timedelta(days=29)
    acts = db.query(models.Activity).filter(models.Activity.day >= since).all()
    activity = [{"day": a.day.isoformat(), "answered": a.answered,
                 "correct": a.correct, "wrong": a.wrong} for a in acts]
    by_category = [
        {"name": r[0] or "未分类", "count": r[1]}
        for r in db.query(models.Question.category, func.count(models.Question.id))
        .group_by(models.Question.category)
        .order_by(func.count(models.Question.id).desc()).all()
    ]
    return {
        "total_questions": total_questions,
        "total_categories": total_categories,
        "total_experiences": total_experiences,
        "total_submissions": total_submissions,
        "correct_submissions": correct,
        "wrong_submissions": wrong,
        "accuracy": accuracy,
        "wrong_book_count": wrong_book_count,
        "review_due_count": review_due,
        "activity": activity,
        "by_category": by_category,
    }


# D. 成长中心（连续天数 / 成就徽章 / 学习报告 / 本月目标）
# 全部由现有表实时聚合，不引入冗余写入；仅 GrowthGoal 存储「本月目标题数」。
def _active_days(db):
    """返回有作答（answered>0）的日期集合，用于连续天数与成就计算。"""
    return {a.day for a in db.query(models.Activity).filter(models.Activity.answered > 0).all()}


def _compute_streak(active):
    """返回 (当前连胜, 最长连胜)。当天未作答但昨天有，则连胜仍计到昨天（可今日补卡）。"""
    if not active:
        return 0, 0
    days = sorted(active)
    longest = cur = 1
    for i in range(1, len(days)):
        if (days[i] - days[i - 1]).days == 1:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 1
    longest = max(longest, cur)
    today = date.today()
    if today in active:
        anchor = today
    elif (today - timedelta(days=1)) in active:
        anchor = today - timedelta(days=1)
    else:
        return 0, longest
    streak = 0
    d = anchor
    while d in active:
        streak += 1
        d -= timedelta(days=1)
    return streak, longest


def _range_stats(db, start, end):
    """聚合某日期区间内的作答量（来自 activity 表）。"""
    rows = db.query(
        func.sum(models.Activity.answered),
        func.sum(models.Activity.correct),
        func.sum(models.Activity.wrong),
    ).filter(models.Activity.day >= start, models.Activity.day <= end).first()
    a = int(rows[0] or 0)
    c = int(rows[1] or 0)
    w = int(rows[2] or 0)
    return {
        "answered": a,
        "correct": c,
        "wrong": w,
        "accuracy": round(c / a * 100, 1) if a else 0.0,
    }


def _focus_minutes(db, start_dt, end_dt):
    v = db.query(func.sum(models.FocusSession.actual_minutes)).filter(
        models.FocusSession.completed == True,
        models.FocusSession.started_at >= start_dt,
        models.FocusSession.started_at <= end_dt,
    ).scalar()
    return int(v or 0)


class GrowthGoalSet(BaseModel):
    target: int = 100


@app.get("/api/growth/summary", summary="成长中心概览（连续天数/成就/报告）")
def growth_summary(db: Session = Depends(get_db)):
    today = date.today()
    active = _active_days(db)
    streak, longest = _compute_streak(active)

    total_subs = db.query(models.Submission).count()
    correct = db.query(models.Submission).filter(models.Submission.is_correct == True).count()
    cats_done = db.query(models.Question.category).join(
        models.Submission, models.Submission.question_id == models.Question.id
    ).filter(models.Question.category != "").distinct().count()
    cats_total = db.query(models.Question.category).filter(
        models.Question.category != "").distinct().count()
    reviews = int(db.query(func.sum(models.ReviewSchedule.review_count)).scalar() or 0)
    focus_done = db.query(models.FocusSession).filter(models.FocusSession.completed == True).count()
    focus_min = int(db.query(func.sum(models.FocusSession.actual_minutes)).filter(
        models.FocusSession.completed == True).scalar() or 0)
    exp = db.query(models.InterviewExp).count()
    wrong_book = db.query(models.WrongBook).count()

    # 本月目标与进度
    cur_month = today.strftime("%Y-%m")
    goal_row = db.query(models.GrowthGoal).filter(models.GrowthGoal.month == cur_month).first()
    goal = goal_row.target if goal_row else 100
    month_start = today.replace(day=1)
    month_stats = _range_stats(db, month_start, today)
    month_answered = month_stats["answered"]

    ctx = dict(streak=streak, correct=correct, cats_done=cats_done, cats_total=cats_total,
               reviews=reviews, focus_done=focus_done, focus_min=focus_min, exp=exp,
               total_subs=total_subs, goal=goal, month_answered=month_answered)

    def badge(bid, name, icon, desc, unlocked, progress, target):
        return {"id": bid, "name": name, "icon": icon, "desc": desc,
                "unlocked": bool(unlocked), "progress": int(min(progress, target)),
                "target": int(target)}

    badges = [
        badge("first_step", "初心者", "🌱", "完成第一次作答", total_subs >= 1, total_subs, 1),
        badge("streak_7", "七日筑基", "🔥", "连续学习 7 天", streak >= 7, streak, 7),
        badge("streak_30", "月半如锋", "⚔️", "连续学习 30 天", streak >= 30, streak, 30),
        badge("streak_100", "百日磨剑", "🗡️", "连续学习 100 天", streak >= 100, streak, 100),
        badge("hundred", "百题斩", "💯", "累计答对 100 题", correct >= 100, correct, 100),
        badge("thousand", "千题斩", "🏆", "累计答对 1000 题", correct >= 1000, correct, 1000),
        badge("all_cats", "全分类通关", "🧭", "每个分类都练过",
              cats_total > 0 and cats_done >= cats_total, cats_done, max(cats_total, 1)),
        badge("reviewer", "复习大师", "🔁", "完成 100 次复习", reviews >= 100, reviews, 100),
        badge("focus50", "番茄达人", "🍅", "完成 50 个番茄", focus_done >= 50, focus_done, 50),
        badge("focus10h", "专注十时", "⏳", "累计专注 600 分钟", focus_min >= 600, focus_min, 600),
        badge("exp_sharer", "面经贡献", "📝", "分享 1 篇面经", exp >= 1, exp, 1),
        badge("goal_keeper", "目标达成", "🎯", "本月达成目标题数",
              goal > 0 and month_answered >= goal, month_answered, max(goal, 1)),
    ]

    # 报告：本周 / 本月
    monday = today - timedelta(days=today.weekday())
    week_start_dt = datetime(monday.year, monday.month, monday.day)
    month_start_dt = datetime(month_start.year, month_start.month, month_start.day)
    end_dt = datetime(today.year, today.month, today.day, 23, 59, 59)
    week = _range_stats(db, monday, today)
    week["focus_minutes"] = _focus_minutes(db, week_start_dt, end_dt)
    month = month_stats
    month["focus_minutes"] = _focus_minutes(db, month_start_dt, end_dt)

    return {
        "streak": streak,
        "longest_streak": longest,
        "total_submissions": total_subs,
        "correct": correct,
        "wrong_book": wrong_book,
        "focus_minutes_total": focus_min,
        "badges": badges,
        "badges_unlocked": sum(1 for b in badges if b["unlocked"]),
        "badges_total": len(badges),
        "report": {"week": week, "month": month},
        "goal": {"month": cur_month, "target": goal, "current": month_answered,
                 "percent": round(month_answered / goal * 100, 1) if goal else 0.0},
    }


@app.get("/api/growth/goal", summary="本月目标题数")
def get_growth_goal(db: Session = Depends(get_db)):
    cur_month = date.today().strftime("%Y-%m")
    g = db.query(models.GrowthGoal).filter(models.GrowthGoal.month == cur_month).first()
    return {"month": cur_month, "target": g.target if g else 100}


@app.put("/api/growth/goal", summary="设置本月目标题数")
def set_growth_goal(payload: GrowthGoalSet, db: Session = Depends(get_db)):
    cur_month = date.today().strftime("%Y-%m")
    target = max(int(payload.target), 1)
    g = db.query(models.GrowthGoal).filter(models.GrowthGoal.month == cur_month).first()
    if g:
        g.target = target
    else:
        g = models.GrowthGoal(month=cur_month, target=target)
        db.add(g)
    db.commit()
    return {"month": cur_month, "target": target}


# ----------------------------- 静态文件 & 前端 -----------------------------
ADMIN_HTML = os.path.join(FRONTEND_DIR, "admin", "index.html")
if os.path.isfile(ADMIN_HTML):
    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/", include_in_schema=False)
    def admin_page():
        return FileResponse(ADMIN_HTML)


# 技术文章摘抄（lianglianglee 静态站）单服务融合：挂载在 /articles/，配合上面的路径重写中间件。
# 必须注册在 "/" 兜底挂载之前，否则会被 SPA 的 "/" 挂载抢走。
# 注意：StaticFiles 不会把 /articles 自动重定向到 /articles/，故显式补 307，避免前端 iframe(src=/articles) 404。
@app.get("/api/articles/status", summary="技术文章资源状态")
def articles_status():
    """供前端决定是否显示文章 iframe；资源不是镜像/仓库的必需内容。"""
    return {
        "available": ARTICLES_AVAILABLE,
        "message": "" if ARTICLES_AVAILABLE else ARTICLES_UNAVAILABLE_MESSAGE,
    }


@app.get("/articles", include_in_schema=False)
def _articles_root():
    if not ARTICLES_AVAILABLE:
        raise HTTPException(status_code=404, detail=ARTICLES_UNAVAILABLE_MESSAGE)
    return RedirectResponse(url="/articles/", status_code=307)

if ARTICLES_AVAILABLE:
    app.mount(ARTICLES_PREFIX, StaticFiles(directory=ARTICLES_BOOK_DIR, html=True), name="articles")
else:
    @app.get("/articles/{article_path:path}", include_in_schema=False)
    def _articles_unavailable(article_path: str):
        raise HTTPException(status_code=404, detail=ARTICLES_UNAVAILABLE_MESSAGE)

# 番茄待办 API（待办清单 + 番茄钟 + 专注统计）；必须注册在 "/" 兜底挂载之前。
# ----------------------------- 番茄待办：分类 / 完成记录 / 专注统计 -----------------------------
class PomodoroCompleteIn(BaseModel):
    todo_id: Optional[int] = None
    kind: str = "focus"          # focus | break
    minutes: int = 25
    completed: bool = True


@app.get("/api/todo/categories", summary="待办分类列表（含计数）")
def todo_categories(db: Session = Depends(get_db)):
    rows = (
        db.query(models.Todo.category, func.count(models.Todo.id))
        .filter(models.Todo.deleted == False, models.Todo.category != None, models.Todo.category != "")
        .group_by(models.Todo.category)
        .order_by(func.count(models.Todo.id).desc())
        .all()
    )
    return [{"name": c, "count": n} for c, n in rows]


@app.post("/api/pomodoro/complete", summary="记录一个完成的番茄 / 休息")
def pomodoro_complete(p: PomodoroCompleteIn, db: Session = Depends(get_db)):
    # 用本地时间（与 growth_summary 的本地日期边界一致），修复跨时区统计偏差
    now = datetime.now()
    mins = max(0, int(p.minutes))
    fs = models.FocusSession(
        todo_id=p.todo_id,
        kind=p.kind,
        minutes=mins,
        started_at=now - timedelta(minutes=mins),
        ended_at=now,
        actual_minutes=mins,
        completed=bool(p.completed),
    )
    db.add(fs)
    db.commit()
    db.refresh(fs)
    return {"id": fs.id, "kind": fs.kind, "minutes": fs.actual_minutes, "completed": fs.completed}


def _day_minutes_map(db, start_dt, end_dt):
    """区间内已完成专注按「本地日期」聚合为 {YYYY-MM-DD: 分钟数}（DB 无关，便于跨库）。"""
    rows = (
        db.query(models.FocusSession.started_at, models.FocusSession.actual_minutes)
        .filter(
            models.FocusSession.completed == True,
            models.FocusSession.started_at >= start_dt,
            models.FocusSession.started_at <= end_dt,
        )
        .all()
    )
    m = {}
    for st, mins in rows:
        if not st:
            continue
        key = st.date().isoformat()
        m[key] = m.get(key, 0) + int(mins or 0)
    return m


@app.get("/api/pomodoro/stats", summary="专注统计：今日/周/月分钟 + 今日番茄数 + 热力图 + 周纵览")
def pomodoro_stats(db: Session = Depends(get_db)):
    today = date.today()
    now = datetime.now()

    today_start = datetime(today.year, today.month, today.day)
    today_minutes = _focus_minutes(db, today_start, now)
    today_count = (
        db.query(models.FocusSession)
        .filter(
            models.FocusSession.completed == True,
            models.FocusSession.kind == "focus",
            models.FocusSession.started_at >= today_start,
            models.FocusSession.started_at <= now,
        )
        .count()
    )

    monday = today - timedelta(days=today.weekday())
    week_start = datetime(monday.year, monday.month, monday.day)
    week_minutes = _focus_minutes(db, week_start, now)

    month_start = datetime(today.year, today.month, 1)
    month_minutes = _focus_minutes(db, month_start, now)

    # 热力图：17 周 × 7 天，列优先（周→天），最右列为本周
    start_monday = monday - timedelta(weeks=16)
    day_map = _day_minutes_map(
        db, datetime(start_monday.year, start_monday.month, start_monday.day), now
    )
    heatmap = []
    for i in range(17 * 7):
        d = start_monday + timedelta(days=i)
        heatmap.append({"day": d.isoformat(), "minutes": day_map.get(d.isoformat(), 0)})

    # 本周纵览（周一~周日）
    week_overview = []
    for i in range(7):
        d = monday + timedelta(days=i)
        week_overview.append({"minutes": day_map.get(d.isoformat(), 0)})

    return {
        "today": {"minutes": today_minutes, "count": today_count},
        "week": {"minutes": week_minutes},
        "month": {"minutes": month_minutes},
        "heatmap": heatmap,
        "week_overview": week_overview,
    }


app.include_router(todo_router)

# ==================== 个人笔记（一题多条，单人系统） ====================
def _note_to_out(n):
    return NoteOut(
        id=n.id, question_id=n.question_id, content=n.content,
        created_at=n.created_at.isoformat() if n.created_at else None,
        updated_at=n.updated_at.isoformat() if n.updated_at else None,
    )


@app.get("/api/questions/{qid}/notes", response_model=List[NoteOut], summary="列出某题所有笔记（按时间倒序）")
def list_notes(qid: int, db: Session = Depends(get_db)):
    if not db.query(models.Question.id).filter(models.Question.id == qid).first():
        raise HTTPException(status_code=404, detail="题目不存在")
    rows = (db.query(models.QuestionNote)
              .filter(models.QuestionNote.question_id == qid)
              .order_by(models.QuestionNote.created_at.desc(),
                        models.QuestionNote.id.desc())
              .all())
    return [_note_to_out(r) for r in rows]


@app.post("/api/questions/{qid}/notes", response_model=NoteOut, summary="新增一条笔记")
def create_note(qid: int, payload: NoteIn, db: Session = Depends(get_db)):
    if not db.query(models.Question).filter(models.Question.id == qid).first():
        raise HTTPException(status_code=404, detail="题目不存在")
    n = models.QuestionNote(question_id=qid, content=payload.content)
    db.add(n)
    db.commit()
    db.refresh(n)
    return _note_to_out(n)


@app.put("/api/questions/{qid}/notes/{note_id}", response_model=NoteOut, summary="更新一条笔记")
def update_note(qid: int, note_id: int, payload: NoteIn, db: Session = Depends(get_db)):
    n = (db.query(models.QuestionNote)
           .filter(models.QuestionNote.id == note_id,
                   models.QuestionNote.question_id == qid)
           .first())
    if not n:
        raise HTTPException(status_code=404, detail="笔记不存在")
    n.content = payload.content
    db.commit()
    db.refresh(n)
    return _note_to_out(n)


@app.delete("/api/questions/{qid}/notes/{note_id}", summary="删除一条笔记")
def delete_note(qid: int, note_id: int, db: Session = Depends(get_db)):
    n = (db.query(models.QuestionNote)
           .filter(models.QuestionNote.id == note_id,
                   models.QuestionNote.question_id == qid)
           .first())
    if not n:
        raise HTTPException(status_code=404, detail="笔记不存在")
    db.delete(n)
    db.commit()
    return {"ok": True}


# 静态资源：按需暴露子目录，严禁把整个 data/ 挂成静态文件（否则 SQLite 库、WAL、备份可被 HTTP 下载）。
#   - 上传图片：/data/images/<file>
#   - 错题本导出 PDF：/data/wrong_book_export.pdf（显式路由，不暴露其它文件）
IMAGES_DIR = os.path.join(BASE_DIR, "data", "images")
# 启动时保证目录和路由都存在：首次上传前访问图片 URL 不应因为 mount 缺失而被
# SPA 根路由吞掉。只暴露这一子目录，绝不暴露整个 data/。
os.makedirs(IMAGES_DIR, exist_ok=True)
app.mount("/data/images", StaticFiles(directory=IMAGES_DIR), name="images")

@app.get("/data/wrong_book_export.pdf", include_in_schema=False)
def wrong_book_pdf():
    pdf_path = os.path.join(BASE_DIR, "data", "wrong_book_export.pdf")
    if not os.path.isfile(pdf_path):
        raise HTTPException(status_code=404, detail="尚未生成错题本导出")
    return FileResponse(pdf_path, filename="wrong_book_export.pdf")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
