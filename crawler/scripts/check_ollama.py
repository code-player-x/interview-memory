#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查 Ollama 服务与可用模型。"""
import json
import urllib.request

try:
    with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
        d = json.loads(r.read().decode("utf-8"))
    models = [m.get("name") for m in d.get("models", [])]
    print("OLLAMA_OK")
    print("MODELS:")
    for m in models:
        print("  -", m)
    print(f"bge-m3 present: {any('bge-m3' in m for m in models)}")
except Exception as e:
    print(f"OLLAMA_DOWN: {type(e).__name__}: {e}")
