"""策略注册与 spec 解析。

spec 语法（驱动方只需传一个字符串即可选用/组合插件）：
  rule                单一规则去重
  semantic            单一语义去重
  none                不去重
  all                 = rule + semantic（组合，并集）
  rule+semantic       显式组合（同上，可扩展到任意数量）
每个名字可带构造参数（fuzzy / backend_name / model / threshold / use_cache），
由驱动方通过 kwargs 透传。
"""
from .rule_based import RuleBasedDedup
from .semantic import SemanticDedup
from .composite import CompositeDedup, NoopDedup


def get_strategy(name: str, **kw):
    name = (name or "").strip().lower()
    if name == "rule":
        return RuleBasedDedup(fuzzy=kw.get("fuzzy", 0.85))
    if name == "semantic":
        return SemanticDedup(
            backend_name=kw.get("backend_name", "ollama"),
            model=kw.get("model", "nomic-embed-text"),
            threshold=kw.get("threshold", 0.9),
            cache_path=kw.get("cache_path"),
            use_cache=kw.get("use_cache", True),
        )
    if name == "none":
        return NoopDedup()
    raise KeyError(f"未知去重策略: {name}（可选: rule / semantic / none / all / rule+semantic）")


def resolve_spec(spec: str, **kw):
    spec = (spec or "rule").strip().lower()
    if spec == "none":
        return NoopDedup()
    if spec == "all":
        return CompositeDedup([get_strategy("rule", **kw), get_strategy("semantic", **kw)])
    if "+" in spec:
        subs = [s.strip() for s in spec.split("+") if s.strip()]
        return CompositeDedup([get_strategy(s, **kw) for s in subs])
    return get_strategy(spec, **kw)
