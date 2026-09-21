"""组合策略：让多个去重插件「并行存在、组合使用」。

  - CompositeDedup(strategies, mode="any")：任意子策略判重即视为重复（并集，最稳妥）；
  - mode="all"：所有子策略都判重才视为重复（交集，更严格、更易漏）。
"""
from .base import DedupStrategy, CheckResult


class NoopDedup(DedupStrategy):
    """空策略：不去重，全部保留。对应 spec 'none'。"""
    name = "none"

    def index(self, existing_texts) -> None:
        pass

    def add(self, text: str) -> None:
        pass

    def check(self, text: str) -> CheckResult:
        return CheckResult(False)


class CompositeDedup(DedupStrategy):
    name = "composite"

    def __init__(self, strategies, mode: str = "any"):
        self.strategies = list(strategies)
        self.mode = mode

    def available(self) -> bool:
        # 任一支不可用则整体不可用（便于上层优雅报错）
        return all(s.available() for s in self.strategies)

    def index(self, existing_texts) -> None:
        for s in self.strategies:
            s.index(existing_texts)

    def add(self, text: str) -> None:
        for s in self.strategies:
            s.add(text)

    def check(self, text: str) -> CheckResult:
        results = [s.check(text) for s in self.strategies]
        if self.mode == "all":
            if all(r.is_duplicate for r in results):
                best = max(results, key=lambda r: r.score)
                return best
            return CheckResult(False)
        # any
        dups = [r for r in results if r.is_duplicate]
        if dups:
            best = max(dups, key=lambda r: r.score)
            return best
        return CheckResult(False)
