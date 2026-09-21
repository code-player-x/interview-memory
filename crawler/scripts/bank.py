#!/usr/bin/env python3
"""题库本地镜像：questions-bank.json 的读写与状态管理。
这是飞书知识库的权威本地副本，去重与每日推送都先读它。
"""
import json
import re
import sys
from pathlib import Path

BANK_PATH = Path(__file__).resolve().parent.parent / "data" / "questions-bank.json"


def normalize(text: str) -> str:
    """归一化题面：去空白/标点/大小写，用于精确去重。"""
    t = text.lower()
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"[，。、；：？！,.?;:!“”\"'()（）\[\]【】{}<>《》\/\\|#@*~`\-_=+^$%&]", "", t)
    return t


def load(path=BANK_PATH):
    if not path.exists():
        return {"meta": {"last_pushed": []}, "items": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save(data, path=BANK_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_entry(item: dict, path=BANK_PATH):
    """新增/追加一条题目，写入本地镜像。item 需含 content；自动补 id/status。"""
    data = load(path)
    items = data.setdefault("items", [])
    if not item.get("id"):
        item["id"] = f"q{len(items) + 1:04d}"
    item["norm"] = normalize(item.get("content", ""))
    items.append(item)
    save(data, path)
    return item["id"]


def mark_status(qid: str, status: str, path=BANK_PATH):
    data = load(path)
    for it in data["items"]:
        if it.get("id") == qid:
            it["status"] = status
            break
    save(data, path)


if __name__ == "__main__":
    # 简单自测：python bank.py
    print("bank items:", len(load()["items"]))
