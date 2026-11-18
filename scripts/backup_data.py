"""离线 SQLite + 本地配图快照；恢复到新目录，绝不覆盖正在使用的数据。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
from contextlib import closing, contextmanager

try:
    from .sqlite_target import backup_sqlite, sqlite_target
except ImportError:
    from sqlite_target import backup_sqlite, sqlite_target


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def is_link(path):
    if path.is_symlink():
        return True
    # Python 3.10/3.11 没有 Path.is_junction()。
    if os.name == "nt" and path.exists():
        return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return False


def regular_files(root):
    def raise_error(error):
        raise error

    for directory, dirs, files in os.walk(root, onerror=raise_error):
        for name in dirs + files:
            path = Path(directory) / name
            if is_link(path):
                raise ValueError("快照不支持符号链接或目录联接")
        for name in files:
            path = Path(directory) / name
            if not path.is_file():
                raise ValueError(f"快照仅支持普通文件：{path}")
            yield path


@contextmanager
def new_output(directory):
    directory.mkdir(parents=True, exist_ok=False)
    try:
        yield
    except BaseException:
        shutil.rmtree(directory)
        raise


def create_snapshot(database, images, output):
    images = Path(images)
    if is_link(images):
        raise ValueError("图片目录不能是链接")
    database, images, output = Path(database).resolve(), images.resolve(), Path(output).resolve()
    if output == images or images in output.parents:
        raise ValueError("备份目录不能位于图片目录内")
    if not database.is_file():
        raise FileNotFoundError(database)
    if not images.is_dir():
        raise NotADirectoryError(images)
    with new_output(output):
        backup_sqlite(database, output / "interview_memory.db")
        (output / "images").mkdir()
        for source in regular_files(images):
            target = output / "images" / source.relative_to(images)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        manifest = {path.relative_to(output).as_posix(): digest(path) for path in regular_files(output)}
        (output / "manifest.json").write_text(json.dumps({"version": 1, "files": manifest}, indent=2), encoding="utf-8")


def verify_snapshot(snapshot):
    snapshot = Path(snapshot).resolve()
    actual = {p.relative_to(snapshot).as_posix(): p for p in regular_files(snapshot) if p != snapshot / "manifest.json"}
    if not (snapshot / "images").is_dir():
        raise ValueError("快照缺少图片目录")
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    if (not isinstance(manifest, dict) or manifest.get("version") != 1
            or not isinstance(manifest.get("files"), dict) or "interview_memory.db" not in manifest["files"]):
        raise ValueError("无效快照清单")
    if any(name != "interview_memory.db" and not name.startswith("images/") for name in actual):
        raise ValueError("快照包含不能恢复的文件")
    if set(actual) != set(manifest["files"]):
        raise ValueError("快照文件缺失或包含未登记文件")
    for name, expected in manifest["files"].items():
        if digest(actual[name]) != expected:
            raise ValueError("快照校验失败：" + name)
    with closing(sqlite3.connect((snapshot / "interview_memory.db").as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite 完整性校验失败")
    return snapshot


def restore_snapshot(snapshot, output):
    snapshot, output = verify_snapshot(snapshot), Path(output).resolve()
    if output == snapshot or snapshot in output.parents:
        raise ValueError("恢复目录不能位于快照内")
    with new_output(output):
        backup_sqlite(snapshot / "interview_memory.db", output / "interview_memory.db")
        shutil.copytree(snapshot / "images", output / "images")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--db")
    backup.add_argument("--images", type=Path, default=Path(__file__).resolve().parents[1] / "data/images")
    backup.add_argument("--output", type=Path, required=True)
    backup.add_argument("--stopped", action="store_true", required=True, help="确认应用及所有数据写入脚本已停止，保证数据库和图片一致")
    restore = commands.add_parser("restore")
    restore.add_argument("--snapshot", type=Path, required=True)
    restore.add_argument("--output", type=Path, required=True, help="不存在的新目录")
    check = commands.add_parser("verify")
    check.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "backup":
        create_snapshot(sqlite_target(args.db), args.images, args.output)
    elif args.action == "restore":
        restore_snapshot(args.snapshot, args.output)
    else:
        verify_snapshot(args.snapshot)
    print("完成；原数据库及配图目录未被覆盖。")


if __name__ == "__main__":
    main()
