"""规则去重策略（原 convert 脚本里的两级去重逻辑，独立成插件）。

做法：
  1) 归一化精确相等（norm-exact）—— 表述完全相同的题；
  2) 字符级模糊 SequenceMatcher >= fuzzy（默认 0.85）—— 仅差标点/措辞的题。
纯字符串规则，无模型、毫秒级、可解释、可回滚。
"""
from difflib import SequenceMatcher

from .base import DedupStrategy, CheckResult
from .util import norm


class RuleBasedDedup(DedupStrategy):
    name = "rule"

    def __init__(self, fuzzy: float = 0.85):
        self.fuzzy = fuzzy
        self._existing = []  # list of (norm_text, raw_text)

    def index(self, existing_texts) -> None:
        self._existing = [(norm(t), t) for t in (existing_texts or [])]

    def add(self, text: str) -> None:
        self._existing.append((norm(text), text))

    def check(self, text: str) -> CheckResult:
        n = norm(text)
        for en, raw in self._existing:
            if en == n:
                return CheckResult(True, 1.0, raw, "norm-exact")
        best = None
        bs = 0.0
        for en, raw in self._existing:
            r = SequenceMatcher(None, n, en).ratio()
            if r >= self.fuzzy and r > bs:
                bs = r
                best = raw
        if best:
            return CheckResult(True, bs, best, f"fuzzy>={self.fuzzy:.2f}")
        return CheckResult(False)
