"""数据库引擎、会话与声明基类。

- 默认 SQLite（data/interview_memory.db），零运维、clone 即跑；
- 生产可切 PostgreSQL/MySQL：设置环境变量 DATABASE_URL 即可（SQLAlchemy 兼容，表结构无需改动）。

SQLite 需要额外照顾两件事：自定义数据库文件的父目录未必已存在，以及
Web 请求的并发写入会比命令行脚本更容易撞到锁。这里统一处理目录、WAL 和
busy timeout，避免把这些环境差异散落到各个接口里。
"""
import os
from collections import defaultdict
from urllib.parse import unquote

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "interview_memory.db")

# SQLite 默认；DATABASE_URL 存在则优先（支持 postgresql+psycopg2:// / mysql+pymysql://）
DATABASE_URL = os.getenv("DATABASE_URL") or ("sqlite:///" + _DEFAULT_DB_PATH.replace(os.sep, "/"))


def _sqlite_file_path(database_url: str):
    """返回 SQLite 文件库的绝对路径；内存库/非 SQLite 返回 ``None``。

    SQLAlchemy 接受 ``sqlite:///relative.db``、``sqlite:////absolute.db`` 以及
    ``file:`` URI。不能只靠字符串拼接，否则自定义 URL 会错误地创建默认 data
    目录，或意外影响 ``:memory:`` 测试库。
    """
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return None
    database = url.database
    if not database or database == ":memory:" or str(url.query.get("mode", "")).lower() == "memory":
        return None

    database = unquote(database)
    if database.startswith("file:"):
        path, _, query = database[5:].partition("?")
        if "mode=memory" in query or path == ":memory:":
            return None
        database = path
    return os.path.abspath(database)


_SQLITE_FILE_PATH = _sqlite_file_path(DATABASE_URL)
if _SQLITE_FILE_PATH:
    # ``exist_ok`` 让多 worker 同时启动也安全；只创建数据库所在的精确父目录。
    os.makedirs(os.path.dirname(_SQLITE_FILE_PATH), exist_ok=True)

_connect_args = {}
if make_url(DATABASE_URL).get_backend_name() == "sqlite":
    # SQLite 单文件 + 允许跨线程访问（FastAPI 依赖在请求线程中解析）。
    _connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True, pool_pre_ping=True)


if make_url(DATABASE_URL).get_backend_name() == "sqlite":
    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, _connection_record):
        """为每条 SQLite 连接设置锁等待；文件库额外启用 WAL。"""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=30000")
            # ``:memory:`` 不支持/不需要 WAL，避免测试库行为被意外改变。
            if _SQLITE_FILE_PATH:
                cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def _column_names(table_name: str) -> set[str]:
    """从当前 engine 实际连接的数据库读取列名，而非猜测默认 SQLite 路径。"""
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _ensure_keywords_column():
    """给旧 ``questions`` 表补 ``keywords`` 列。

    ``create_all`` 不会给已有表增加列。迁移必须针对当前 engine 运行，并让未知
    错误显式冒出；否则配置错误会悄悄导致接口与模型不一致。
    """
    if "keywords" in _column_names("questions"):
        return

    dialect = engine.dialect.name
    if dialect == "mysql":
        # 旧 MySQL 对 TEXT DEFAULT 的支持不一致；VARCHAR 足以承载关键词。
        ddl = "ALTER TABLE questions ADD COLUMN keywords VARCHAR(4096) DEFAULT ''"
    else:
        ddl = "ALTER TABLE questions ADD COLUMN keywords TEXT DEFAULT ''"

    try:
        with engine.begin() as connection:
            connection.execute(text(ddl))
    except OperationalError:
        # 多 worker 首次启动时，另一个进程可能已经完成了同一迁移。仅这种已完成
        # 情况可忽略；其余错误继续抛出，避免吞掉真实 schema 故障。
        if "keywords" not in _column_names("questions"):
            raise


def _has_unique_question_index(table_name: str) -> bool:
    """当前数据库是否已有覆盖 ``question_id`` 的单列唯一约束或索引。"""
    inspector = inspect(engine)
    for constraint in inspector.get_unique_constraints(table_name):
        if constraint.get("column_names") == ["question_id"]:
            return True
    for index in inspector.get_indexes(table_name):
        if index.get("unique") and index.get("column_names") == ["question_id"]:
            return True
    return False


