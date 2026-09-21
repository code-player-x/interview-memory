"""Embedding 后端插件目录。

每个后端实现 `embed(texts: list[str]) -> list[list[float]]` 与 `available() -> bool`。
新增后端只需在此目录加一个模块并在 semantic.py 里注册，无需改动驱动。
"""
