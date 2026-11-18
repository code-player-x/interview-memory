"""Lock and atomically replace a crawler JSONL snapshot."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


@contextmanager
def output_lock(output):
    # OS releases the lock even when the collector is interrupted.
    with output.with_suffix(output.suffix + ".lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def save(output, rows):
    tmp = NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False)
    path = Path(tmp.name)
    try:
        with tmp:
            for row in rows.values():
                tmp.write(json.dumps(row, ensure_ascii=False) + "\n")
        path.replace(output)
    finally:
        path.unlink(missing_ok=True)
