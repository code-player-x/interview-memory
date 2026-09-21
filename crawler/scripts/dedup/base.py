"""去重策略抽象基类。

每个去重方法（归一化规则、语义向量、组合…）都实现同一套接口，
从而可以「单独作为一个插件使用」，也可以被 CompositeDedup 并行组合。

接口约定：
  index(existing_texts)   —— 用基线文本（已有题面）预建索引，只调一次
  add(text)               —— 每保留一道题后，把它的文本增量加入索引
  check(text) -> CheckResult —— 判断单条文本相对当前索引是否重复
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CheckResult:
    is_duplicate: bool
    score: float = 0.0            # 相似度/置信度
    matched: Optional[str] = None  # 命中的已有文本
    detail: str = ""              # 判定原因（如 norm-exact / fuzzy>=0.85 / cosine>=0.90）


class DedupStrategy:
    name = "base"

    def index(self, existing_texts) -> None:
        """用基线文本预建索引。默认空实现。"""
        pass

    def add(self, text: str) -> None:
        """增量加入一条已保留的文本。默认空实现。"""
        pass

    def check(self, text: str) -> CheckResult:
        raise NotImplementedError

    def available(self) -> bool:
        """后端是否可用（语义类需要联网/模型，规则类恒 true）。"""
        return True
