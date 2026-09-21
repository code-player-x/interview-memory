#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""对最大领域做成分分析：区分「关键词命中」与「category 兜底」，并看子主题分布。"""
import json
import random
import re
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_questions import classify, blob, RULES  # noqa: E402

BANK = Path(__file__).resolve().parent.parent / "data" / "questions-bank.json"
data = json.loads(BANK.read_text(encoding="utf-8"))
items = data["items"]

groups = {}
for it in items:
    groups.setdefault(classify(it), []).append(it)

target = sys.argv[1] if len(sys.argv) > 1 else "llm_basics"
v = groups.get(target, [])
print(f"[{target}] 共 {len(v)} 题\n")

pat = dict((k, p) for k, _n, _f, p in RULES).get(target, "")
hit_kw = [it for it in v if pat and re.search(pat, blob(it))]
print(f"  由关键词命中: {len(hit_kw)}")
print(f"  由 category 兜底进入: {len(v) - len(hit_kw)}")
print(f"  兜底题的原 category 分布: "
      f"{dict(Counter(it.get('category','') for it in v if not (pat and re.search(pat, blob(it)))))}\n")

# 子主题探针
SUB = {
    "AI产品/应用/行业": r"产品|商业化|落地场景|行业|趋势|创业|竞品|用户增长|商业模式|to\s*b|to\s*c",
    "传统ML/深度学习基础": r"机器学习|深度学习|神经网络|反向传播|梯度|过拟合|正则|"
                    r"损失函数|激活函数|卷积|rnn|lstm|\bcnn\b|批归一化|dropout|优化器",
    "数学基础": r"矩阵|向量空间|概率|统计|求导|泰勒|信息熵|kl\s*散度|交叉熵|贝叶斯|分布",
    "模型架构/推理": r"transformer|注意力|moe|mamba|kv\s*cache|量化|推理|上下文窗口|位置编码|"
               r"rope|归一化|自回归|解码|采样|temperature",
    "Agent相关": r"agent|智能体|工具调用|mcp|workflow|规划|记忆",
    "RAG相关": r"rag|检索|向量|embedding|召回",
    "工程/部署": r"部署|服务|性能|监控|docker|k8s|推理服务|并发|吞吐",
}
cnt = Counter()
for it in v:
    t = blob(it)
    for name, p in SUB.items():
        if re.search(p, t):
            cnt[name] += 1
print("  子主题探针（可多重命中）:")
for name, c in cnt.most_common():
    print(f"    {name:<24} {c:>5}")

random.seed(7)
print("\n  随机抽样 12 条:")
for it in random.sample(v, min(12, len(v))):
    print(f"    [{it['id']}] ({it.get('category')}) {it.get('content','')[:64]}")
