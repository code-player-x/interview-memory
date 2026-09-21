"""sentence-transformers 本地模型后端（可选，需 pip 安装）。

适合无 Ollama 环境，直接本地推理。中文推荐 BAAI/bge-small-zh-v1.5 之类。
依赖懒加载：仅当真正选用该后端时才 import，不影响其它路径。
"""
import os


class SentenceTransformersBackend:
    name = "st"

    def __init__(self, model: str = "BAAI/bge-small-zh-v1.5"):
        self.model_name = model
        self._m = None

    def _load(self):
        if self._m is None:
            from sentence_transformers import SentenceTransformer  # 懒加载
            self._m = SentenceTransformer(self.model_name)
        return self._m

    def available(self) -> bool:
        try:
            self._load()
            return True
        except Exception:
            return False

    def embed(self, texts):
        m = self._load()
        arr = m.encode(texts, normalize_embeddings=True)
        return arr.tolist()
