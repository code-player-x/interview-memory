"""艾宾浩斯遗忘曲线：复习阶段推进与间隔计算。

阶段约定（与 app.py 一致）：
- stage 从 1 开始；steps 为间隔天数列表（默认 "1,2,4,7,15,30,60"）。
- stage > len(steps) 视为「已掌握」（mark_mastered 将 stage 置为 len(steps)+1）。
- 答错（remembered=False）回到第 1 阶段（重置记忆曲线）。
"""
from datetime import datetime, timedelta
from typing import List

_DEFAULT_STEPS = [1, 2, 4, 7, 15, 30, 60]


def get_steps(s: str) -> List[int]:
    """解析 '1,2,4,7,15,30,60' 为间隔天数列表；空或非法时回退默认。"""
    if not s or not s.strip():
        return list(_DEFAULT_STEPS)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    try:
        return [int(p) for p in parts if p]
    except ValueError:
        return list(_DEFAULT_STEPS)


def next_review_for_stage(stage: int, steps: List[int], base: datetime = None) -> datetime:
    """根据当前阶段返回下次复习时间（base + 间隔天数）。"""
    if base is None:
        base = datetime.utcnow()
    if not steps:
        return base + timedelta(days=1)
    idx = min(max(int(stage), 1) - 1, len(steps) - 1)
    return base + timedelta(days=steps[idx])


def advance_stage(stage: int, remembered: bool, steps: List[int]) -> int:
    """复习反馈推进阶段：记住→下一阶段；答错→重置到第 1 阶段。"""
    n = len(steps)
    if remembered:
        return min(int(stage) + 1, n + 1)
    return 1


def is_mastered(stage: int, steps: List[int]) -> bool:
    """是否已掌握：阶段超过最后一步。"""
    return int(stage) > len(steps)
