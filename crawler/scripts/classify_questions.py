#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按技术领域给题库分类，并导出为每个领域一个 Markdown 文件。

分类设计（两阶段，避免误判）：
  阶段 1：按【题面 + 标签】做有序关键词匹配（越具体越靠前）。
          ⚠️ 刻意【不】纳入答案正文：答案旁征博引会把无关题串味
          （实测"Redis 大 Key"因答案提到 go 而被判成 Go）。
  阶段 2：用原 category 兜底（手撕算法/行为与HR/项目深挖/Go 等强先验）。
  阶段 3：general。

用法：
  python scripts/classify_questions.py            # 打印分布
  python scripts/classify_questions.py --apply    # 写 questions/*.md
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
BANK = PROJ / "data" / "questions-bank.json"
OUTDIR = PROJ / "questions"

# (key, 中文领域名, 文件名, 关键词正则) —— 顺序即优先级
RULES = [
    ("puzzle", "智力题与逻辑推理", "puzzle.md",
     r"智力题|100\s*层楼|鸡蛋|匹马|赛道.*赛出|毒药|水桶|量出|天平|海盗分金|"
     r"过桥|蓝眼睛|棕眼|约瑟夫|三门问题|分金条|果冻问题|量水问题|"
     r"称重|概率题|帽子问题|猴子|香蕉"),

    # 后训练/预训练放在算法之前：避免 "DPO 数学推导" 被手撕类关键词抢走
    ("llm_posttraining", "大模型后训练（微调/对齐）", "llm-posttraining.md",
     r"微调|fine[\s\-]?tun|(?<!\w)sft(?!\w)|\brlhf\b|\bdpo\b|\bppo\b|奖励模型|"
     r"\brm\b.*偏好|对齐(?!.*内存|.*字节)|alignment|lora|qlora|peft|"
     r"蒸馏|distill|\brlvr\b|grpo|指令微调|拒绝采样|人类反馈|"
     r"偏好(数据|优化)|继续预训练|增量预训练|后训练|\brft\b"),

    ("llm_pretraining", "大模型预训练", "llm-pretraining.md",
     r"预训练|pre[\s\-]?train|语料|数据清洗|去重率|数据配比|数据管道|"
     r"tokeniz|\bbpe\b|词表|scaling\s*law|规模定律|涌现|"
     r"分布式训练|数据并行|张量并行|流水线并行|3d\s*并行|"
     r"混合专家|\bmoe\b.*(训练|路由|负载)|expert.*(并行|负载)|"
     r"训练稳定性|loss\s*spike|warmup|预训练目标|next[\s\-]token|"
     r"自回归.*(训练|目标)|\bmlm\b|数据质量|预训练数据|基座模型.*训练"),

    ("algorithm", "手撕算法", "algorithm.md",
     r"手撕|leetcode|反转链表|两数之和|合并\s*k\s*个有序链表|层序遍历|"
     r"最近公共祖先|合并区间|最长无重复|快速排序|快速选择|\blru\b|"
     r"二分查找|动态规划|回溯|滑动窗口|拓扑排序|堆排序|"
     r"二叉搜索树|二叉树的|链表|时间复杂度.*空间复杂度|"
     r"算法(题|实现|思路)|排序(算法|.*实现)|查找算法"),

    ("mq", "消息队列（Kafka 等）", "mq.md",
     r"kafka|rocketmq|rabbitmq|pulsar|消息队列|消息丢失|重复消费|"
     r"消息积压|顺序消息|事务消息|consumer\s*group|rebalance|"
     r"\bisr\b|topic.*分区|分区数|offset.*提交|死信|延迟队列|(?<![a-z])mq(?![a-z])"),

    ("java", "Java / JVM / 并发", "java.md",
     r"(?<![a-z])jvm(?![a-z])|垃圾回收|垃圾收集|(?<![a-z])gc(?![a-z])|"
     r"双亲委派|类加载|元空间|永久代|方法区|oom|synchronized|volatile|"
     r"happens[\s\-]before|(?<![a-z])aqs(?![a-z])|reentrantlock|threadlocal|"
     r"(?<![a-z])cas(?![a-z])|aba\s*问题|线程池|阻塞队列|completablefuture|"
     r"concurrenthashmap|(?<![a-z])java(?![a-z])|spring|(?<![a-z])jdk(?![a-z])|"
     r"四种引用|对象创建.*堆|\bheap\b.*dump"),

    ("os_network", "操作系统与计算机网络", "os-network.md",
     r"进程(?!.*agent)|线程(?!池|.*go)|协程(?!.*goroutine)|虚拟内存|分页|分段|"
     r"页面置换|上下文切换|用户态|内核态|系统调用|零拷贝|"
     r"select\s*/\s*poll|epoll|io\s*多路复用|(?<![a-z])tcp(?!\w)|"
     r"(?<![a-z])udp(?!\w)|三次握手|四次挥手|time_wait|拥塞控制|"
     r"(?<![a-z])http(?!\w)|(?<![a-z])https(?!\w)|(?<![a-z])dns(?!\w)|"
     r"osi\s*七层|状态码|输入\s*url|文件系统|inode|网络分层"),

    ("distributed", "分布式系统", "distributed.md",
     r"分布式事务|分布式锁|分布式\s*id|分布式一致性|(?<![a-z])cap(?!\w)|"
     r"base\s*理论|\braft\b|\bpaxos\b|\b2pc\b|\b3pc\b|\btcc\b|\bsaga\b|"
     r"一致性哈希|脑裂|熔断|降级|限流|服务注册|服务发现|注册中心|"
     r"负载均衡|微服务|服务治理|幂等|分布式追踪|链路追踪|分布式协调"),

    ("redis", "Redis 与缓存", "redis.md",
     r"redis|缓存穿透|缓存击穿|缓存雪崩|缓存一致性|双写一致|"
     r"(?<![a-z])rdb(?!\w)|(?<![a-z])aof(?!\w)|zset|跳表|内存淘汰|"
     r"过期(策略|删除)|热\s*key|大\s*key|pipeline|multi\s*/\s*exec|"
     r"发布订阅|pub\s*/\s*sub|哨兵|memcached|布隆过滤器|缓存预热|"
     r"缓存(?!.*kv.*llm)"),

    ("mysql", "MySQL", "mysql.md",
     r"mysql|innodb|myisam|b\s*\+\s*树|b\+tree|聚簇索引|二级索引|覆盖索引|"
     r"联合索引|最左前缀|索引失效|回表|(?<![a-z])mvcc(?![a-z])|"
     r"redo\s*log|undo\s*log|binlog|间隙锁|行锁|表锁|next[\s\-]key|"
     r"隔离级别|(?<![a-z])acid(?![a-z])|分库分表|慢\s*sql|explain|"
     r"执行计划|buffer\s*pool|主从复制|数据库.*事务|sql\s*优化|"
     r"索引(?!.*向量)|主键(?!.*分布式)|死锁|数据库锁|分表|"
     r"数据库(?!.*向量)"),

    ("go", "Go 语言", "go.md",
     r"golang|goroutine|channel|(?<![a-z])gmp(?![a-z])|调度器|(?<![a-z])defer(?![a-z])|"
     r"panic.*recover|(?<![a-z])slice(?![a-z])|切片|协程.*go|sync\.|rwmutex|"
     r"(?<![a-z])mutex(?![a-z])|(?<![a-z])atomic(?![a-z])|context\.|逃逸分析|"
     r"(?<![a-z])gin(?![a-z])|(?<![a-z])gorm(?![a-z])|go\s*module|"
     r"结构体|interface|泛型.*go|"
     # go 紧贴中文（"Go 后端"/"go是"/"Go 的"），避免命中英文 go to
     r"(?<![a-z])go(?![a-z])\s*[\u4e00-\u9fa5]|[\u4e00-\u9fa5]\s*(?<![a-z])go(?![a-z])"),

    ("rag", "RAG 与向量检索", "rag.md",
     r"(?<![a-z])rag(?![a-z])|检索增强|向量(库|检索|数据库|化)|embedding|"
     r"召回|重排|rerank|milvus|faiss|文档切分|chunking|混合检索|"
     r"bm25|稠密检索|稀疏检索|知识库(?!.*飞书)|切片策略|分割策略|"
     r"检索(?!.*es\b)|文档.*解析"),

    ("multimodal", "多模态", "multimodal.md",
     r"多模态|(?<![a-z])clip(?![a-z])|siglip|(?<![a-z])vlm(?![a-z])|"
     r"视觉|图像(?!.*系统)|视频理解|语音|whisper|q[\s\-]?former|"
     r"perceiver|视觉\s*token|文生图|扩散模型|stable\s*diffusion|"
     r"跨模态|模态对齐|(?<![a-z])ocr(?![a-z])|视觉编码器|目标检测|音频"),

    ("prompt", "提示工程", "prompt.md",
     r"提示词|(?<![a-z])prompt(?![a-z])|提示注入|prompt\s*injection|"
     r"few[\s\-]?shot|zero[\s\-]?shot|思维链|(?<![a-z])cot(?![a-z])|"
     r"system\s*prompt|角色设定|提示模板|jailbreak|越狱|提示工程"),

    ("safety", "安全与沙箱", "safety.md",
     r"沙箱|(?<![a-z])sandbox(?![a-z])|安全隔离|越狱|注入攻击|权限控制|"
     r"代码执行.*隔离|容器逃逸|敏感信息|脱敏|合规|审计|红队|"
     r"red\s*team|风险管控|异常管控|安全框架|安全.*对齐"),

    ("agent", "Agent 架构与工程", "agent.md",
     r"(?<![a-z])agent(?![a-z])|智能体|多智能体|multi[\s\-]agent|工具调用|"
     r"function\s*call|(?<![a-z])mcp(?![a-z])|(?<![a-z])skills?(?![a-z])|"
     r"workflow|工作流|规划能力|(?<![a-z])react(?![a-z])|plan[\s\-]and[\s\-]execute|"
     r"记忆(?!.*redis|.*缓存)|上下文压缩|上下文工程|context\s*engineering|"
     r"langchain|langgraph|autogpt|crewai|autogen|llamaindex|"
     r"(?<![a-z])a2a(?![a-z])|任务编排|自主决策|agentic|"
     r"tree[\s\-]of[\s\-]thoughts|意图识别"),

    ("evaluation", "评估与可观测", "evaluation.md",
     r"评估(?!.*风险)|评测|benchmark|(?<![a-z])eval(?![a-z])|"
     r"可观测|observability|监控告警|幻觉|hallucination|"
     r"成功率|ab\s*测试|a\s*/\s*b\s*(测试|对比)|人工抽查|打分|"
     r"效果.*衡量|指标.*(准确率|召回率)|观测性"),

    ("system_design", "系统设计与场景题", "system-design.md",
     r"如何设计|设计一个|设计.*系统|短链|秒杀|feed\s*流|朋友圈|"
     r"排行榜|附近的人|延迟任务|断点续传|大文件|防刷|"
     r"高并发|高可用|架构设计|技术方案|容量规划|灰度发布|"
     r"推送系统|即时通讯|im\s*系统|计数器.*设计"),

    # 放在 agent 之后：避免 ReAct（Agent 推理框架）被前端的 react 抢走
    ("frontend", "前端与全栈", "frontend.md",
     r"javascript|(?<![a-z])js(?![a-z])|typescript|(?<![a-z])vue(?![a-z])|"
     r"webpack|tailwind|(?<![a-z])css(?![a-z])|(?<![a-z])html(?![a-z])|"
     r"(?<![a-z])dom(?![a-z])|前端|浏览器|低代码|typeof|instanceof|"
     r"(?<![a-z])es6(?![a-z])|node\.?js|(?<![a-z])npm(?![a-z])|"
     r"组件(?!.*agent)|打包|样式|路由.*(hash|history)|响应式|"
     r"(?<![a-z])props(?![a-z])|状态管理|(?<![a-z])react(?![a-z]).*(组件|渲染|hook)|"
     r"\bui\b\s*组件|画布|可视化.*前端"),

    ("ai_product", "AI 产品与应用", "ai-product.md",
     r"ai\s*产品|ai\s*native|商业化|落地场景|行业.*趋势|创业|竞品|"
     r"用户增长|商业模式|(?<![a-z])to\s*b(?![a-z])|(?<![a-z])to\s*c(?![a-z])|"
     r"产品(经理|设计|定位|形态|壁垒)|ai\s*编程|copilot|cursor|"
     r"提示词.*产品|用户体验.*ai|ai\s*应用"),

    ("design_pattern", "设计模式 / 面向对象", "design-pattern.md",
     r"单例|工厂方法|工厂模式|简单工厂|抽象工厂|观察者模式|观察者|装饰器模式|装饰模式|"
     r"适配器模式|适配器|建造者|原型模式|代理模式|责任链|模板方法|饿汉|懒汉|"
     r"面向对象|封装性|继承.*多态|多态|抽象类|接口隔离|依赖倒置|单一职责|开闭原则|"
     r"里氏替换|迪米特|solid|高内聚|低耦合|设计模式|设计原则|组合复用|回调机制|"
     r"委托模式|门面模式|享元|桥接"),

    ("llm_basics", "大模型与 AI 基础概念", "llm-basics.md",
     r"大模型|(?<![a-z])llm(?![a-z])|transformer|自注意力|注意力机制|"
     r"(?<![a-z])moe(?![a-z])|mamba|状态空间|(?<![a-z])ssm(?![a-z])|"
     r"kv\s*cache|上下文窗口|长上下文|推理加速|量化|"
     r"投机采样|speculative|temperature|采样策略|解码|beam|"
     r"基座模型|开源模型|模型能力|涌现能力|语言模型|"
     r"因果掩码|自回归|位置编码|rope|归一化层|激活函数"),

    ("engineering", "工程落地与运维", "engineering.md",
     r"docker|(?<![a-z])k8s(?![a-z])|kubernetes|容器|ci\s*/\s*cd|"
     r"部署|(?<![a-z])git(?![a-z])|code\s*review|重构|单测|单元测试|"
     r"性能优化|排查|线上问题|故障|事故|压测|就绪探针|存活探针|"
     r"告警|日志|llmops|mlops|推理服务|服务化|网关|中间件"),

    ("behavioral", "行为面试 / 项目深挖 / HR", "behavioral.md",
     r"为什么(离职|跳槽|选择)|职业规划|优缺点|团队合作|冲突|"
     r"项目(深挖|难点|亮点|介绍)|(?<![a-z])hr(?![a-z])|薪资|期望|"
     r"自我介绍|反问|加班|压力|遇到的.*困难|如何(学习|成长)|"
     r"复盘|简历|面试技巧|怎么答|为什么想转"),
]