def _as_count(value, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _dedupe_wrong_book(connection):
    """合并历史并发写入留下的同题错题本行，再建立唯一索引。"""
    rows = connection.execute(text(
        "SELECT id, question_id, first_wrong_at, wrong_count, last_user_answer, "
        "error_reason, mastery, updated_at FROM wrong_book "
        "WHERE question_id IS NOT NULL ORDER BY question_id, id"
    )).mappings().all()
    groups = defaultdict(list)
    for row in rows:
        groups[row["question_id"]].append(row)

    for question_id, group in groups.items():
        if len(group) < 2:
            continue
        # 保留最早 id，聚合次数/最早错题时间；状态保守地保留为待复习，避免已掌握
        # 的旧行把新近答错覆盖掉。文本取时间最新且非空的一条。
        keep = min(group, key=lambda item: item["id"])
        latest = sorted(
            group,
            key=lambda item: (str(item["updated_at"] or item["first_wrong_at"] or ""), item["id"]),
            reverse=True,
        )
        first_wrong_at = min(
            (item["first_wrong_at"] for item in group if item["first_wrong_at"] is not None),
            default=None,
        )
        last_user_answer = next(
            (item["last_user_answer"] for item in latest if item["last_user_answer"]),
            keep["last_user_answer"],
        )
        error_reason = next(
            (item["error_reason"] for item in latest if item["error_reason"]),
            keep["error_reason"],
        )
        updated_at = next(
            (item["updated_at"] for item in latest if item["updated_at"] is not None),
            keep["updated_at"],
        )
        mastery = (
            "reviewing"
            if any(item["mastery"] != "mastered" for item in group)
            else "mastered"
        )
        connection.execute(text(
            "UPDATE wrong_book SET first_wrong_at=:first_wrong_at, wrong_count=:wrong_count, "
            "last_user_answer=:last_user_answer, error_reason=:error_reason, mastery=:mastery, "
            "updated_at=:updated_at WHERE id=:id"
        ), {
            "id": keep["id"],
            "first_wrong_at": first_wrong_at,
            # NULL 在历史表中表示至少已有一次答错，不能把它当 0 丢失。
            "wrong_count": sum(_as_count(item["wrong_count"], default=1) for item in group),
            "last_user_answer": last_user_answer,
            "error_reason": error_reason,
            "mastery": mastery,
            "updated_at": updated_at,
        })
        for item in group:
            if item["id"] != keep["id"]:
                connection.execute(text("DELETE FROM wrong_book WHERE id=:id"), {"id": item["id"]})


def _dedupe_review_schedule(connection):
    """合并历史并发写入留下的同题复习计划行，再建立唯一索引。"""
    rows = connection.execute(text(
        "SELECT id, question_id, stage, next_review_at, last_reviewed_at, review_count, status "
        "FROM review_schedule WHERE question_id IS NOT NULL ORDER BY question_id, id"
    )).mappings().all()
    groups = defaultdict(list)
    for row in rows:
        groups[row["question_id"]].append(row)

    for question_id, group in groups.items():
        if len(group) < 2:
            continue
        keep = min(group, key=lambda item: item["id"])
        stages = [_as_count(item["stage"], default=1) or 1 for item in group]
        next_review_at = min(
            (item["next_review_at"] for item in group if item["next_review_at"] is not None),
            default=None,
        )
        last_reviewed_at = max(
            (item["last_reviewed_at"] for item in group if item["last_reviewed_at"] is not None),
            default=None,
        )
        # 任一 pending 就继续保留复习，避免合并时无意取消待复习任务。
        status = "pending" if any(item["status"] != "done" for item in group) else "done"
        connection.execute(text(
            "UPDATE review_schedule SET stage=:stage, next_review_at=:next_review_at, "
            "last_reviewed_at=:last_reviewed_at, review_count=:review_count, status=:status "
            "WHERE id=:id"
        ), {
            "id": keep["id"],
            "stage": min(stages),
            "next_review_at": next_review_at,
            "last_reviewed_at": last_reviewed_at,
            "review_count": max(_as_count(item["review_count"]) for item in group),
            "status": status,
        })
        for item in group:
            if item["id"] != keep["id"]:
                connection.execute(text("DELETE FROM review_schedule WHERE id=:id"), {"id": item["id"]})


def _ensure_question_uniqueness():
    """兼容已有数据库：先合并重复行，再创建跨后端唯一索引。

    ``create_all`` 不会把新模型上的 ``UniqueConstraint`` 回填到已存在的
    SQLite/PostgreSQL/MySQL 表。这里使用检查后的唯一索引补齐该约束；若并发
    启动时其他进程先完成迁移，仅在确认索引已存在时吞掉对应 DDL 异常。
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not {"wrong_book", "review_schedule"}.issubset(tables):
        return

    with engine.begin() as connection:
        _dedupe_wrong_book(connection)
        _dedupe_review_schedule(connection)
        for table_name in ("wrong_book", "review_schedule"):
            if _has_unique_question_index(table_name):
                continue
            index_name = f"uq_{table_name}_question_id"
            if engine.dialect.name in {"sqlite", "postgresql"}:
                ddl = f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table_name} (question_id)"
            else:
                # MySQL's support for ``IF NOT EXISTS`` on CREATE INDEX varies
                # by version; the pre-check plus post-error verification below
                # keeps the migration portable.
                ddl = f"CREATE UNIQUE INDEX {index_name} ON {table_name} (question_id)"
            try:
                connection.execute(text(ddl))
            except SQLAlchemyError:
                if not _has_unique_question_index(table_name):
                    raise


def init_db():
    """创建所有表（幂等）。必须在导入 models 后调用，确保表已注册到 Base.metadata。"""
    from . import models  # noqa: F401  (确保表类已注册到元数据)
    Base.metadata.create_all(bind=engine)
    _ensure_keywords_column()
    _ensure_question_uniqueness()


def get_db():
    """FastAPI 依赖：每个请求一个 Session，请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
