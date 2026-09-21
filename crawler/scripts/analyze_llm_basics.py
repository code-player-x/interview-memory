# -*- coding: utf-8 -*-
"""分析 llm-basics.md（1212 题）真实成分：按关键词重新聚类到更细的桶，
看它到底有多少是「真·大模型基础」，多少是误放进来的其他领域碎片。
"""
import re
from pathlib import Path
from collections import defaultdict

F = Path("G:/interview-memory/crawler/questions_v2/full/llm-basics.md")
text = F.read_text(encoding="utf-8")
blocks = re.split(r"\n---\n", text)

def title_of(b):
    m = re.search(r"^## \s*\d+\.\s*(.+)$", b, re.M)
    return m.group(1).strip() if m else None

titles = [t for t in (title_of(b) for b in blocks) if t]
print(f"TOTAL={len(titles)}")

# 优先级桶：顺序即匹配优先级（先到先得）
BUCKETS = [
    ("前端/JS/Web", r"js|javascript|前端|react|vue|webpack|vite|typeof|instanceof|闭包|原型链|事件循环|浏览器|css|html|\bdom\b|tailwind|低代码|组件|hooks|小程序|echarts"),
    ("AI产品/职场/行为", r"产品|简历|职业规划|薪资|转岗|跳槽|面试|沟通|需求|增长|商业化|用户|项目管理|团队协作|复盘|汇报|绩效|老板|向上|okr|晋升|竞争力|软技能"),
    ("Agent/工具/MCP", r"agent|智能体|工具调用|function calling|mcp|多智能体|react\b|规划|记忆|反思|编排"),
    ("RAG/检索/向量", r"rag|检索|向量|embedding|知识库|召回|重排|rerank|chunk|切分"),
    ("提示工程", r"prompt|提示词|few-shot|cot|思维链|角色设定|system prompt"),
    ("后端/DB/网络/OS(非LLM)", r"mysql|redis|索引|事务|缓存|go\b|java|jvm|线程|锁|并发|tcp|http|操作系统|进程|网络|kafka|消息队列|docker|k8s|微服务|分布式"),
    ("算法/数据结构", r"链表|二叉树|二叉|排序|动态规划|数组|哈希|栈|队列|贪心|图|dfs|bfs|字符串|递归"),
    ("ML/深度学习基础", r"过拟合|正则化|梯度|损失|激活函数|反向传播|特征|归一化|batch|学习率|神经网络|cnn|rnn|lstm|集成|决策树|svm|聚类|降维|pca|auc|roc|precision|recall|f1|交叉熵|准确率|样本|标签|训练集|验证集|泛化"),
    ("真·大模型基础", r"transformer|attention|注意力|token|分词|位置编码|rope|量化|幻觉|采样|temperature|top-p|top-k|上下文|kv\s*cache|解码|moe|蒸馏|预训练|微调|gpt|bert|llama|qwen|deepseek|chatgpt|gptq|awq|推理|涌现|scaling|参数|对齐|奖励"),
]

compiled = [(name, re.compile(pat, re.I)) for name, pat in BUCKETS]
samples = defaultdict(list)
counts = defaultdict(int)

for t in titles:
    placed = False
    for name, rx in compiled:
        if rx.search(t):
            counts[name] += 1
            if len(samples[name]) < 4:
                samples[name].append(t)
            placed = True
            break
    if not placed:
        counts["其他/碎片"] += 1
        if len(samples["其他/碎片"]) < 6:
            samples["其他/碎片"].append(t)

for name, _ in compiled:
    print(f"\n### {name}: {counts[name]}")
    for s in samples[name]:
        print(f"   - {s}")
print(f"\n### 其他/碎片: {counts['其他/碎片']}")
for s in samples['其他/碎片']:
    print(f"   - {s}")

llm_true = counts.get("真·大模型基础", 0)
print(f"\n=== 结论：真·大模型基础约 {llm_true} / {len(titles)} ({llm_true*100//len(titles)}%)；其余 {len(titles)-llm_true} 属误放/兜底 ===")
