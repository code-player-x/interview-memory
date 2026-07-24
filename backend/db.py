"""数据库引擎、会话与声明基类。

- 默认 SQLite（data/interview_memory.db），零运维、clone 即跑；
- 生产可切 PostgreSQL/MySQL：设置环境变量 DATABASE_URL 即可（SQLAlchemy 兼容，表结构无需改动）。
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "interview_memory.db")

# SQLite 默认；DATABASE_URL 存在则优先（支持 postgresql+psycopg2:// / mysql+pymysql://）
DATABASE_URL = os.getenv("DATABASE_URL") or ("sqlite:///" + _DEFAULT_DB_PATH.replace(os.sep, "/"))

_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # SQLite 单文件 + 允许跨线程访问（FastAPI 依赖在请求线程中解析）
    _connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def init_db():
    """创建所有表（幂等）。必须在导入 models 后调用，确保表已注册到 Base.metadata。"""
    from . import models  # noqa: F401  (确保表类已注册到元数据)
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI 依赖：每个请求一个 Session，请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
