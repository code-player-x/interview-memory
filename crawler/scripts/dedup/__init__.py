"""可插拔去重策略包（plugin 化）。

设计要点（对应需求「语义去重是一个可以单独进行的功能，类似插件，
和原来的驱动方式并行存在，也可以组合使用」）：
  - 每个去重方法是一个独立 Strategy 插件（rule / semantic / none），
    彼此互不影响，可单独 import 使用；
  - CompositeDedup 把多个插件「并行组合」（rule+semantic / all），
    默认并集（任一判重即去重），也可交集（mode=all）；
  - semantic 后端本身也可插拔（ollama / sentence-transformers）；
  - 提供 DedupRunner 统一驱动循环，convert 流程与独立 CLI 共用。

用法：
  from dedup import resolve_spec, DedupRunner
  strat = resolve_spec("rule+semantic", threshold=0.9)   # 组合
  strat = resolve_spec("semantic")                        # 单独语义
  runner = DedupRunner(strat, baseline=existing_texts)
  kept, dups = runner.process([(id, text), ...])
"""
from .base import DedupStrategy, CheckResult
from .rule_based import RuleBasedDedup
from .semantic import SemanticDedup
from .composite import CompositeDedup, NoopDedup
from .runner import DedupRunner
from .registry import get_strategy, resolve_spec

__all__ = [
    "DedupStrategy", "CheckResult",
    "RuleBasedDedup", "SemanticDedup", "CompositeDedup", "NoopDedup",
    "DedupRunner", "get_strategy", "resolve_spec",
]
