"""Ollama 本地 embedding 后端（默认）。

依赖本地已启动 Ollama 且拉取了 embedding 模型（如 nomic-embed-text）。
接口：POST /api/embeddings  {"model":..., "prompt":...} -> {"embedding":[...]}
"""
import json
import urllib.request


class OllamaBackend:
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434",
                 model: str = "nomic-embed-text", timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status == 200
        except Exception:
            return False

    def embed(self, texts):
        vecs = []
        for t in texts:
            payload = json.dumps({"model": self.model, "prompt": t}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.load(r)
            vecs.append(data["embedding"])
        return vecs