CATEGORY_FALLBACK = {
    "手撕算法": "algorithm",
    "行为与HR": "behavioral",
    "项目深挖": "behavioral",
    "后端八股（Go）": "go",
    "架构设计": "system_design",
    "工程落地": "engineering",
    "后端八股": "engineering",
    "概念基础": "general",
}

META = {k: (n, f) for k, n, f, _ in RULES}
META["general"] = ("其他 / 未分类", "general.md")


def blob(it):
    """只用题面 + 标签（不纳入答案正文，避免串味）。"""
    parts = [
        it.get("content", "") or "",
        " ".join(str(t) for t in (it.get("tags") or [])),
    ]
    return " ".join(parts).lower()


def classify(it):
    text = blob(it)
    for key, _name, _fn, pat in RULES:
        if re.search(pat, text):
            return key
    cat = it.get("category", "")
    return CATEGORY_FALLBACK.get(cat, "general")


# ---------------- Markdown 生成 ----------------

def esc(s):
    return (s or "").replace("\r\n", "\n").strip()


def render_item(it, idx):
    a = it.get("answer") or {}
    if not isinstance(a, dict):
        a = {"展开": str(a or "")}
    ans = esc(a.get("简版")) or esc(a.get("展开"))
    detail = esc(a.get("展开"))
    extra = []
    if esc(a.get("加分点")):
        extra.append(f"**加分点**\n\n{esc(a.get('加分点'))}")
    if esc(a.get("雷区")):
        extra.append(f"**雷区**\n\n{esc(a.get('雷区'))}")
    if esc(a.get("评分要点")):
        extra.append(f"**评分要点**\n\n{esc(a.get('评分要点'))}")
    if esc(it.get("sub_questions")):
        extra.append(f"**分点设问**\n\n{esc(it.get('sub_questions'))}")

    tags = [str(t) for t in (it.get("tags") or []) if str(t).strip()]
    tag_txt = " ".join(f"`{t}`" for t in tags) if tags else "（无）"
    src = esc(it.get("source")) or "（未标注）"
    qid = it.get("id", "")

    L = []
    L.append(f"## {idx}. {esc(it.get('content'))[:60]}")
    L.append("")
    L.append(f"> 原题 ID：`{qid}` ｜ 原分类：{it.get('category','')} ｜ 来源：{src}")
    L.append("")
    L.append("### 题干")
    L.append("")
    L.append(esc(it.get("content")) or "（空）")
    L.append("")
    L.append("### 选项")
    L.append("")
    L.append("（本题为问答题，原始题库无选项字段）")
    L.append("")
    L.append("### 答案")
    L.append("")
    L.append(ans or "（暂无）")
    L.append("")
    L.append("### 解析")
    L.append("")
    L.append(detail or "（暂无）")
    for e in extra:
        L.append("")
        L.append(e)
    L.append("")
    L.append("### 难度")
    L.append("")
    L.append(esc(it.get("difficulty")) or "（未标注）")
    L.append("")
    L.append("### 标签")
    L.append("")
    L.append(tag_txt)
    L.append("")
    L.append("---")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--bank", default=str(BANK))
    ap.add_argument("--out", default=str(OUTDIR))
    args = ap.parse_args()

    data = json.loads(Path(args.bank).read_text(encoding="utf-8"))
    items = data["items"]

    groups = defaultdict(list)
    for it in items:
        groups[classify(it)].append(it)

    order = [k for k, _, _, _ in RULES] + ["general"]
    print(f"总题数 {len(items)}\n")
    print(f"{'领域':<26}{'文件名':<26}{'题数':>6}{'占比':>8}")
    print("-" * 70)
    rows = []
    for k in order:
        if k not in groups:
            continue
        n = len(groups[k])
        name, fname = META[k]
        rows.append((fname, name, n))
        print(f"{name:<26}{fname:<26}{n:>6}{n/len(items)*100:>7.1f}%")
    print("-" * 70)
    print(f"{'合计':<26}{'':<26}{sum(len(v) for v in groups.values()):>6}")

    if not args.apply:
        print("\n[dry-run] 加 --apply 写文件")
        return

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    import time
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[write] 输出目录: {out}")
    for k in order:
        if k not in groups:
            continue
        name, fname = META[k]
        body = [f"# {name}",
                "",
                f"> 题目数量：**{len(groups[k])}** ｜ 生成时间：{stamp} ｜ "
                f"源文件：`{Path(args.bank).name}`",
                "",
                "本题库为问答题，「选项」一栏统一标注为不适用。",
                "",
                "---",
                ""]
        for i, it in enumerate(groups[k], 1):
            body.append(render_item(it, i))
        (out / fname).write_text("\n".join(body), encoding="utf-8")
        print(f"  {fname}  ({len(groups[k])} 题)")

    # 索引文件
    idx = ["# 题库领域索引", "", f"> 生成时间：{stamp} ｜ 总题数：{len(items)}", "",
           "| 文件名 | 领域 | 题目数量 |", "| --- | --- | ---: |"]
    for k in order:
        if k not in groups:
            continue
        name, fname = META[k]
        idx.append(f"| [{fname}](./{fname}) | {name} | {len(groups[k])} |")
    idx.append(f"| **合计** | | **{len(items)}** |")
    (out / "README.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    print(f"  README.md (索引)")
    print(f"\n[done] 共 {len([k for k in order if k in groups])} 个领域文件")


if __name__ == "__main__":
    main()
