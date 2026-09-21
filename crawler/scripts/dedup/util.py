"""去重通用工具：归一化、哈希、文本抽取。"""
import re
import hashlib


def norm(s: str) -> str:
    """归一化：转小写 -> 去所有空白 -> 去标点（保留中英文数字）。

    用于规则去重的「精确相等」判定，例如
    「Agent 是什么？」与「agent 是什么！！」归一化后都等于 `agent是什么`。
    """
    s = (s or "").lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^\w\u4e00-\u9fff]", "", s)  # 去标点，保留中英文数字
    return s


def sha256(s: str, length: int = 16) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:length]


def extract_text(rec, fields=("question", "content", "text", "title")) -> str:
    """从一个题记录里抽取题面文本，兼容多种输入结构。"""
    if isinstance(rec, str):
        return rec.strip()
    if isinstance(rec, dict):
        for f in fields:
            v = rec.get(f)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


def record_id(rec, idx: int) -> str:
    """为一条记录生成稳定 id（用于报告与回查）。"""
    if isinstance(rec, dict):
        for f in ("id", "qid", "question_id"):
            v = rec.get(f)
            if v is not None and str(v).strip():
                return str(v)
    t = extract_text(rec)
    return t or str(idx)
