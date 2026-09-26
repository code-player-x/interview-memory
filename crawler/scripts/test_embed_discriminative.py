#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证某嵌入模型对短中文题面的区分度。

用法: python test_embed_discriminative.py [model]
打印一组明显不同的短中文题面之间的余弦矩阵；若大量接近 1.0 说明该模型对短中文坍缩（不可用）。
"""
import sys
import json
import urllib.request
import numpy as np

URL = "http://localhost:11434/api/embed"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "bge-m3"

# 明显互不相同的短题面
TEXTS = [
    "抽象工厂", "职业规划", "过桥问题", "内存泄漏是什么", "如何设计Agent记忆系统",
    "RAG是什么", "MySQL索引", "快速排序", "协程和线程区别", "饿汉模式",
    "分布式锁怎么实现", "JWT和Session区别", "什么是闭包", "红黑树和AVL树区别",
    "为什么需要虚拟内存", "Kafka怎么保证不丢消息", "Transformer的注意力机制",
]


def embed(texts):
    payload = json.dumps({"model": MODEL, "input": texts}).encode("utf-8")
    req = urllib.request.Request(URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    return data["embeddings"]


def main():
    embs = embed(TEXTS)
    try:
        M = np.asarray(embs, dtype=np.float64)
        if M.ndim != 2 or M.shape[0] != len(TEXTS) or M.shape[1] == 0:
            raise ValueError("数量或维度不符")
        if not np.isfinite(M).all():
            raise ValueError("向量包含非有限值")
        # Scale first to avoid overflow/underflow of norms on finite vectors.
        scales = np.max(np.abs(M), axis=1, keepdims=True)
        if (scales == 0).any():
            raise ValueError("向量范数为零")
        M = M / scales
        M = M / np.linalg.norm(M, axis=1, keepdims=True)
    except (ValueError, TypeError, OverflowError) as exc:
        print(f"!! 无效嵌入响应：{exc}")
        raise SystemExit(1) from exc
    n = len(TEXTS)
    print(f"模型: {MODEL}  维度: {len(embs[0])}")
    print("相互余弦 (应远低于 1.0 才可用):")
    print("        " + " ".join(f"{t[:4]:>6}" for t in TEXTS))
    off_diag = []
    for i in range(n):
        row = " ".join(f"{float(M[i] @ M[j]):6.3f}" for j in range(n))
        print(f"{TEXTS[i][:5]:>6} {row}")
        for j in range(n):
            if i != j:
                off_diag.append(float(M[i] @ M[j]))
    off_diag = np.array(off_diag)
    # 统计"危险"对：余弦>=0.95 的不同题
    danger = int((off_diag >= 0.95).sum())
    print()
    print(f"非对角平均余弦: {off_diag.mean():.4f}  最大: {off_diag.max():.4f}")
    print(f"余弦>=0.95 的不同题对数: {danger} / {len(off_diag)}  (0 才说明区分度好)")
    if danger > 0:
        print("!! 该模型对短中文坍缩，不可用于去重。")
        sys.exit(1)
    else:
        print("OK 通过本组短中文区分度冒烟检查；实际去重效果仍需正负样本评估。")


if __name__ == "__main__":
    main()
