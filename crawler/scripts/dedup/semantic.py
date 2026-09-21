"""语义去重策略（向量余弦相似度）。

把题面转成 embedding，与索引里的已有向量算余弦相似度，>= threshold（默认 0.9）
判为重复。能识别「同义不同表述」的题，弥补规则去重的漏检。

特点（作为独立插件）：
  - 后端可插拔：默认 ollama（nomic-embed-text），可选 sentence-transformers；
  - 带 embedding 缓存（pickle），首次跑慢、后续秒级且幂等；
  - available() 显式探测后端，不可用时由上层优雅报错，绝不静默出错结果。

首次对全库（1354 + 1175）跑会触发大量 embedding 请求，建议在 Ollama 启动时执行；
缓存建立后重跑几乎零成本。
"""
import math
import os
import pickle
from pathlib import Path

from .base import DedupStrategy, CheckResult
from .util import sha256
from .backends.ollama import OllamaBackend
from .backends.sentence_transformers import SentenceTransformersBackend

PROJ = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = PROJ / "data" / "tmp" / ".semantic_embed_cache.pkl"


def cosine(a, b) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class SemanticDedup(DedupStrategy):
    name = "semantic"

    def __init__(self, backend=None, backend_name: str = "ollama",
                 model: str = "nomic-embed-text", threshold: float = 0.9,
                 cache_path=None, use_cache: bool = True, cache_only: bool = False):
        if backend is None:
            backend = (SentenceTransformersBackend(model=model)
                       if backend_name == "st" else OllamaBackend(model=model))
        self.backend = backend
        self.threshold = threshold
        self.use_cache = use_cache
        self.cache_only = cache_only
        self.cache_path = str(cache_path or DEFAULT_CACHE)
        self._emb = []  # list of (text, vec)
        self._cache = self._load_cache() if self.use_cache else {}

    def available(self) -> bool:
        if self.cache_only:
            # 仅依赖本地缓存，无需联网后端；缓存可用即视为可用
            return bool(self._cache)
        try:
            return self.backend.available()
        except Exception:
            return False

    def _load_cache(self):
        try:
            return pickle.load(open(self.cache_path, "rb"))
        except Exception:
            return {}

    def _save_cache(self):
        if not self.use_cache:
            return
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        pickle.dump(self._cache, open(self.cache_path, "wb"))

    def _embed(self, texts):
        out = []
        need, need_idx = [], []
        for i, t in enumerate(texts):
            h = sha256(t)
            if self.use_cache and h in self._cache:
                out.append(self._cache[h])
            elif self.cache_only:
                # 缓存未命中且禁止联网：返回 None，由上层按规则去重/保留
                out.append(None)
            else:
                out.append(None)
                need.append(t)
                need_idx.append(i)
        if need:
            vecs = self.backend.embed(need)
            for t, v in zip(need, vecs):
                self._cache[sha256(t)] = v
            self._save_cache()
            j = 0
            for i in need_idx:
                out[i] = vecs[j]
                j += 1
        return out

    def index(self, existing_texts) -> None:
        vecs = self._embed(list(existing_texts or []))
        self._emb = list(zip(existing_texts or [], vecs))

    def add(self, text: str) -> None:
        v = self._embed([text])[0]
        self._emb.append((text, v))

    def check(self, text: str) -> CheckResult:
        v = self._embed([text])[0]
        best = None
        bs = 0.0
        for t, ev in self._emb:
            s = cosine(v, ev)
            if s >= self.threshold and s > bs:
                bs = s
                best = t
        if best:
            return CheckResult(True, bs, best, f"cosine>={self.threshold:.2f}")
        return CheckResult(False)
