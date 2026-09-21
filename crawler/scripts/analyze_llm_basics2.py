# -*- coding: utf-8 -*-
"""第二层分析：对 llm-basics.md 中第一轮未匹配(其他/碎片)的题，用更细的关键词再聚类，
弄清这 853 题到底能拆到哪些具体领域。
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

PASS1 = [
    r"js|javascript|前端|react|vue|webpack|vite|typeof|instanceof|闭包|原型链|事件循环|浏览器|css|html|\bdom\b|tailwind|低代码|组件|hooks|小程序",
    r"产品|简历|职业规划|薪资|转岗|跳槽|面试|沟通|需求|增长|商业化|用户|项目管理|团队协作|复盘|汇报|绩效|老板|向上|okr|晋升|竞争力|软技能",
    r"agent|智能体|工具调用|function calling|mcp|多智能体|react\b|规划|记忆|反思|编排",
    r"rag|检索|向量|embedding|知识库|召回|重排|rerank|chunk|切分",
    r"prompt|提示词|few-shot|cot|思维链|角色设定|system prompt",
    r"mysql|redis|索引|事务|缓存|go\b|java|jvm|线程|锁|并发|tcp|http|操作系统|进程|网络|kafka|消息队列|docker|k8s|微服务|分布式",
    r"链表|二叉树|二叉|排序|动态规划|数组|哈希|栈|队列|贪心|图|dfs|bfs|字符串|递归",
    r"过拟合|正则化|梯度|损失|激活函数|反向传播|特征|归一化|batch|学习率|神经网络|cnn|rnn|lstm|集成|决策树|svm|聚类|降维|pca|auc|roc|precision|recall|f1|交叉熵|准确率|样本|标签|训练集|验证集|泛化",
    r"transformer|attention|注意力|token|分词|位置编码|rope|量化|幻觉|采样|temperature|top-p|top-k|上下文|kv\s*cache|解码|moe|蒸馏|预训练|微调|gpt|bert|llama|qwen|deepseek|chatgpt|gptq|awq|推理|涌现|scaling|参数|对齐|奖励",
]

unmatched = []
for t in titles:
    if not any(re.search(p, t, re.I) for p in PASS1):
        unmatched.append(t)

BUCKETS2 = [
    ("设计模式/面向对象", r"工厂|单例|观察者|策略|装饰|适配|原型|建造者|代理|模板方法|桥接|组合模式|享元|外观|状态模式|命令模式|职责链|迭代器|访问者|备忘录|中介|mvc|oop|面向对象|继承|多态|封装|抽象类|接口|设计模式"),
    ("软件工程/编码/测试", r"重构|代码质量|可维护性|单元测试|测试|ci|cd|code review|命名|注释|设计原则|solid|迪米特|开闭|依赖倒置|耦合|内聚|可读性|技术债|代码规范|结对|tdd"),
    ("架构/系统设计", r"架构|高可用|高并发|扩容|限流|降级|熔断|一致性|分布式事务|幂等|可扩展|容灾|异地多活"),
    ("数据库/SQL通用", r"\bsql\b|慢查询|分库|分表|\bjoin\b|范式|事务隔离|幻读|脏读|死锁.*(数据库|mysql)|主从|读写分离"),
    ("网络/协议", r"\btcp\b|\budp\b|\bhttp\b|\bhttps\b|\bdns\b|websocket|\brpc\b|\bgrpc\b|\brest\b|长连接|握手"),
    ("操作系统", r"进程|线程|死锁|虚拟内存|分页|文件系统|中断|调度算法|信号量|互斥"),
    ("编程语言通用(内存/GC等)", r"指针|引用|值类型|引用类型|垃圾回收|\bgc\b|内存泄漏|堆栈|异常|泛型|闭包|作用域|拷贝|深浅"),
    ("数据结构基础", r"数组|链表|栈|队列|树|图|堆|哈希|字符串|二叉树|红黑树|跳表|位图"),
    ("算法思想", r"排序|查找|动态规划|贪心|回溯|分治|双指针|滑动窗口|位运算|贪心"),
]

compiled = [(n, re.compile(p, re.I)) for n, p in BUCKETS2]
counts = defaultdict(int)
samples = defaultdict(list)
for t in unmatched:
    for n, rx in compiled:
        if rx.search(t):
            counts[n] += 1
            if len(samples[n]) < 5:
                samples[n].append(t)
            break
    else:
        counts["仍无法归类/极短碎片"] += 1
        if len(samples["仍无法归类/极短碎片"]) < 8:
            samples["仍无法归类/极短碎片"].append(t)

total_um = len(unmatched)
print(f"未匹配(第一轮其他/碎片)总数={total_um}")
for n, _ in compiled:
    print(f"\n### {n}: {counts[n]}")
    for s in samples[n]:
        print(f"   - {s}")
print(f"\n### 仍无法归类/极短碎片: {counts['仍无法归类/极短碎片']}")
for s in samples['仍无法归类/极短碎片']:
    print(f"   - {s}")
print(f"\n=== 853 碎片可拆: 设计模式/面向对象={counts.get('设计模式/面向对象',0)} 软工/测试={counts.get('软件工程/编码/测试',0)} 架构/设计={counts.get('架构/系统设计',0)} DB={counts.get('数据库/SQL通用',0)} 网络={counts.get('网络/协议',0)} OS={counts.get('操作系统',0)} 语言通用={counts.get('编程语言通用(内存/GC等)',0)} 数据结构={counts.get('数据结构基础',0)} 算法={counts.get('算法思想',0)} 仍不可归={counts.get('仍无法归类/极短碎片',0)} ===")
