"""为仅支持 SQLite 的历史工具解析数据库目标，不初始化或连接数据库。"""
import os
from pathlib import Path

from sqlalchemy.engine import make_url
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def sqlite_target(explicit_path=None):
    """显式 --db 优先，其次 DATABASE_URL；不支持的后端必须拒绝，不能回退。"""
    if explicit_path is not None:
        return str(Path(explicit_path).resolve())
    # 与应用一致：进程环境优先，未提供时读取项目 .env；不修改调用进程环境。
    configured = os.environ["DATABASE_URL"] if "DATABASE_URL" in os.environ else dotenv_values(ROOT / ".env").get("DATABASE_URL")
    if not configured:
        return str(ROOT / "data" / "interview_memory.db")
    url = make_url(configured)
    if url.get_backend_name() != "sqlite":
        raise ValueError("此历史工具仅支持 SQLite；DATABASE_URL 指向其他后端，已拒绝运行。")
    if not url.database or url.database == ":memory:" or url.database.startswith("file:") or url.query:
        raise ValueError("此历史工具需要普通 SQLite 文件 URL，不支持内存库或 URI 参数。")
    return str(Path(url.database).resolve())


def backup_sqlite(source, destination):
    """生成含 WAL 已提交记录的独立快照；不覆盖既有备份。"""
    import sqlite3
    from contextlib import closing

    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    with destination.open("xb"):
        pass
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db:
            with closing(sqlite3.connect(destination)) as backup:
                db.backup(backup)
                # 独立快照无需 WAL；避免后续只读校验生成 -wal/-shm 边文件。
                backup.execute("PRAGMA journal_mode=DELETE")
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("SQLite 备份完整性检查失败")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
