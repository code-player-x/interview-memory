#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""确认各备份/当前文件状态与题数。"""
import json
from pathlib import Path

B = Path("G:/interview-memory/crawler/data/questions-bank.json")
PRE = Path("G:/interview-memory/crawler/data/questions-bank.json.bak_20260919_004328")
AUD = Path("G:/interview-memory/crawler/data/questions-bank.json.bad_dedup_audit_20260919")

for name, p in [("当前 bank", B), ("去重前备份", PRE), ("降级结果留档", AUD)]:
    if not p.exists():
        print(f"{name}: 不存在")
        continue
    try:
        n = len(json.loads(p.read_text(encoding="utf-8"))["items"])
        print(f"{name}: {p.stat().st_size:,} bytes | {n} 题")
    except Exception as e:
        print(f"{name}: 解析失败 {e}")
