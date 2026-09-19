"""Third-pass curation decisions for the non-AI-only domains.

The source corpus mixes scraped interview transcripts, article prose and
otherwise useful questions.  These declarations deliberately keep only
decisions that can be reproduced: malformed context-dependent prompts are
removed, clear duplicates are merged, and only unambiguous topics move across
domains.  ``curate_full_v2.py`` archives every affected source row before
writing the result.
"""

from __future__ import annotations

import re


# These are article narration, interview transcripts, incomplete code labels,
# or prompts whose object is missing.  A useful technical question is retained
# and rewritten where the missing context can be recovered safely instead.
EXTRA_DROP_IDS = {
    # Algorithm: non-algorithm article copy / transcript fragments.
    "q1730", "q1862", "q2274", "q2502", "q2508", "q2520", "q2778",
    "q2784", "q3031", "q3135", "q3232", "q3270", "q3377", "q3510",
    "q3524", "q3916",
    # Distributed: metadata and project-specific follow-up without a subject.
    "q0166",
    # Engineering: copied narration, a broken dialogue and undefined fields.
    "q1684", "q1751", "q1766", "q1771", "q1835", "q1888", "q1892",
    "q1980", "q2057", "q2065", "q2288", "q2304", "q2305", "q2515",
    "q2753", "q2880", "q2977", "q3046", "q3055", "q3083", "q3168",
    # Frontend: article references and project context with no defined object.
    "q1518", "q2360", "q2481", "q2602", "q2733", "q2736", "q3100",
    # General: prose headings, snippets and cross-turn questions that cannot
    # stand on their own.
    "q1605", "q1619", "q1624", "q1625", "q1631", "q1635", "q1640",
    "q1656", "q1657", "q1705", "q1715", "q1882", "q1884", "q1889",
    "q1992", "q2046", "q2047", "q2084", "q2115", "q2130", "q2133",
    "q2138", "q2240", "q2242", "q2255", "q2295", "q2297", "q2308",
    "q2501", "q2624", "q2648", "q2668", "q2687", "q2700", "q2705",
    "q2709", "q2717", "q2722", "q2723", "q2724", "q2735", "q2744",
    "q2747", "q2749", "q2756", "q2759", "q2773", "q2788", "q2851",
    "q2881", "q2906", "q2929", "q3004", "q3050", "q3054", "q3057",
    "q3062", "q3068", "q3070", "q3081", "q3089", "q3092", "q3110",
    "q3116", "q3122", "q3143", "q3144", "q3146", "q3234", "q3265",
    "q3324", "q3326", "q3408", "q3419", "q3452", "q3472", "q3525",
    "q3720", "q3765", "q3767", "q3773", "q3805", "q3806", "q3807",
    "q3810", "q3872", "q3873", "q3921", "q3937", "q3943",
    "q1355", "q2506", "q2524", "q2186", "q3699", "q0168", "q2179",
    "q2182", "q3620", "q1825", "q1826", "q3527",
    # Java / MySQL / OS / Redis: known unusable article or answer-status text.
    "q2213", "q3367", "q1636", "q3134", "q3178",
    # System-design article narration rather than a question.
    "q1685", "q1887", "q1988", "q2009", "q2021", "q2117", "q2118",
    "q2226", "q2280", "q2281", "q2286", "q2420", "q2813", "q3066",
    "q3069", "q3071", "q3075", "q3077", "q3085", "q3180", "q3184",
    "q3231", "q3627", "q3667", "q3672", "q3710", "q3822", "q3831",
    "q3837",
}


# A merge means that the target is the one canonical question.  The source
# answer is archived, so no detail is silently discarded.
EXTRA_MERGED_INTO = {
    "q0030": "q0099",
    "q0140": "q0085",
    "q1129": "q0033",
    "q3304": "q0806",
    "q4138": "q0035",
    "q1450": "q1929",
    "q2093": "q2106",
    "q2658": "q2746",
    "q2781": "q2691",
    "q3718": "q3820",
    "q3191": "q3753",
    "q3175": "q3182",
    "q3712": "q3816",
    "q1834": "q1833",
    "q2146": "q1452",
    "q1554": "q3224",
    "q2169": "q3224",
    "q3220": "q3224",
    "q3738": "q3722",
    "q4116": "q0986",
    "q4125": "q0986",
}


# Questions that clearly belong to another existing category.  Deliberately
# avoid moving vague interview transcripts; those are removed instead.
EXTRA_MOVE_TO = {
    # Algorithm was polluted by AI, frontend and infrastructure entries.
    "q1097": "agent", "q1134": "agent", "q1138": "agent",
    "q1507": "llm-posttraining", "q1514": "agent", "q1986": "mq",
    "q1990": "mq", "q2194": "rag", "q2197": "rag", "q2391": "frontend",
    "q2393": "frontend", "q2414": "os-network", "q2439": "frontend",
    "q2443": "frontend", "q2539": "frontend", "q2547": "frontend",
    "q2566": "frontend", "q2567": "frontend", "q2575": "frontend",
    "q2791": "frontend", "q2801": "os-network", "q2817": "frontend",
    "q2999": "rag", "q3312": "frontend", "q3359": "frontend",
    "q3382": "frontend", "q3383": "frontend", "q3387": "frontend",
    "q3493": "behavioral", "q3856": "rag", "q3862": "rag",
    "q3869": "llm-pretraining", "q3973": "agent", "q4044": "mysql",
    "q4056": "mysql", "q4062": "redis", "q4078": "os-network",
    # Agent / sandbox questions are not distributed-systems basics.
    "q0004": "agent", "q0018": "agent", "q0027": "agent", "q0028": "agent",
    "q0114": "agent", "q0128": "agent", "q0161": "agent", "q1182": "safety",
    "q1184": "safety", "q1185": "safety", "q1194": "safety", "q1196": "safety",
    "q1225": "agent", "q1237": "agent", "q1274": "rag", "q1301": "agent",
    "q1510": "agent", "q1735": "agent", "q2205": "agent", "q2787": "frontend",
    "q3953": "agent",
    # Engineering entries with a clear AI or people/process owner.
    "q0078": "agent", "q0109": "rag", "q1063": "llm-basics", "q1621": "evaluation",
    "q3366": "frontend", "q3626": "agent", "q3991": "behavioral",
    # A few clear frontend / agent entries that had landed in general.
    "q1820": "os-network", "q1875": "frontend", "q2376": "frontend",
    "q2380": "frontend", "q2383": "frontend", "q2387": "frontend",
    "q2412": "frontend", "q2416": "os-network", "q2437": "frontend",
    "q2438": "frontend", "q2454": "frontend", "q2461": "frontend",
    "q2485": "frontend", "q2543": "frontend", "q2584": "frontend",
    "q2611": "frontend", "q3131": "os-network", "q3361": "os-network",
    "q1929": "rag", "q2106": "agent", "q2746": "frontend",
    "q2691": "os-network", "q3820": "llm-basics", "q3753": "llm-basics",
    "q3532": "evaluation", "q3624": "evaluation",
    "q1961": "evaluation", "q2625": "behavioral", "q2171": "llm-basics",
    "q2173": "llm-basics", "q2175": "llm-basics", "q2979": "safety",
    "q3379": "mysql", "q1473": "agent", "q2036": "rag",
    # Go contained a frontend article and a RAG sizing duplicate.
    "q1833": "rag", "q2385": "frontend",
    # Java questions about AI framework selection belong with Agent work.
    "q1452": "agent", "q3529": "agent",
    # Redis carried a number of RAG/Agent questions, plus system-design prompts.
    "q0026": "agent", "q0111": "rag", "q1118": "agent", "q1152": "rag",
    "q1245": "prompt", "q1248": "agent", "q1250": "agent", "q1482": "agent",
    "q2833": "os-network", "q2864": "agent", "q3314": "os-network",
    "q3909": "llm-basics", "q3975": "agent", "q4120": "system-design",
    "q4121": "system-design",
    # System-design carried tutorials, frontend questions and LLM fundamentals.
    "q0019": "agent", "q0023": "safety", "q1423": "llm-basics", "q1511": "agent",
    "q1515": "agent", "q1879": "behavioral", "q2471": "frontend",
    "q2574": "design-pattern", "q2682": "frontend", "q2827": "frontend",
    "q2901": "agent", "q2913": "behavioral", "q3216": "llm-basics",
    "q3224": "llm-basics", "q3247": "frontend", "q3566": "behavioral",
    "q3583": "agent", "q3722": "llm-basics", "q3875": "llm-basics",
    "q3881": "llm-basics", "q3910": "llm-basics", "q3960": "ai-product",
}


# Engineering's numbered OS/network block was imported into the wrong file.
# Keep this range rule explicit rather than duplicating 180 IDs in MOVE_TO.
EXTRA_RANGE_MOVES = {
    "engineering": (("q0602", "q0847", "os-network"),),
}


# Fragments caught independently of their ID.  These patterns intentionally
# target narration and not ordinary technical terms such as "React" or
# "Docker", which could describe a valid standalone prompt.
EXTRA_FRAGMENT_RE = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^\s*(?:本文|本章|本节|下一[篇节]|前面|后面|上述|下文|如下图|下图|"
        r"这一[篇节条]|这部分|这对|这些步骤|这个方案|这种分块|这里瀑布流|"
        r"它们?|他们?|但是|同理|另外|其次|最后|第一|第二|第三|第四|我们来|"
        r"我来|推荐大家|所谓|只有当|一图|核心问题)",
        r"(?:老王|候选人|师兄).{0,80}(?:说|问|追问|继续|突然|开门见山|画风)",
        r"(?:本系列文章|上一[篇节]|下一节|#(?:秋招|面经|阿里巴巴|淘宝闪购))",
        r"^\s*(?:reconnectDelay|maxReconnectAttempts|tokenUsage|isStreaming|model)\s*\?:",
    )
]


EXTRA_TITLE_REWRITES = {
    "q3264": "如何用动态规划计算不同二叉搜索树的数量？",
    "q3440": "不使用日期库时，如何计算两个日期之间的天数？",
    "q3856": "如何用 MinHash 与 LSH 做海量文本近似去重？",
    "q3862": "检索模型如何利用难负样本提升召回与排序效果？",
    "q1507": "DPO 的优势、局限和适用场景是什么？何时需要在线强化学习？",
    "q2205": "生产环境如何用模型路由、优先级调度、熔断与降级治理不稳定的 LLM 服务？",
    "q2787": "文档预览服务何时应拆为微服务？它与微前端如何配合？",
    "q3366": "瀑布流布局中，如何在预加载与列高均衡之间取舍？",
    "q3626": "Agent 工具调用超时或陷入循环时，系统如何兜底？",
    "q2106": "如何定义一个适合 LLM 调用的工具？常见设计误区有哪些？",
    "q2746": "原生 H5 的优势与局限是什么？何时应引入框架或工具库？",
    "q1470": "面试中应如何有条理地回答项目经历问题？",
    "q0038": "如何在简历中体现 AI 项目已具备生产级能力，而非仅是 Demo？",
    "q1606": "面试中如何选择并讲述一个与岗位匹配的项目？",
    "q1891": "如何清晰说明项目性质、个人职责与非本人工作？",
    "q2627": "面试中被问及团队调薪制度时，如何专业回答？",
    "q2726": "面试中如何确认并回应团队的工作节奏与加班安排？",
    "q2699": "如何说明项目成员的分工、协作方式与个人贡献？",
    "q2730": "如何说明一个项目的周期、里程碑与个人投入？",
    "q1471": "团队为何要建设低代码平台？它适合哪些场景？",
    "q2694": "页面加载时如何减少布局抖动（CLS）？",
    "q2734": "低代码平台的典型用户有哪些？各自需要哪些能力？",
    "q2750": "低代码平台如何管理大量页面并支持设计态与运行态？",
    "q1961": "如何评估一个回答是否真正对用户有用（IsUse）？",
    "q1473": "Agent 如何在思考、行动与观察之间推进任务？",
    "q2036": "HNSW 与 IVF 如何分别缩小向量检索的搜索空间？",
    "q2625": "面试中如何说明团队的日常工作与迭代节奏？",
    "q2171": "Self-Attention 的计算过程是什么？",
    "q2173": "Multi-Head Attention 的原理和作用是什么？",
    "q2175": "神经网络训练中，前向传播、反向传播与优化器如何协同工作？",
    "q2979": "多个 Agent 执行者之间如何做资源与权限隔离？",
    "q3622": "Java 后端面试通常如何考察 JVM、并发与集合等基础能力？",
    "q2385": "defer 与 async 脚本的加载和执行时机有什么区别？",
    "q3379": "MySQL 中 DELETE、TRUNCATE 与 DROP 有什么区别？",
    "q3378": "编译器通常如何将源代码转换为可执行程序？",
    "q2277": "如何系统复盘一次面试并改进薄弱环节？",
    "q3186": "面试中遇到不会的问题后，如何建立有效的复盘与学习闭环？",
    "q3529": "Agent 开发中，Java 与 Python 各自适合哪些场景？",
    "q2471": "单页应用（SPA）与多页应用（MPA）有什么区别？如何选型？",
    "q2901": "为什么 Agent 系统需要感知、规划、行动与学习的闭环？",
    "q2913": "如何在简历中准确描述 Tool Manager 或 Router 的设计与贡献？",
    "q3216": "主流大模型架构有哪些？分别适合哪些任务？",
    "q3910": "为什么探索 MoE 架构？它相比稠密模型有哪些优势与代价？",
}


EXTRA_FIELD_FIXES = {
    "q1507": {
        "kaodian": "考察 DPO 与在线 RL 的机制和边界，避免把某一种对齐方法说成行业唯一主流。",
        "framework": "1) DPO 用偏好对直接优化策略、无需显式奖励模型与 PPO；2) 优势是离线训练简单稳定；3) 局限是依赖偏好数据覆盖和目标函数；4) 在线 RL 可利用可验证奖励与新采样，但成本和稳定性要求更高；5) 用任务、数据与评测决定组合。",
    },
    "q4062": {
        "kaodian": "考察过期键清理与 maxmemory 淘汰的区别，以及版本和配置会影响具体调度细节。",
        "framework": "1) 过期键通过惰性删除与主动过期周期协同处理；2) 主动周期按配置和过期压力自适应执行，不背固定抽样数字；3) maxmemory-policy 仅在内存达到上限时生效；4) 依据缓存价值和写入语义选策略；5) 用命中率、延迟和淘汰量验证。",
    },
    "q4078": {
        "kaodian": "考察 select、poll、epoll 的接口语义、数据结构和工作负载差异，避免把 epoll 简化成所有操作 O(1)。",
        "framework": "1) select/poll 由调用方每轮传入关注集合并扫描就绪项；2) epoll 将关注集合注册到内核并返回就绪事件；3) 比较描述符数量、活跃比例、跨平台和触发模式；4) 说明 LT/ET 的读取义务；5) 以压测而非口号选型。",
    },
}


EXTRA_OVERRIDES = {
    "q1507": {
        "answer": "DPO（Direct Preference Optimization）直接利用偏好对训练策略，避开了经典 RLHF 中单独训练奖励模型再进行 PPO 优化的整条链路。它通常更容易实现、训练更稳定、离线迭代成本更低，因此是重要的对齐基线和生产候选，而不是“主流不用”的方法。\n\n它的边界也很清楚：质量高度依赖偏好数据的覆盖、标注一致性和长度偏差控制；训练目标主要利用固定离线偏好，难以从部署后的新反馈或可验证环境奖励中主动探索。标准 DPO 还要选择参考策略和 KL/温度相关超参数，不能把它理解为没有约束的普通 SFT。\n\n当任务已有高质量偏好对、希望快速稳定地提升回答风格或指令遵循时，DPO 很合适；当任务存在可自动验证的奖励、需要在交互环境中持续探索或优化多步行为时，可评估拒绝采样、在线偏好优化或 GRPO/PPO 一类方法。实际选型应固定模型和数据版本，比较任务成功率、偏好胜率、安全回归、成本与稳定性，而不是按“DPO 或 RL 二选一”下结论。",
        "followup": "DPO 的偏好数据出现长度偏差或标注噪声时，如何发现并缓解？",
        "sources": [{"title": "Direct Preference Optimization", "url": "https://arxiv.org/abs/2305.18290"}],
    },
    "q4062": {
        "answer": "Redis 处理过期键通常是惰性删除与主动过期周期结合：访问一个带 TTL 的键时会检查并删除已过期键；后台也会从带过期时间的键中持续抽样清理，避免大量冷键长期占用内存。主动清理的频率、时间预算和抽样行为会随 Redis 版本与配置变化，不应把某个固定次数或抽样数量当作通用结论。\n\n内存淘汰是另一件事：只有设置了 `maxmemory` 且内存达到上限时，Redis 才按 `maxmemory-policy` 决定拒绝写入或淘汰键。常见策略包括 `noeviction`、`allkeys-lru`、`volatile-lru`、`allkeys-lfu`、`volatile-lfu`、`allkeys-random`、`volatile-random`、`volatile-ttl`，以及较新版本提供的 `allkeys-lrm` / `volatile-lrm`；其中 `volatile-*` 只考虑设置了 TTL 的键。\n\n选策略要看数据语义：会话或可重建缓存常用 allkeys LRU/LFU；必须保留的数据应避免依赖淘汰并设置容量保护。上线后观察 `evicted_keys`、过期键数量、命中率、内存碎片和 p99 延迟，必要时调整 TTL、容量或冷热分层。",
        "followup": "为什么 Redis 的 LRU/LFU 是近似策略，而不是维护一个严格全局顺序？",
        "sources": [{"title": "Redis key eviction", "url": "https://redis.io/docs/latest/develop/reference/eviction/"}],
    },
    "q4078": {
        "answer": "select、poll 和 epoll 都用于让一个线程等待多个文件描述符上的事件，但它们的注册和取回方式不同。select 与 poll 每次调用都由用户态传入关注集合，内核检查后再返回；应用仍需遍历集合找出就绪项。select 的集合大小通常受 `FD_SETSIZE` 等实现限制，poll 没有同样的位图上限，但两者在大量描述符、少量活跃连接时都需要线性扫描。\n\nepoll 先通过 `epoll_ctl` 把关注的描述符注册到内核，再用 `epoll_wait` 获取已就绪的事件列表，避免每轮重复传递整个集合。它通常更适合大量长连接且活跃比例低的 Linux 服务，但注册、删除、唤醒和用户态处理仍有成本，不能概括成“epoll 全部 O(1)”。\n\nepoll 的 LT（水平触发）在条件仍满足时会继续通知，较不容易漏事件；ET（边缘触发）只在状态变化时通知，通常要求描述符非阻塞并持续读/写到 `EAGAIN`。实际选择还要考虑平台、连接活跃度、代码复杂度和压测结果；跨平台库往往会在不同系统上选用相应机制。",
        "followup": "使用 ET 时，为什么必须把 socket 读到 EAGAIN？",
        "sources": [{"title": "Linux epoll(7)", "url": "https://man7.org/linux/man-pages/man7/epoll.7.html"}],
    },
    "q3379": {
        "answer": "在 MySQL 中，`DELETE`、`TRUNCATE TABLE` 和 `DROP TABLE` 的对象与事务语义不同。`DELETE` 是 DML：可以带 `WHERE`，按行删除；在 InnoDB 等支持事务的引擎中，它可在同一事务内回滚，并会执行相应的 DELETE 触发器。大量删除会产生较多 undo/redo 与索引维护开销。\n\n`TRUNCATE TABLE` 清空表中的全部数据但保留表定义。MySQL 将它作为 DDL 处理，通常隐式提交，不能像普通 `DELETE` 一样依赖事务回滚；它不能带 `WHERE`，一般也不会触发 DELETE 触发器。若存在外键引用等约束，是否可执行还要按约束关系和 MySQL 规则验证，不能把它当成无条件的快速删除。\n\n`DROP TABLE` 删除表对象本身，包括表定义及其中的数据；之后需要重新建表才能使用。生产操作前应确认库表、备份与权限，并在预发布环境验证。若只是清理满足条件的历史数据，用分批 `DELETE` 或分区管理通常更可控；若确实要清空整表，再评估 `TRUNCATE` 的锁、复制和回滚影响。",
        "followup": "大表历史数据清理时，为什么常用分区删除或分批 DELETE，而不是一次性 DELETE？",
        "sources": [{"title": "MySQL TRUNCATE TABLE", "url": "https://dev.mysql.com/doc/refman/8.4/en/truncate-table.html"}],
    },
}


# Fourth-pass full-corpus review.  These rules close the remaining confirmed
# scope collisions, context-free titles and factual errors found after the
# third-pass domains were merged into the same deterministic pipeline.
EXTRA_DROP_IDS.update({
    # The title has no comparison target; a generic answer cannot turn it into
    # a valid, self-contained interview question.
    "q3679",
})

EXTRA_MERGED_INTO.update({
    # Same topic, with the canonical question retaining the clearer scope.
    "q0808": "q0170",       # Reliable UDP.
    "q0119": "q1986",       # Redis Stream versus Kafka/RabbitMQ.
    "q4094": "q0213",       # Kafka message-loss prevention.
    "q4097": "q0214",       # Message backlog handling.
    "q4070": "q0634",       # IPC mechanisms.
    "q2608": "q3284",       # Vue two-way binding.
    "q3578": "q4059",       # Cache penetration/breakdown/avalanche.
    "q1915": "q1929",       # RAG chunking strategy.
    "q0865": "q0851",       # The 1/2/5/10 bridge puzzle is an example there.
    "q1758": "q1693",       # Agent versus Workflow.
    "q3689": "q1693",
    "q3812": "q3895",       # LoRA rank.
    "q3813": "q3896",       # LoRA target modules.
    "q3219": "q2171",       # Self-Attention computation.
    "q1445": "q1767",       # General engineering selection method.
    "q1736": "q1767",
    "q1504": "q3250",       # Performance investigation and optimization.
    "q1696": "q0001",       # Malformed prompt whose answer is Agent basics.
    "q1707": "q0001",
    "q2593": "q2545",       # Vue 2 versus Vue 3.
    "q3707": "q3693",       # Building credible experience without an internship.
    "q2068": "q3547",       # How to tell a real AI-project story.
    "q3372": "q2647",       # Choosing and presenting project highlights.
    "q2285": "q4013",       # MoE routing load balance.
    "q2496": "q2497",       # Duplicate Go GC overview with obsolete claims.
    "q3721": "q3842",       # Activation checkpointing.
    "q3874": "q1490",       # Encoder/decoder architecture distinction.
})

EXTRA_MOVE_TO.update({
    # A Go-GC block was accidentally imported into Java.
    "q0324": "go", "q0325": "go", "q0326": "go", "q0328": "go",
    "q0329": "go", "q0330": "go", "q0331": "go", "q0332": "go",
    "q0333": "go", "q0334": "go", "q0340": "go",
    "q2497": "go",
    # Clear topical owners for retained, formerly context-dependent prompts.
    "q1461": "llm-basics", "q1693": "agent", "q1697": "agent",
    "q1722": "agent", "q2716": "behavioral", "q2841": "behavioral",
    "q3370": "algorithm",
})

EXTRA_TITLE_REWRITES.update({
    "q0324": "Go 的垃圾回收如何通过三色标记与混合写屏障工作？",
    "q0612": "外部中断、CPU 异常与软件陷入（系统调用）有什么区别？",
    "q0613": "Linux 的 hardirq 与 softirq 有什么区别？为什么要拆分为两阶段？",
    "q0851": "四人过桥、最多两人同行且以慢者计时：如何求最优方案？",
    "q1461": "机器学习模型如何从数据中学习？常见学习范式有哪些？",
    "q1490": "Encoder-only、Decoder-only 与 Encoder-Decoder 架构有什么区别？",
    "q1693": "Agent 与 Workflow 的核心区别是什么？分别适用于哪些场景？",
    "q1697": "LLM、RAG 与 Agent 的本质区别和关系是什么？",
    "q1722": "LLM、Agent 与 MCP 分别是什么？三者有什么关系？",
    "q1741": "面试中遇到多个真实线上问题的连续追问时，如何结构化分析与回答？",
    "q1767": "实际工程中如何做技术选型？",
    "q2383": "CSS 中百分比单位（%）与 vw/vh 有什么区别？",
    "q2390": "JavaScript 基本类型为什么能访问属性和方法？装箱与拆箱机制是什么？",
    "q2497": "Go 的垃圾回收原理、优缺点与常见回收策略有哪些？",
    "q2545": "Vue 2 与 Vue 3 在响应式、组织方式和性能上有什么区别？",
    "q2623": "面试官质疑“就这？”时，如何重新讲清项目价值与技术深度？",
    "q2647": "如何在自我介绍中选择并讲清最有亮点的项目？",
    "q2716": "面试官问“你主要做哪一块？”时，如何介绍自己的技术主攻方向？",
    "q2841": "面试中遇到层层追问时，如何展示技术深度并应对知识边界？",
    "q3250": "项目中的性能优化如何定位、实施和验证？",
    "q3261": "刚入职时应如何快速熟悉项目、研发流程并建立成长闭环？",
    "q3370": "异或有哪些关键性质？如何用于找落单数和缺失数问题？",
    "q3693": "没有实习经历时，如何构建可验证的项目经历并争取机会？",
})

EXTRA_FIELD_FIXES.update({
    "q0324": {
        "kaodian": "考察 Go 垃圾回收的可达性判定、三色标记、混合写屏障，以及并发 GC 仍保留短暂停顿的原因。",
        "framework": "1) 从 goroutine 栈、全局变量等根开始做可达性分析；2) 用白、灰、黑三色描述标记队列；3) 并发标记期间用写屏障避免漏标；4) 准备和标记终止阶段仍有短暂停顿；5) 清扫回收不可达对象，并用 trace/基准观察实际代价。",
    },
    "q0612": {
        "kaodian": "区分异步外部中断、同步异常和程序显式进入内核的陷入/系统调用；避免把软件陷入与 Linux softirq 混为一谈。",
        "framework": "1) 按触发源和同步性区分三类事件；2) 外部设备中断的处理路径；3) 除零、缺页等 CPU 异常的处理与返回语义；4) 系统调用/陷入的作用及 x86-64 入口；5) 与 Linux softirq 的边界。",
    },
    "q0613": {
        "kaodian": "考察硬中断的快速响应、 softirq 的延后处理、并发与不可阻塞约束，以及 ksoftirqd 的边界。",
        "framework": "1) hardirq 的来源和最小化处理原则；2) softirq 是延后的内核工作而非用户态守护进程；3) pending softirq 的运行时机与 ksoftirqd；4) 并发和不可阻塞约束；5) tasklet、NAPI、workqueue 的适用边界。",
    },
    "q0851": {
        "kaodian": "考察四人过桥问题的通用建模、两种候选策略及最优性比较。",
    },
    "q1461": {
        "kaodian": "考察监督、无监督、自监督与强化学习等学习范式，以及模型通过优化参数获得能力的机制。",
    },
    "q1490": {
        "kaodian": "考察三类 Transformer 架构的注意力可见性、训练目标和适用任务，并区分任务表述统一与架构统一。",
        "framework": "1) Encoder-only 的双向表征和 MLM；2) Decoder-only 的因果掩码和自回归预测；3) Encoder-Decoder 的编码、交叉注意力与解码；4) 文本到文本/条件生成是任务统一，不等于架构相同；5) 按质量、延迟、成本和维护性选型。",
    },
    "q1693": {
        "kaodian": "考察 Agent 与 Workflow 在控制流、确定性、成本、可观测性和适用场景上的边界。",
    },
    "q1697": {
        "kaodian": "考察 LLM、RAG 与 Agent 的层次关系及各自解决的问题。",
    },
    "q1722": {
        "kaodian": "考察 LLM、Agent 与 MCP 的角色边界及其“模型—执行系统—连接协议”关系。",
    },
    "q1741": {
        "kaodian": "考察面对真实线上问题时澄清现象、提出假设、验证根因、止血与复盘的工程分析能力。",
    },
    "q1767": {
        "kaodian": "考察工程技术选型时识别业务约束、量化权衡、PoC 验证与演进设计的能力。",
    },
    "q2383": {
        "kaodian": "考察 CSS 百分比单位与视口单位的参照物及布局适用场景。",
    },
    "q2390": {
        "kaodian": "考察基本类型的属性访问、null/undefined 例外、临时包装与 ToPrimitive 语义。",
        "framework": "1) 基本类型与对象的区别；2) 属性访问时的 ToObject 语义；3) 临时包装为何不保留新属性；4) new String 等包装对象的陷阱；5) 对象转基本类型的 ToPrimitive。",
    },
    "q2497": {
        "kaodian": "考察 Go 的追踪式标记-清扫、可达性判定、并发与写屏障，以及它和引用计数、分代、压缩等策略的取舍。",
        "framework": "1) 从根可达性判定存活；2) 并发标记、写屏障、标记终止与清扫；3) 延迟、吞吐、碎片的权衡；4) Green Tea 改善扫描局部性而不是分代 GC；5) 与引用计数、复制、标记-整理、分代策略对比。",
    },
    "q2545": {
        "kaodian": "考察 Vue 2 与 Vue 3 在响应式、代码组织、编译优化和 TypeScript 支持上的核心变化。",
    },
    "q2623": {
        "kaodian": "考察面对项目质疑时，如何从背景、约束、决策、结果和复盘展示项目深度。",
    },
    "q2647": {
        "kaodian": "考察如何筛选与岗位相关、可验证且能深入展开的项目亮点，并以高信息密度表达。",
        "framework": "1) 先用一句话说明职责范围和岗位关联；2) 选择一个最能代表能力的真实项目；3) 按背景、约束、决策、结果、复盘展开；4) 数据说明口径和基线；5) 不把示例或他人成果说成自己的经历。",
    },
    "q2716": {
        "kaodian": "考察如何用“领域—代表项目—技术栈—职责与结果”清晰介绍技术主攻方向。",
    },
    "q2841": {
        "kaodian": "考察面对漏斗式技术追问时构建知识树、诚实说明边界并进行复盘的能力。",
    },
    "q3250": {
        "kaodian": "考察基于指标定位系统瓶颈，并按缓存、并发、批处理、异步与架构分层优化的能力。",
        "framework": "1) 定义用户可感知的目标和性能基线；2) 通过指标、trace、profile 与压测定位瓶颈；3) 用最窄的措施解决已证实的瓶颈；4) 校验一致性、容量、错误率与成本等副作用；5) 灰度验证并持续监控回归。",
    },
    "q3261": {
        "kaodian": "考察新人通过最小可运行、链路梳理、小需求闭环与持续反馈快速成长的路径。",
    },
    "q3370": {
        "kaodian": "考察异或的抵消性质，以及其在数组去重、找缺失数等算法题中的应用。",
    },
    "q3693": {
        "kaodian": "考察在缺少实习经历时，通过真实问题、可验证成果和诚实表达构建项目经历的能力。",
        "framework": "1) 区分项目经历与实习经历；2) 从真实问题定义有限且可交付的目标；3) 留下代码、测试、压测或复盘等可验证证据；4) 如实说明原型、离线实验或实际使用范围；5) 用复盘展示判断和成长。",
    },
    "q3842": {
        "kaodian": "考察激活值保存与反向重算的交换关系；区分显存节省、单步耗时和系统吞吐。",
        "framework": "1) 常规反向为何保存激活；2) checkpoint 只保留边界输入和必要状态，反向按需重算；3) 用计算换激活显存；4) 不等于单步一定加速；5) 以峰值显存、step time、token/s 联合评测。",
    },
})

EXTRA_OVERRIDES.update({
    "q0324": {
        "answer": "Go 的 GC 是追踪式标记-清扫：运行时从 goroutine 栈、全局变量和运行时根出发，能到达的堆对象视为存活，未标记对象可被回收。白、灰、黑是描述标记进度的抽象：白色尚未确认存活，灰色已发现但其引用尚未扫描完，黑色已完成扫描。\n\n现代 Go 在标记的大部分时间里与用户 goroutine 并发运行，但并不是“全程没有 STW”。准备和标记终止等阶段仍需要短暂停顿；暂停长度取决于堆、根集合和运行负载，不能承诺固定微秒数。并发标记期间，如果程序修改指针关系，混合写屏障会维护标记正确性，避免因引用变化漏标；随后清扫阶段回收不可达对象，通常可与程序执行交错进行。\n\n理解这道题的关键是：三色标记说明如何发现存活对象，写屏障解决并发修改时的正确性，短暂停顿与并发阶段共同平衡延迟和吞吐。调优应以 gctrace、profile 和真实负载为依据，而不是只背某个 Go 版本的历史说法。",
        "followup": "并发标记时，如果没有写屏障，黑色对象新增了对白色对象的引用，为什么可能漏标？",
        "sources": [{"title": "A Guide to the Go Garbage Collector", "url": "https://go.dev/doc/gc-guide"}],
    },
    "q0612": {
        "answer": "这些名称会随体系结构略有差异，面试时先按触发来源和同步性回答。外部中断通常由网卡、磁盘、定时器等设备异步提出，CPU 在合适边界进入内核的中断处理程序。CPU 异常由当前正在执行的指令同步触发，例如除零、缺页或非法指令；内核可能修复后重试、继续执行，或向进程报告错误。\n\n软件陷入/系统调用则是程序显式执行入口指令请求内核服务；在 x86-64 Linux 上通常走 `syscall`，`int 0x80` 主要是历史或兼容入口。三者都会保存现场并进入内核入口，但触发者、是否同步和返回语义不同。这里的“软件陷入”不能等同于 Linux softirq；后者是内核的延后处理机制。",
        "followup": "缺页异常为什么有时能在内核处理后回到原指令继续执行，有时却会让进程收到信号？",
        "sources": [{"title": "Linux x86-64 entry code", "url": "https://docs.kernel.org/6.2/x86/entry_64.html"}],
    },
    "q0613": {
        "answer": "hardirq 是设备或中断控制器送达的硬件中断上下文。处理程序应尽快确认或应答硬件、记录必要状态并安排可延后的工作，避免长时间占用中断上下文。\n\nsoftirq 是 Linux 的内核延后处理机制，不是“一个轮询标志位的守护进程”。硬中断处理返回、或内核准备返回用户态时，已标记 pending 的 softirq 可以被执行；工作过多时会由每 CPU 的 `ksoftirqd` 分担。普通内核配置下，softirq 仍不是可随意阻塞的普通线程上下文，并且同一种 softirq 可在多个 CPU 并发运行，因此需要正确的并发控制。网络收包、定时器等是典型场景；需要睡眠或较长处理时应转给 workqueue 等进程上下文机制。",
        "followup": "为什么硬中断处理程序通常只确认设备并把后续工作交给 softirq、NAPI 或 workqueue？",
        "sources": [{"title": "Linux kernel interrupt contexts", "url": "https://docs.kernel.org/kernel-hacking/hacking.html"}],
    },
    "q1490": {
        "answer": "三类架构的差异首先在注意力可见性和条件建模方式。Encoder-only（如 BERT）用双向自注意力学习输入表征，常配合掩码语言建模，适合分类、检索、抽取和句向量等理解任务。Decoder-only（如 GPT 系列）用因果掩码按 token 自回归预测，天然适合开放式生成、对话和代码。Encoder-Decoder（如 T5、BART）先编码输入，再让解码器通过交叉注意力生成输出，常用于翻译、摘要和文本到文本任务。\n\n把任务统一表述为文本到文本或条件 token 预测，不等于所有模型架构相同。T5/BART 是 Encoder-Decoder；GPT 类是 Decoder-only 的因果自回归模型，不会先由一个独立编码器把输入压成单一语义向量再解码。统一任务接口有助于复用训练、提示适配和服务能力，但不意味着它在所有任务上都优于 Encoder-only 或专用小模型。\n\nDecoder-only 常作为通用大模型主干，是因为训练目标和部署形式相对统一、易于扩展，并能借助提示和指令适配覆盖许多任务；但实际选型仍应比较目标质量、延迟、成本、数据和维护性。",
        "followup": "同一任务同时可用 Encoder-Decoder 和 Decoder-only 时，你会怎样设计公平的质量与成本对比？",
        "sources": [{"title": "T5: Text-to-Text Transfer Transformer", "url": "https://arxiv.org/abs/1910.10683"}, {"title": "GPT-2 documentation", "url": "https://huggingface.co/docs/transformers/v4.52.2/model_doc/gpt2"}],
    },
    "q1697": {
        "answer": "LLM 是生成或理解能力的模型底座；RAG 是在推理时检索外部资料并把证据放入上下文的技术方案；Agent 是围绕目标、状态、工具和反馈循环组织执行的系统。三者不在同一层级，因此不是互相替代的三个“产品类型”。\n\nRAG 不改变基座模型参数，主要帮助模型访问私有、最新或可引用的知识；它只有在检索到可靠证据并正确使用时才可能降低幻觉，不能保证答案正确。Agent 则决定是否检索、调用哪个工具、如何根据结果继续或停止。一个简单 RAG 可以完全是固定 Workflow，不需要 Agent；一个 Agent 也可以不使用 RAG；在复杂任务中，RAG 常只是 Agent 可调用的一个工具。\n\n选型先看问题：只需通用生成时直接调用 LLM；需要可更新、可追溯的知识时增加 RAG；步骤开放、需要多轮工具调用和反馈时再考虑 Agent，并为它设置权限、预算和终止条件。",
        "followup": "为什么“给 LLM 接上向量库”不必然等于构建了 Agent？",
    },
    "q1722": {
        "answer": "LLM 是根据输入生成或判断内容的模型；Agent 是把模型、任务状态、工具调用和反馈循环组合起来的执行系统；MCP（Model Context Protocol）是客户端与外部工具、资源和提示等能力交互的一套开放协议。可以把它们理解为“能力内核—应用执行层—连接接口”。\n\n这三者并不存在严格的必然依赖：一个 LLM 应用可以通过 MCP 访问工具而不构成 Agent；一个 Agent 也可以使用自定义 API 适配器而不使用 MCP。MCP 的价值在于减少每个客户端和每个工具之间重复定制的集成工作，但它不负责替 Agent 做规划、鉴权策略或业务权限决策。\n\n因此设计时应分别回答：模型负责什么推理，执行系统如何保存状态与限制行动，协议如何暴露能力并传递身份、权限和审计信息。",
        "followup": "为什么采用 MCP 后，工具的业务权限、输入校验和审计仍需要由应用层负责？",
    },
    "q2390": {
        "answer": "字符串、数字、布尔值、Symbol 和 BigInt 等基本类型在访问属性或方法时会按语言规范发生对象包装语义，因此 `'abc'.length` 和 `'abc'.toUpperCase()` 可以工作；`null` 与 `undefined` 不能这样访问，会抛出异常。\n\n把属性赋给基本类型后通常无法保留，是因为操作面对的是临时包装语义而非可持久修改的对象。引擎未必真的分配一个可观察的临时对象，不能把“创建后立即销毁”当作必须的实现细节。显式 `new String('x')` 得到的是对象，和基本字符串在 `===` 下不同，日常应避免。对象参与需要基本值的运算时会走 ToPrimitive，通常涉及 `valueOf` 或 `toString`，但具体顺序取决于上下文。",
        "followup": "为什么 `new String('x') === 'x'` 为 false，而 `String('x') === 'x'` 为 true？",
        "sources": [{"title": "ECMAScript ToObject and ToPrimitive", "url": "https://tc39.es/ecma262/multipage/abstract-operations.html#sec-toobject"}],
    },
    "q2497": {
        "answer": "Go 运行时采用追踪式标记-清扫 GC：从 goroutine 栈、全局变量和运行时根出发，能到达的堆对象为存活对象，不能到达的对象可回收，因此循环引用不会像纯引用计数那样泄漏。一次 GC 通常包含很短的准备或收尾停顿、与用户 goroutine 并发的标记，以及通常可并发或按需进行的清扫；写屏障用于保证并发标记时不漏掉引用。\n\n它的优点是自动管理内存并尽量缩短停顿；代价是扫描可达堆、写屏障和运行时元数据会消耗 CPU，且对象不搬迁，碎片只能由分配器缓解。Green Tea 改进的是标记/扫描的局部性和 CPU 可扩展性，不是“按对象年龄分代”的 GC；不要把它说成 Go 1.20 的分代实验。\n\n引用计数、复制、标记-整理和分代回收是其他常见策略，各自在实时性、碎片、吞吐和实现复杂度上取舍不同。排查或调优 Go 服务时，应先从实际的堆增长、分配率、暂停、CPU 和延迟数据入手，而不是仅按算法标签下结论。",
        "followup": "为什么非移动式标记-清扫 GC 更容易保留碎片？Go 的分配器如何缓解这个问题？",
        "sources": [{"title": "A Guide to the Go Garbage Collector", "url": "https://go.dev/doc/gc-guide"}, {"title": "Go Green Tea garbage collector", "url": "https://go.dev/blog/greenteagc"}],
    },
    "q2623": {
        "answer": "遇到质疑时，先不要用虚构的指标或堆技术名词硬撑。可以先澄清对方希望了解的是业务价值、个人贡献还是技术深度，然后用“背景—目标—约束—候选方案—决策—验证—复盘”重新组织回答。\n\n例如，先用一句话把项目从功能描述拉回问题和约束：说明谁受影响、原方案的瓶颈、自己负责的边界以及成功标准。接着只挑一个真实难点，讲清可选方案、为何放弃其中一些、最终方案带来的结果和代价。所有数字都应能说明时间窗口、样本量和基线；没有线上数据时明确说是原型或离线实验。\n\n如果项目确实规模不大，也可以展示小项目中的工程判断，例如如何定义边界、如何测试失败路径、怎样把一次问题复盘为可复用机制。关键不是把项目说得更大，而是让决策和证据经得起追问。",
        "followup": "当没有线上指标时，怎样用测试、压测或用户访谈为项目结果提供可信证据？",
    },
    "q2647": {
        "answer": "自我介绍不需要平均罗列所有项目。先用一句话说明自己的职责范围和与岗位的关系，再挑一个最相关、最能接受追问的真实项目展开；其余项目只作补充。\n\n展开时按“背景—目标—约束—决策—结果—复盘”组织：背景说明用户与问题，目标给出可验证标准，约束说明资源或兼容性边界，决策比较候选方案及代价，结果说明数据口径或可验证证据，最后说清未解决的风险。示例数字只能明确标为示意，不能当作个人经历；若没有线上数据，应如实说明原型、离线评测或开源使用情况。\n\n项目亮点的判断标准是岗位相关、个人贡献清楚、技术细节能讲透，并且有代码、测试、设计记录、压测或复盘可供验证。",
        "followup": "两个项目都相关时，如何根据面试岗位和可验证证据决定先讲哪一个？",
    },
    "q2841": {
        "answer": "层层追问通常是在考察你能否从定义走到原理、边界、取舍和真实工程影响，而不只是背结论。准备时可以为每个重要主题建立知识树：它是什么、为什么这样设计、怎样实现、在哪些条件下失效、有哪些替代方案，以及如何通过指标或实验验证。\n\n被问到知识边界时，先说清已确认的事实和证据；不确定的部分可以说明自己的推测及验证方法，而不是编造细节。答完后把问题按概念、实现、场景和复盘归档，补上原始文档、最小实验或源码阅读结果。\n\n这种做法适用于任何强调深度的技术面试；不应根据零散经历给某家公司贴固定的面试风格标签。",
        "followup": "一个“Redis 为什么快”的基础题，如何展开成定义、实现、边界与压测验证四层回答？",
    },
    "q3250": {
        "answer": "性能优化应是“度量—定位—假设—验证—固化”的闭环。先定义用户可感知的目标和基线，例如成功率、p95/p99、吞吐、资源成本与数据正确性；再用指标、分布式追踪、profile、日志和压测判断瓶颈是在 CPU、锁、IO、数据库、缓存、网络还是下游依赖，避免凭感觉改代码。\n\n方案应针对已证实的瓶颈选择最窄的一层：减少重复计算或序列化、修复索引和查询模式、批处理、连接复用、缓存、异步化、限流/背压或容量扩展。每种方案都有副作用，例如缓存的一致性、批处理的等待时间、并发的排队和异步化的失败补偿，因此需要同时检查错误率、正确性、容量和成本。\n\n最后在接近真实的负载下回归验证，灰度发布并持续监控。如果指标没有改善，就撤回假设并继续定位；一次优化不能只报告局部耗时下降，而要说明端到端结果和取舍。",
        "followup": "如果单个 SQL 已很快但接口 p99 仍高，你会怎样用 trace 和线程池指标继续定位？",
    },
    "q3261": {
        "answer": "新人最有效的起点是先建立“最小可运行”和一个可解释的业务链路：把本地环境、依赖、日志和一个简单接口跑通，再从入口追到数据存储和下游，画出链路图并向同事确认关键业务规则。这样提出的问题会更具体，也更容易得到高质量反馈。\n\n随后主动认领边界清晰的小需求或缺陷，完整走一遍需求澄清、开发、自测、评审、发布和观察流程。每周记录卡点、已验证的结论和下一步计划，并与导师或负责人定期校准优先级。\n\n目标不是短时间背完所有框架，而是持续形成“跑通—理解—交付—复盘”的闭环；遇到不确定的信息要先查文档、代码和日志，再带着假设请教他人。",
        "followup": "第一次接手一个陌生接口时，怎样把调用链、数据表、缓存和外部依赖画成可确认的链路图？",
    },
    "q3370": {
        "answer": "异或（XOR）按位比较：相同为 0、不同为 1。它满足 `a ^ a = 0`、`a ^ 0 = a`，并满足交换律和结合律，因此一组元素可以任意重排后让成对元素抵消。\n\n典型应用一：数组中只有一个数出现一次、其余出现两次时，把全部元素异或，结果就是落单数。应用二：有两个数各出现一次时，先得到它们的异或，再取其中任意一个为 1 的位把数组分组，两组分别异或即可。应用三：把 `0..n` 与数组元素一起异或，可找出缺失数。上述方法都可做到 O(n) 时间、O(1) 额外空间。\n\n异或也常用于状态翻转、校验和某些密码学构造，但“把数据和固定密钥做一次异或”本身不是安全加密方案；算法题里应优先说明它的抵消性质和适用前提。",
        "followup": "为什么用 `x & -x` 可以取出两个落单数异或结果中最低位的 1？",
    },
    "q3693": {
        "answer": "没有实习经历不等于没有项目经历。招聘方更容易从一个完整、真实、可验证的工程闭环判断能力：你发现了什么问题，目标和约束是什么，做过哪些取舍，如何验证结果，以及从中学到了什么。\n\n可以从身边真实的重复劳动、社团或课程需求、开源 issue、竞赛或已有项目的改进开始，把范围控制在能够交付和复盘的大小。保留代码提交、设计记录、测试、压测、演示或用户反馈等证据；若只是原型或离线实验，要明确其使用范围和数据口径，而不是虚构团队规模、线上流量或收益。\n\n面试时把项目讲成“背景—约束—决策—验证—复盘”，并主动说明自己的真实贡献和未解决风险。开源贡献、课程项目、Hackathon 或独立工具都可以成为材料，前提是经得起细节追问。",
        "followup": "个人项目没有真实用户流量时，可以怎样设计不夸大的验证方案？",
    },
    "q3842": {
        "answer": "梯度检查点（activation checkpointing）会把部分前向区域的中间激活不长期保存，只保留检查点边界所需的输入或状态；反向传播需要这些值时，再重跑该区域的前向计算。因此它本质上是“用额外计算换激活显存”，并不节省参数、梯度或优化器状态。\n\n它通常会增加单步计算量，不能宣称必然加速；但如果释放出的显存允许使用更大的 batch、更长序列，或避免 OOM 与低效的配置，端到端吞吐可能提高。不同分段方式、模型结构、随机算子和硬件都会改变具体的节省比例与耗时，不能把某个复杂度或固定百分比当作通用结论。\n\n实际使用时应同时比较峰值显存、每步耗时、token/s 和最终收敛，并确认重算时的随机状态和有状态算子语义正确。",
        "followup": "Checkpoint 包裹含 dropout 的模块时，为什么需要考虑随机状态的保存与重放？",
        "sources": [{"title": "PyTorch activation checkpointing", "url": "https://docs.pytorch.org/docs/2.14/checkpoint.html"}],
    },
})


# Seventh-pass project-wide review.  These decisions consolidate the final
# independently checked corpus audit: a question either has one stable scope,
# is moved to its actual subject, or is removed when its missing context cannot
# be reconstructed without inventing facts.  Keep this as a final overlay so
# it remains reproducible from the authored records and archives every change.
EXTRA_DROP_IDS.update({
    # Agent / LLM fragments or product gossip with no stable technical object.
    "q1142", "q2316", "q3061", "q3118", "q3417", "q3444", "q3612", "q3704",
    # A question about a missing system/object cannot be made self-contained.
    "q0363", "q0873", "q0874", "q0883", "q1598", "q1674", "q1686", "q1698",
    "q1931", "q1990", "q2293", "q2320", "q2322", "q2323", "q2327", "q2342",
    "q2344", "q2521", "q2578", "q2706", "q3067", "q3095", "q3099", "q3229",
    "q3230", "q3523", "q4132",
    # Truncated MySQL prose that has neither a query nor a schema to answer.
    "q0501", "q0521", "q0561", "q0585", "q3341", "q1774", "q1827",
})

EXTRA_MERGED_INTO.update({
    # Agent / AI: preserve the one question that already has the clearest
    # self-contained scope instead of keeping near-identical definitions.
    "q2856": "q2857", "q2866": "q3661", "q2904": "q0001", "q3421": "q3446",
    "q3461": "q1693", "q3480": "q1240", "q3568": "q4000", "q3589": "q0001",
    "q3944": "q154", "q3966": "q1218", "q3967": "q4000", "q3972": "q0094",
    "q1558": "q1373", "q1608": "q2910", "q1702": "q1524", "q1703": "q1690",
    "q1704": "q1524", "q2214": "q1373", "q2237": "q1689", "q2238": "q1689",
    "q2302": "q1689", "q3533": "q2251", "q3556": "q1385", "q3575": "q1549",
    "q3664": "q1441", "q3713": "q2173", "q3731": "q1063", "q3771": "q1061",
    "q1164": "q1051", "q3886": "q3779", "q3869": "q3206", "q3826": "q3616",
    "q1082": "q1507", "q1088": "q1507", "q1107": "q1238", "q1108": "q0076",
    "q1123": "q3895", "q1259": "q1859", "q1280": "q2997", "q3223": "q2252",
    "q1486": "q1161", "q1251": "q0076", "q1208": "q0013",
    # RAG: make the answer path unique rather than repeating the same retrieval
    # definition, index or optimisation advice in several wordings.
    "q0058": "q2999", "q0091": "q1098", "q0092": "q1072", "q0096": "q1275",
    "q0098": "q1072", "q1089": "q1929", "q1117": "q1097", "q1136": "q2975",
    "q1145": "q3090", "q1243": "q2074", "q1264": "q2194", "q1281": "q2197",
    "q1412": "q0121", "q1420": "q0121", "q1440": "q0121", "q1491": "q0121",
    "q1502": "q1072", "q1547": "q0121", "q1770": "q1722", "q1822": "q2074",
    "q1833": "q1929", "q1842": "q0109", "q1850": "q0111", "q1948": "q1946",
    "q1951": "q3090", "q1966": "q3090", "q2030": "q2033", "q2032": "q1548",
    "q2195": "q1760", "q3006": "q1274", "q3019": "q3486", "q3208": "q0121",
    "q3497": "q0111", "q3601": "q0014",
    # Operating system / networking: retain comparisons that contain the full
    # boundary and merge the shorthand duplicates into them.
    "q0303": "q0065", "q0631": "q0065", "q2400": "q0065", "q4072": "q0647",
    "q0649": "q4073", "q0650": "q4073", "q0668": "q4078", "q0715": "q4090",
    "q0748": "q3376", "q0750": "q3376", "q0798": "q4082", "q2691": "q4081",
    "q3361": "q0787",
    # Distributed systems and MQ duplicate clusters.
    "q4085": "q0739", "q0975": "q0061", "q4106": "q0061", "q0969": "q0173",
    "q4104": "q3748", "q0951": "q3748", "q3543": "q0437", "q0961": "q4108",
    "q4101": "q0216", "q4093": "q0226", "q4100": "q0229", "q4095": "q0215",
    "q4096": "q0217", "q0202": "q0201", "q0203": "q0201", "q4102": "q0201",
    "q0406": "q1986", "q0435": "q4067",
    # Redis / MySQL duplicate clusters.
    "q0381": "q0380", "q0415": "q4058", "q0419": "q4058", "q0424": "q4062",
    "q0425": "q4062", "q0426": "q4062", "q0433": "q3396", "q0442": "q4059",
    "q0445": "q4059", "q0371": "q1453", "q0472": "q3379", "q3281": "q4037",
    "q3398": "q4054", "q3590": "q3577", "q3576": "q4047", "q4051": "q3577",
    "q3655": "q3658", "q3947": "q156",
    # Java / Go / frontend duplicate clusters.
    "q0042": "q0324", "q2507": "q2574", "q0043": "q0337", "q0046": "q0142",
    "q0142": "q0274", "q0281": "q0040", "q0291": "q0040", "q0299": "q0066",
    "q0300": "q0066", "q0367": "q0067", "q2497": "q0324", "q1533": "q2385",
    "q2456": "q2561", "q2548": "q2609", "q2490": "q2615", "q2619": "q2394",
    "q2539": "q2393", "q3383": "q2439", "q2438": "q2437", "q2616": "q3297",
    "q2695": "q2665",
    # Product/behavioral/general questions with the same interview objective.
    "q0982": "q0171", "q0172": "q0983", "q0137": "q0088", "q2628": "q0088",
    "q2646": "q0088", "q2647": "q0088", "q2732": "q0088", "q2962": "q0088",
    "q2988": "q0088", "q3515": "q0088", "q3566": "q0088", "q3613": "q0088",
    "q1733": "q2811", "q2812": "q2811", "q2920": "q2811", "q3238": "q2811",
    "q3373": "q2811", "q1360": "q1396", "q1466": "q1396", "q1709": "q1396",
    "q1779": "q1396", "q1780": "q1396", "q1823": "q1396", "q1991": "q1396",
    "q1997": "q1396", "q2081": "q1396", "q1638": "q1637", "q1773": "q1772",
    "q1775": "q1772", "q1793": "q1792", "q1805": "q1792", "q1812": "q2098",
    "q1813": "q2098", "q2010": "q2024", "q2011": "q2024", "q2012": "q2024",
    "q2022": "q2024", "q2062": "q2061", "q2063": "q2061", "q2064": "q2061",
    "q2314": "q2313", "q1551": "q1587",
})

EXTRA_MOVE_TO.update({
    # Agent and AI product ownership.
    "q2857": "rag", "q2895": "ai-product", "q2902": "behavioral", "q3459": "behavioral",
    "q3547": "behavioral", "q3548": "agent", "q4003": "behavioral", "q3984": "safety",
    "q1092": "rag", "q1137": "evaluation", "q1179": "multimodal", "q1180": "multimodal",
    "q1351": "multimodal", "q1330": "safety", "q1350": "behavioral", "q0129": "agent",
    "q1837": "multimodal", "q1972": "system-design", "q3997": "evaluation",
    # OS/network content that arrived in other source files.
    "q3303": "os-network", "q0812": "os-network", "q4077": "os-network", "q0604": "os-network",
    "q1455": "os-network", "q1465": "os-network", "q1468": "os-network",
    # System / engineering / language / frontend ownership.
    "q1752": "engineering", "q3505": "java", "q0952": "system-design", "q0922": "system-design",
    "q1163": "llm-basics", "q3757": "llm-basics", "q3777": "llm-basics", "q1869": "frontend",
    "q3498": "rag", "q3506": "rag", "q1970": "system-design", "q2938": "engineering",
    "q0167": "engineering", "q1425": "agent", "q1971": "rag", "q2035": "rag",
    "q1975": "engineering", "q1981": "java", "q1982": "frontend", "q2428": "frontend",
    "q2580": "frontend", "q2572": "engineering", "q2707": "frontend", "q2708": "engineering",
    "q2719": "frontend", "q2913": "agent", "q3192": "agent", "q3460": "agent",
    "q3618": "agent", "q3198": "llm-basics", "q3925": "llm-basics", "q3902": "evaluation",
    "q3969": "agent", "q3970": "evaluation", "q3400": "engineering", "q3539": "engineering",
    "q3537": "java", "q1639": "frontend", "q2058": "frontend", "q2061": "frontend",
    "q2313": "llm-basics", "q1362": "behavioral", "q1364": "agent", "q1436": "engineering",
    "q1454": "llm-basics", "q1553": "llm-basics", "q2015": "llm-basics", "q2245": "llm-basics",
    "q2247": "llm-basics", "q2249": "llm-basics", "q2307": "llm-basics", "q1481": "system-design",
    "q1484": "engineering", "q1571": "agent", "q1572": "agent", "q1576": "agent",
    "q1604": "engineering", "q1699": "rag", "q1794": "rag", "q1925": "rag",
    "q2039": "rag", "q1519": "behavioral", "q1542": "behavioral", "q1750": "behavioral",
    "q1824": "behavioral", "q2088": "engineering", "q2244": "behavioral", "q2246": "behavioral",
    "q2346": "engineering",
    # Redis/MySQL misclassified records.
    "q4067": "redis", "q1965": "agent", "q0990": "engineering", "q0600": "go",
    "q0992": "engineering", "q156": "safety", "q3347": "system-design", "q3339": "system-design",
    "q1079": "evaluation", "q1140": "behavioral", "q1503": "behavioral", "q3619": "behavioral",
    "q1415": "frontend", "q1903": "frontend", "q2477": "frontend", "q2610": "frontend",
    "q3251": "frontend", "q3285": "frontend", "q3369": "frontend", "q3623": "java",
    "q1883": "evaluation", "q1969": "evaluation", "q2225": "agent", "q2898": "agent",
    "q3112": "agent", "q3454": "agent", "q3197": "llm-posttraining",
})

EXTRA_TITLE_REWRITES.update({
    "q0044": "Go 中 panic 与 recover 的作用、边界和常见误区是什么？",
    "q0099": "LRU 缓存的核心数据结构与 O(1) 读写如何实现？",
    "q0103": "何时选择 Redis Stream、托管消息队列或 Kafka？网关应承担哪些职责？",
    "q0167": "定时任务从生成、调度到触发执行应如何设计？",
    "q0171": "如何设计一个抢红包系统？随机金额、并发扣减和公平性如何处理？",
    "q0380": "Redis String 的内存占用为何与版本、位宽和分配器有关？如何正确评估？",
    "q0417": "哪些条件会触发 Redis RDB 快照？优雅关闭、全量同步和手动快照有何区别？",
    "q0438": "Redis 分布式锁为何需要 owner token？如何安全释放？",
    "q0439": "Redis Lua 脚本能保证何种原子性？边界和风险是什么？",
    "q0441": "Redis 分布式锁何时不足以保护强一致副作用？fencing token 与共识系统如何取舍？",
    "q0453": "Redis Cluster 的 16384 槽位如何工作？它与集群规模有什么关系？",
    "q0454": "Redis SCAN 的遍历保证、重复与新增/删除边界是什么？",
    "q0470": "SQL 中 IN 与 EXISTS 应如何依据语义、索引和执行计划选择？",
    "q0490": "为什么关系型数据库常用 B+ 树索引？它适合哪些查询模式？",
    "q0530": "InnoDB 自增主键的分配与 innodb_autoinc_lock_mode 如何影响并发插入？",
    "q0536": "事务的四种隔离级别分别解决什么问题？InnoDB 的默认隔离级别有什么边界？",
    "q0537": "InnoDB 的 SERIALIZABLE 隔离级别如何工作？代价是什么？",
    "q0543": "何时选择 READ COMMITTED 而非 InnoDB 默认的 REPEATABLE READ？",
    "q0590": "MySQL 异步复制、半同步复制与组复制的确认语义有什么区别？",
    "q0594": "何时需要对 MySQL 做分库分表或分区？应依据哪些容量与性能证据？",
    "q0596": "基于编码的分库分表路由有哪些约束？如何规划扩容与迁移？",
    "q0615": "Linux 从加电到用户空间服务启动的大致流程是什么？",
    "q0720": "DNS 名称解析的递归与迭代流程是什么？DNS 属于哪一层协议？",
    "q0721": "DNS 查询通常使用哪些传输协议？何时会使用 TCP、DoT 或 DoH？",
    "q0723": "服务端收到数据包后，操作系统如何按 socket 四元组或端口将其交付给正确进程？",
    "q0730": "为什么 ICMP ping 失败时，HTTP 请求仍可能成功？",
    "q0739": "URL 长度、HTTP 方法与安全性之间有哪些真实边界？",
    "q0767": "TLS 握手中的随机值、密钥交换材料分别解决什么问题？",
    "q0769": "TLS 1.3 如何实现 1-RTT 建连？0-RTT 有什么重放风险？",
    "q0770": "HTTPS 如何结合证书认证、密钥交换与对称记录保护？",
    "q0773": "HTTPS 会保护 URL 的哪些部分？哪些连接元数据仍可能暴露？",
    "q0775": "浏览器证书“安全”提示实际验证了什么？它不能证明什么？",
    "q0776": "自签名证书能否使用？私有 PKI、信任锚和公有证书分别适合什么场景？",
    "q0777": "RPC 的作用是什么？远程调用与本地调用有哪些可靠性边界？",
    "q0784": "Nginx 开源版支持哪些 upstream 负载均衡策略？哪些属于商业或第三方扩展？",
    "q0800": "出现大量 TIME_WAIT 时，应如何先定位角色、连接模式和风险，再决定治理措施？",
    "q0801": "服务端为何可能产生大量 TIME_WAIT？连接复用和协议角色如何影响？",
    "q0807": "实时音视频为何通常偏向 UDP？丢包、拥塞与回退如何处理？",
    "q0817": "MTU 与 MSS 分别是什么？TCP 分段和 IP 分片的关系是什么？",
    "q0830": "NAT/NAPT 是什么？它如何维护地址和端口映射？",
    "q0915": "Kubernetes HostPath 在路径不存在时如何受 type 配置影响？",
    "q0918": "Pod 如何使用 ServiceAccount 凭据访问 Kubernetes API Server？端口和 Service 如何配置？",
    "q0940": "Kubernetes Service 如何通过 EndpointSlice 与数据平面把流量转发给后端 Pod？",
    "q0958": "常见限流算法有哪些？Nginx limit_req 使用的是什么整形模型？",
    "q0964": "Raft 的基础选主和提交保证是什么？CheckQuorum/lease 属于什么扩展？",
    "q1059": "量化后的大模型显存如何估算？为什么 4-bit 权重仍不足以保证单卡可运行？",
    "q1190": "什么是沙箱逃逸？发生疑似逃逸时如何按事件响应流程处置并建立安全基线？",
    "q1212": "评测中哪些因素会导致模型产生不忠实回答或幻觉？如何分别诊断？",
    "q1320": "LayerNorm 与 BatchNorm 有何区别？为什么自回归 Transformer 常用 LayerNorm 或 RMSNorm？",
    "q1415": "浏览器的重排（layout/reflow）与重绘分别是什么？如何减少它们的代价？",
    "q1484": "如何审查 AI 生成代码的正确性、安全性、依赖与可维护性？",
    "q1566": "Qwen 的 MoE 型号为什么采用 MoE？它与稠密型号如何取舍？",
    "q1594": "如何分别评测数学推理、代码生成与软件工程任务？常用基准和指标是什么？",
    "q1883": "如何设计可复现的 Agent/LLM 评测？",
    "q1969": "AI 系统的单元测试、异常覆盖与质量门禁应如何设计？",
    "q2014": "模型规模、数据与训练预算如何共同影响能力和部署取舍？",
    "q2039": "HNSW 与 IVF 如何分别缩小向量检索的搜索空间？应如何比较？",
    "q2114": "System Prompt 或 Tool Definition 过大时，如何诊断和治理？",
    "q2136": "MCP 与 Google Agent Development Kit（ADK）的定位和边界有什么区别？",
    "q2141": "何时应使用强化学习而非仅 SFT 来提升 Agent 多步任务能力？收益和代价是什么？",
    "q2153": "工具调用应使用模型原生 Tool Calling，还是由 Prompt 约束结构化输出？",
    "q2162": "在 Java/Spring 系统中，何时选择 LangGraph4j 而不是 Python LangGraph？",
    "q2290": "猎鹿博弈为何不同于囚徒困境？合作、风险与均衡如何理解？",
    "q2292": "重复博弈为何可能支持合作？需要哪些收益与持续互动条件？",
    "q2343": "在 Go 驱动的 Agent 服务中，context.Context 与 LLM prompt 各自负责什么？",
    "q2389": "为什么 JavaScript 中 0.1 + 0.2 不严格等于 0.3？应如何处理浮点误差？",
    "q2392": "link 与 @import 引入 CSS 有什么区别？应如何选择？",
    "q2464": "CSS 隐藏、脱离文档流与真正移除 DOM 的状态、事件和性能差异是什么？",
    "q2514": "synchronized 与 ReentrantLock 如何比较和选型？",
    "q2654": "如何根据受校验的 Schema 将结构化描述安全地渲染为组件树？",
    "q2664": "前端框架如何把组件描述渲染并提交到真实 DOM？",
    "q2771": "常见 HTTP 请求头按路由、内容协商、认证、缓存和来源应如何理解？",
    "q2816": "前端组件如何在不破坏宿主对象语义的前提下进行包装与扩展？",
    "q2820": "如何按文档类型、目标用户和更新频率设计知识库的解析与检索流程？",
    "q2911": "如何设计 Agent Workflow 与 Controller 的职责边界？",
    "q2927": "如何从宿主形态、上下文、工具与安全边界比较自研 Coding Agent 与现成 Coding Agent？",
    "q2976": "子 Agent 如何实现？适用场景、隔离边界与代价是什么？",
    "q3014": "常见 Agent 协作模式有哪些？应如何按任务依赖和风险选择？",
    "q3138": "流式响应中 message 与 delta 等事件字段通常如何区分和处理？",
    "q3141": "哪些场景不适合使用流式响应？",
    "q3197": "指令微调与偏好优化相对基座模型主要改变哪些行为？如何评估？",
    "q3251": "three.js 场景的射线检测和加速结构应如何选择？",
    "q3344": "用户密码应如何安全存储？",
    "q3429": "如何设计直播/视频内容理解系统，并与图像 VLM 区分？",
    "q3482": "音频 codec 的帧率、RVQ 层数和码本大小如何影响质量、码率与延迟？",
    "q3496": "音视频模型 Bad Case 如何收集、归因、优化并防止整体回归？",
    "q3504": "Jedis、Lettuce、Redisson、Spring Data Redis 的定位与选择是什么？",
    "q3544": "前端应用如何设计可靠的 undo/redo？状态快照与命令模式如何取舍？",
    "q3585": "MCP 调用链有哪些安全与可靠性风险？如何治理？",
    "q3580": "JDK 7 与 JDK 8 的 PermGen/Metaspace 和常见 GC 机制有哪些差异？",
    "q3634": "如何对手机号、地址等低熵 PII 建立可查询且可轮换的安全索引？",
    "q3636": "单元测试在工程交付中解决什么问题？应覆盖哪些行为边界？",
    "q3637": "如何提升 AI 生成工程文档的事实准确性并评估？",
    "q3640": "RAG 请求变慢时，如何系统排查检索、重排、生成与依赖链路？",
    "q3652": "Coding Agent 如何进行上下文压缩，并保证任务可继续执行？",
    "q3703": "多智能体思想如何用于大模型推理？",
    "q3776": "为什么没有因果掩码的双向注意力模型不适合直接自回归生成？",
    "q3783": "FFN 与 Attention 的参数、FLOPs 和质量代价如何比较？",
    "q3844": "如何基于任务、数据、算力和部署约束选择微调基座模型？",
    "q3846": "如何将已有研究方向与 LLM 结合，并提出可验证的落地方案？",
    "q3854": "如何构建可复现、可审计的大模型预训练文本数据清洗管线？",
    "q3919": "如何设计受控、可复现的模型比较实验？",
    "q3968": "多业务场景中，四层意图识别可如何划分？",
    "q4002": "如何在给定系统架构和负载下设计缓存、并发与容量治理？",
    "q4020": "Java 中四种引用类型及其区别？ThreadLocal 的弱引用边界是什么？",
    "q4021": "Java 中常见 OutOfMemoryError 类型有哪些？如何排查？",
    "q4022": "synchronized 的实现与锁优化如何随 JDK 版本变化？",
    "q4029": "哪些条件会触发特定 JVM 收集器的 Full GC 或降级路径？如何诊断？",
    "q4122": "RocketMQ 延时消息在不同版本中如何实现？如何保证消费端幂等与防重？",
    "q4130": "已知 8 个球中有一个偏重，最少用天平称几次能找出它？",
    "q0877": "在连续转动的 24 小时区间内，时、分、秒针严格重合和时分针重合各多少次？",
})


# Sixth-pass full-corpus review.  These changes come from a second independent
# review of the complete rendered corpus.  Keep the decisions declarative so a
# later regeneration has exactly the same result and every removed source row
# remains recoverable from the review archive.
EXTRA_DROP_IDS.update({
    # Compound prompts, navigation copy, or fragments with no stable object.
    "q3484", "q3522", "q2992",
    "q1599", "q1755", "q2306", "q2324", "q2495", "q2528", "q2685",
    "q2757", "q3918",
})

EXTRA_MERGED_INTO.update({
    # Engineering context-window and Agent-cost repeats.
    "q1643": "q0078",
    "q2102": "q2113",
    "q3665": "q1458",
    "q3974": "q150",
    "q2986": "q2991",
    # General-domain excerpts that duplicate a canonical scoped question.
    "q1729": "q2106",
    "q2273": "q1929",
    "q2463": "q1537",
    "q3195": "q2171",
    "q3762": "q3821",
    "q3863": "q1063",
    "q3780": "q3876",
    "q3823": "q1545",
    "q3836": "q0011",
    "q3861": "q3860",
    "q3702": "q1492",
    "q3913": "q1492",
    # Cross-domain canonicalization.
    "q1266": "q1929",
    "q3945": "q154",
    "q0755": "q2417",
    "q0409": "q4063",
    "q0410": "q4063",
    "q1438": "q1391",
    "q2000": "q0081",
})

EXTRA_MOVE_TO.update({
    # Canonical targets whose original import domain was wrong.
    "q1391": "agent",
    "q1492": "llm-pretraining",
    "q154": "agent",
    "q2417": "os-network",
    "q4063": "redis",
    # Engineering topics imported into the catch-all engineering file.
    "q1896": "frontend",
    "q2158": "evaluation",
    "q2905": "evaluation",
    "q3890": "llm-basics",
    "q1737": "behavioral",
    "q3661": "evaluation",
    "q0939": "engineering",
    "q1183": "safety",
    "q1190": "safety",
    "q3485": "llm-pretraining",
    # MySQL had absorbed Agent, RAG and safety material.
    "q0101": "agent", "q0062": "agent", "q1095": "agent",
    "q1096": "agent", "q1139": "agent", "q2877": "agent",
    "q2100": "safety",
    "q0072": "rag", "q1530": "rag", "q2030": "rag", "q2043": "rag",
    # General-domain entries with a clear specialist owner.
    "q3056": "llm-basics", "q3751": "llm-basics", "q3877": "llm-basics",
    "q3879": "llm-basics", "q3791": "llm-basics", "q3848": "llm-basics",
    "q3849": "llm-basics", "q3853": "llm-basics", "q3479": "llm-basics",
    "q3782": "llm-basics", "q3789": "llm-basics", "q3798": "llm-basics",
    "q3799": "llm-pretraining", "q3923": "llm-pretraining",
    "q3926": "llm-pretraining", "q3924": "agent", "q3927": "system-design",
    "q3981": "evaluation", "q3090": "rag", "q3788": "engineering",
    # Self-contained rewrites from the general catch-all domain.
    "q1385": "agent", "q1416": "redis", "q1642": "evaluation",
    "q1670": "os-network", "q1728": "agent", "q1754": "prompt",
    "q1760": "rag", "q1790": "agent", "q1859": "rag", "q1937": "rag",
    "q1941": "agent", "q1962": "llm-basics", "q2250": "llm-pretraining",
    "q2251": "agent", "q2252": "llm-posttraining", "q2265": "behavioral",
    "q2595": "frontend", "q2665": "frontend", "q2670": "frontend",
    "q2673": "os-network", "q2689": "frontend", "q2771": "os-network",
    "q2865": "evaluation", "q3114": "llm-basics", "q3149": "ai-product",
    "q3161": "behavioral",
})

EXTRA_TITLE_REWRITES.update({
    "q1896": "Composition API 相比 Options API 的工程收益与适用边界是什么？",
    "q2158": "如何观测和评估上下文压缩的效果？",
    "q2905": "LLMOps 覆盖哪些治理能力？如何按需求选型？",
    "q3137": "为什么用 curl 验证 SSE/流式响应时常需加 -N（--no-buffer）？",
    "q3890": "为什么同一文本在不同模型 tokenizer 下 Token 数不同？如何实测？",
    "q1737": "面试中如何用量化收益、成本与备选方案说明技术取舍？",
    "q3661": "如何为 Agent 工具调用设计日志、指标、追踪与审计？",
    "q0939": "Kubernetes 集群内应用如何通过 Service 访问外部数据库、缓存等服务？",
    "q2877": "带规划工作流的 Coding Agent 如何从需求澄清到分步实施？",
    "q3056": "FlashAttention-2 如何优化 Transformer 注意力？接入模型时需要验证哪些前提？",
    "q3751": "Self-Attention 与 Multi-Head Attention 有什么区别？",
    "q3877": "为什么 Transformer 通常使用缩放点积注意力？它与加法注意力有什么区别？",
    "q3879": "Multi-Head Attention 的“多头”表示什么？如何理解并验证各头的作用？",
    "q3791": "Transformer 的上下文表示与 RNN 的递归隐状态有什么本质区别？",
    "q3848": "Post-LN、Pre-LN 与 LLaMA 式 RMSNorm+RoPE 设计为何演进？",
    "q3849": "更换 tokenizer 时，词表、Embedding 和输出层应如何迁移与验证？",
    "q3799": "对比学习与难负例挖掘如何提升表征学习？",
    "q3923": "训练研究中为什么要控制样本量和训练步数？",
    "q3926": "Pairwise/Triplet Ranking 训练与 Pointwise 训练有何区别？",
    "q3853": "训练中如何设置和验证学习率调度，而不是只依赖训练框架默认值？",
    "q3924": "Agent 如何针对专业场景设计定制任务、工具链和评估闭环？",
    "q3927": "智能运维（AIOps）平台通常解决哪些问题？核心架构是什么？",
    "q3981": "RAG/检索评测中的金标相关文档应由谁、按什么流程标注？",
    "q3090": "Agentic RAG 与传统 RAG 的流程、控制权和适用场景有何区别？",
    "q3479": "Transformer 解码器层中注意力投影与 FFN 的参数量/FLOPs 比例如何估算？",
    "q3788": "数据分块（chunking）在什么访问模式下能减少 I/O？有哪些代价？",
    "q1385": "Agent 的工具/技能如何实现渐进式披露（按需加载 Schema）？",
    "q1416": "Redis 从节点如何通过 replication ID 和 offset 判断与主节点的同步状态？",
    "q1642": "Harness 测试中返回值看似正确却断言失败时，如何定位解析、断言和生命周期问题？",
    "q1670": "如何在不中断登录的前提下迁移 JWT/旧会话凭证？",
    "q1728": "对话状态跟踪（DST）有哪些方法？如何选型？",
    "q1754": "如何让 LLM 稳定遵循固定输出格式？",
    "q1760": "查询改写如何把口语化、信息不完整的问题转为可检索 Query？",
    "q1790": "如何把多种自然语言说法归一到同一业务意图？",
    "q1859": "RAG 与微调分别解决什么问题？如何选型和组合？",
    "q1937": "RAG 如何从文档中定位与问题最相关的段落？",
    "q1941": "Agent 如何基于错误码注册表、日志和上下文解释错误并给出下一步动作？",
    "q1962": "关系网络和表格数据分别适合哪些机器学习方法？",
    "q2250": "训练中如何使用权重衰减、学习率与调度策略？",
    "q2251": "LLM/Agent 链路中如何把模型输出格式化并校验为结构化实例？",
    "q2252": "大模型常见微调方法有哪些？如何选型？",
    "q2265": "面试中记不清指标时，如何诚实说明并展示估算/验证能力？",
    "q2595": "Vue created 中发起异步请求后，回调里何时能访问组件状态和 DOM？",
    "q2665": "异步获取内容高度未知时，前端如何稳定布局并避免 CLS？",
    "q2670": "React Hooks 如何在状态更新后触发重新渲染？",
    "q2673": "HTTP/2 如何在一条连接上并发传输多个请求？",
    "q2689": "Promise 的状态机、链式调用与错误传播机制是什么？",
    "q2771": "HTTP 请求中常见请求头有哪些？各自作用是什么？",
    "q2865": "为什么 LLM 可观测平台不能替代业务端到端质量验证？",
    "q3114": "LLM 的参数化知识、上下文知识与外部知识分别如何存储和使用？",
    "q3149": "AI 产品的收入与利润通常由哪些业务和技术因素共同决定？",
    "q3161": "面试中如何证明自己在生产环境使用 AI 编程并完成工程化验证？",
    "q3782": "规则/模板系统与生成式模型在表达能力、可控性和适用场景上有何区别？",
    "q3789": "DeepSeek-V3/R1 如何通过 MoE、MLA、FP8 等技术平衡性能与成本？",
    "q3798": "上下文相关词表示如何缓解多义词问题？它与静态词向量有何区别？",
})

EXTRA_TITLE_REWRITES.update({
    "q1530": "RAG 索引如何按数据、查询和更新需求设计与优化？",
    "q2030": "常见向量索引算法有哪些？它们如何在召回、延迟与内存之间取舍？",
    "q2043": "RAG 项目如何根据数据规模、过滤与更新需求选择向量索引？",
})

EXTRA_OVERRIDES.update({
    "q1896": {
        "kaodian": "考察 Composition API 与 Options API 的组织方式、复用能力、类型体验和迁移边界。",
        "framework": "1) 先说明两者都能实现同一组件能力；2) 比较按选项组织与按业务逻辑组织；3) 解释 composable 的复用和 TypeScript 推断；4) 说明大型组件、跨组件逻辑与团队约定；5) 给出渐进迁移和测试策略。",
        "answer": "Composition API 与 Options API 的差异主要在代码组织和复用方式，不是运行能力的高低。Options API 按 `data`、`methods`、`computed` 等选项组织，简单组件和熟悉 Vue 2 的团队通常更易读；Composition API 可以把同一个业务能力的状态、计算和副作用放在一个 composable 或同一段 setup 逻辑中，复杂组件拆分和跨组件复用更直接。\n\nComposition API 对 TypeScript 的推断、泛型封装和依赖显式表达通常更友好，但也可能因把逻辑任意拆散而变得难读。是否采用应看组件复杂度、复用频率、团队规范和已有代码，而不是把它当作性能优化。\n\n迁移可以从新增复杂组件或独立逻辑开始，保留现有 Options API，复用相同的测试和组件边界；不要为了风格统一一次性重写稳定页面。",
        "followup": "什么时候一个简单展示组件仍更适合 Options API？",
    },
    "q2158": {
        "kaodian": "考察上下文压缩是否同时用成本、信息保真和任务质量三类指标验证。",
        "framework": "1) 固定模型、输入和目标输出预算；2) 记录压缩前后 token、延迟与成本；3) 检查关键实体、决策和未完成事项的保留；4) 用长任务回归集比较成功率与错误类型；5) 对异常样本可回放、可追踪并做好脱敏。",
        "answer": "上下文压缩不能只看 token 下降。首先记录压缩前后的输入 token、输出预留、压缩耗时、缓存命中和总成本，确认它确实释放了可用预算；再检查服务名、时间、ID、用户约束、已执行动作等关键事实是否被保留。\n\n更重要的是在固定任务集上比较压缩前后的任务成功率、工具参数正确率、引用/事实错误和需要反复澄清的比例。把失败按“漏保留事实、摘要失真、检索未命中、模型未遵循”分类，才能知道该改摘要、状态结构还是检索。\n\n日志应关联会话和版本，但工具参数、用户内容和摘要要按权限脱敏、设置保留期，并支持对单个 bad case 回放，而不是把完整敏感上下文长期落盘。",
        "followup": "怎样设计一个能暴露“摘要漏掉关键约束”的长对话回归集？",
    },
    "q2905": {
        "kaodian": "考察把 LLMOps 拆成可验证的治理能力，而非按厂商或热度给工具排名。",
        "framework": "1) 盘点模型、Prompt、数据和评测版本；2) 覆盖部署、路由、回退与容量；3) 建立质量、成本、延迟和安全观测；4) 加入权限、审计和发布治理；5) 按现有栈、数据边界和缺口做试点选型。",
        "answer": "LLMOps 是让模型应用可重复发布、可观测和可治理的一组能力，而不等同于某个产品。基础能力通常包括模型、Prompt、检索配置和评测集版本管理；离线/线上评测与回归；部署、路由、限流、回退和容量管理；token 成本、延迟、错误、工具调用与业务质量观测；以及权限、数据脱敏、审计和变更审批。\n\n选型先列出硬约束：数据能否出域、现有 tracing/CI/模型网关、是否需要自部署、团队的标注与运维能力、合规要求和预算。缺什么补什么：已有 OpenTelemetry 时可能只需补评测与 Prompt 版本；高风险业务则优先审计、审批和回归门禁。\n\n应在真实链路上试运行，检查接入开销、数据完整性、查询能力和告警是否真正帮助定位问题；不要用“主流”或排行榜代替需求分析。",
        "followup": "已有通用 APM 时，LLMOps 还需要补哪些模型特有的可观测字段？",
    },
    "q3137": {
        "kaodian": "考察客户端输出缓冲、服务端 flush 和中间代理缓冲是三个独立问题。",
        "framework": "1) 说明 `-N/--no-buffer` 禁用 curl 的输出缓冲；2) 区分它与 HTTP 流式传输本身；3) 检查 SSE 响应头、服务端 flush 和代理配置；4) 用带时间戳的最小流式接口复现；5) 不把一次命令行现象误判为服务端完整响应。",
        "answer": "`curl -N`（`--no-buffer`）会关闭 curl 自己对标准输出的缓冲，因此在终端验证 SSE 或分块响应时，常能更快看到已经到达的字节。它不是让服务端“变成流式”，也不保证端到端没有任何缓冲。\n\n不加 `-N` 时，curl 可能等输出缓冲区积累到一定程度才打印；它不必然等到整个响应结束。相反，即使加了 `-N`，应用没有 flush、反向代理/CDN 缓冲响应、压缩或管道命令再次缓冲，终端仍可能看不到实时增量。\n\n排查时使用一个定时发送事件的最小接口，检查 `Content-Type: text/event-stream`、连接/缓存相关响应头和代理配置，并给每个事件加时间戳；这样能分别定位是服务端、网络中间层还是客户端显示造成的延迟。",
        "followup": "为什么 SSE 服务通常还要检查反向代理的响应缓冲配置？",
    },
    "q3890": {
        "kaodian": "考察 tokenizer 由词表、预切分和编码规则共同决定，以及以目标 API 实测 token 的方法。",
        "framework": "1) 解释 BPE、Unigram 等算法和词表不同会改变切分；2) 指出中文、空格、标点、代码和特殊 token 的影响；3) 用目标模型 tokenizer 计算完整请求；4) 以服务端 usage 为最终计费核对；5) 避免使用跨模型固定倍数估算。",
        "answer": "同一文本在不同模型中 token 数不同，是因为模型的词表、预切分规则、合并算法和特殊 token 不同。中文、空格、标点、代码片段以及聊天模板都会放大这种差异，因此不能用“中文一定是几个字符一个 token”或某个模型之间的固定倍数做预算。\n\n离线估算时，应使用目标模型或供应商公开的 tokenizer，并把 system prompt、消息角色、工具 schema、图片/附件占位和预留输出一并计算。真正发起请求后，以 API 返回的 input/output token usage 作为计费与容量的事实来源，因为服务端序列化方式可能与本地近似工具不同。\n\n调优时记录模型版本和完整请求形态，比较不同 prompt、工具描述和检索片段对 token 的贡献；不要只对用户正文计数。",
        "followup": "为什么只用用户输入文本估算 token，常会低估 Agent 请求的实际成本？",
    },
    "q1737": {
        "kaodian": "考察能否用可核验的基线、取舍和结果说明工程决策，而不是罗列技术名词。",
        "framework": "1) 交代目标、约束和基线；2) 列出至少两个可行方案；3) 比较质量、延迟、成本、风险和维护性；4) 说明决策与个人贡献；5) 给出数据口径、验证方式和未解决问题。",
        "answer": "说明技术取舍时，先把问题和约束说清楚：例如目标是降低 p99 延迟、预算受限，还是必须满足数据隔离。然后列出实际比较过的方案，说明每个方案对质量、开发周期、运行成本、风险和维护复杂度的影响，而不是只说“效果更好”。\n\n结果应有可核验口径：基线是什么、观察窗口多长、样本量或压测条件是什么、收益和新增成本分别是多少。没有线上数据时，诚实说明是离线评测、压测或原型结果，并说明下一步如何验证。\n\n面试中最有价值的是你为什么排除了某个看似更先进的方案、如何控制剩余风险，以及你负责了哪一部分决策和落地。",
        "followup": "如果方案 A 更快但一致性风险更高，你会如何组织一段可追问的回答？",
    },
    "q3661": {
        "kaodian": "考察 Agent 工具调用的可追踪性、可审计性与隐私/权限约束如何一起设计。",
        "framework": "1) 用 request、trace 和 tool span 关联一次任务；2) 记录工具版本、授权主体、输入摘要、结果状态和耗时；3) 统计成功率、重试、错误、token 与成本；4) 对高风险动作留不可抵赖审计；5) 对敏感字段脱敏、最小化保留并设置告警。",
        "answer": "每次 Agent 任务应有 request/trace ID，并把每次模型调用、规划、工具调用和人工确认作为关联 span。工具 span 至少记录工具名称和版本、调用主体及权限、输入的安全摘要或哈希、结果状态、错误分类、重试次数、耗时和成本；不要默认把完整密钥、个人数据或 SQL 结果写入日志。\n\n监控关注成功率、超时、拒绝率、重复调用、循环步数、参数校验失败、下游错误和端到端任务质量。高风险写操作还应记录批准人、预览摘要、执行前置条件和不可篡改的审计事件，以支持事后追责与恢复。\n\n日志、指标和 trace 的价值是缩小定位范围，不能替代回归评测；需要将线上 bad case 脱敏回流到评测集，并为异常成本、权限拒绝和失败率建立告警。",
        "followup": "工具参数中含个人数据时，怎样让调试信息仍能用于聚合分析？",
    },
    "q0939": {
        "kaodian": "考察 Kubernetes 内外部服务发现、无 selector Service/EndpointSlice、TLS 与网络边界。",
        "framework": "1) 先确认外部服务的 DNS、端口、可达性与所有权；2) 选择直接 DNS、ExternalName 或无 selector Service 加 EndpointSlice；3) 区分名称抽象与真实代理转发；4) 配置 TLS、凭证、超时和连接池；5) 用 NetworkPolicy、监控和故障演练验证。",
        "answer": "集群内应用访问外部数据库或缓存，最简单的方式通常是直接使用受管的 DNS 名称和端口，并由应用配置 TLS、认证、超时和连接池。如果希望给外部依赖提供稳定的集群内名称，可以使用 `ExternalName` Service（DNS CNAME 方式），或创建不带 selector 的 Service 并维护对应的 EndpointSlice。\n\n无 selector Service 的价值是提供 Kubernetes DNS 和端口抽象；它不会自动把外部数据库变成由 kube-proxy 转发的工作负载。ExternalName 也只是 DNS 别名，不能替代网络连通性、证书校验或数据库凭证治理。\n\n上线前要验证 VPC/防火墙、NetworkPolicy、DNS 解析、故障转移和连接上限，并在观测中区分应用连接池耗尽、网络超时和外部服务本身故障。",
        "followup": "什么情况下应该直接使用外部 DNS，而不是再创建 Kubernetes Service 抽象？",
    },
    "q1183": {
        "kaodian": "考察按威胁模型选择 Agent 代码执行隔离，而非把某一种运行时当作绝对安全。",
        "framework": "1) 定义不可信代码、数据、网络和多租户威胁；2) 比较进程、容器、gVisor、MicroVM、WASM 的隔离边界与冷启动；3) 加最小权限、资源配额和网络出口控制；4) 做一次性环境、镜像供应链与秘密管理；5) 通过逃逸演练和审计持续验证。",
        "answer": "隔离选型应从威胁模型出发。普通进程隔离启动快但共享宿主内核，适合可信或低风险任务；容器提供文件系统和 namespace/cgroup 边界，但仍依赖宿主内核；gVisor 通过用户态内核接口缩小攻击面；MicroVM 提供更强的虚拟化边界但启动与资源成本更高；WASM 的能力模型适合受限计算，但不能自动覆盖所有原生依赖场景。\n\n对不可信 Agent 生成代码，通常需要一次性执行环境、只读或无宿主挂载、最小镜像、CPU/内存/时间/进程数配额、默认拒绝网络出口、按域名或代理白名单放行，并把密钥放在短期、按任务授权的通道中。\n\n不要只比较启动毫秒数；还应验证多租户隔离、文件/网络权限、镜像供应链、日志审计、故障清理和在真实攻击样本下的逃逸抵抗能力。",
        "followup": "为什么容器的资源限制并不能替代对网络出口和宿主挂载的限制？",
    },
    "q1190": {
        "kaodian": "考察沙箱逃逸的检测、隔离、取证、修复和恢复闭环，而不是背固定条目。",
        "framework": "1) 明确逃逸信号和告警分级；2) 先隔离受影响任务/节点并撤销凭证；3) 保全日志、镜像和网络证据；4) 修补根因、轮换秘密并重建可信环境；5) 复盘检测缺口、权限和发布流程。",
        "answer": "沙箱逃逸是指受限代码突破预期的文件、进程、网络或宿主边界。怀疑发生时，首要目标是限制影响面：停止或隔离相关任务和节点、阻断网络出口、撤销任务凭证和临时令牌，并按预案通知安全响应人员。\n\n在不破坏证据的前提下保全审计日志、进程/网络信息、镜像摘要和任务输入输出，判断是否访问了宿主、其他租户或外部系统。随后修补漏洞或错误配置，轮换可能暴露的密钥，从可信镜像重新创建环境，并对受影响数据和下游操作做对账。\n\n长期基线包括最小权限、默认拒绝网络、不可写宿主挂载、一次性环境、资源上限、镜像签名/扫描、运行时审计和定期逃逸演练。具体处置顺序应服从组织的事件响应流程和业务恢复要求。",
        "followup": "为什么事件处置中要同时冻结凭证和保留运行时证据？",
    },
    "q3485": {
        "kaodian": "考察训练 OOM 时区分权重、优化器、激活和通信缓冲，并按质量和吞吐验证优化。",
        "framework": "1) 用 profiler 确认峰值来自哪类内存；2) 控制序列长度、micro-batch 与数据形状；3) 用混合精度、检查点和高效 attention 降低激活；4) 用 ZeRO/FSDP、并行或卸载处理模型状态；5) 回归质量、吞吐、稳定性和通信。",
        "answer": "训练显存由权重、梯度、优化器状态、激活值、临时 workspace 和通信 buffer 共同组成。先用框架 profiler 或峰值内存快照定位，而不是遇到 OOM 就只做量化。长序列和大 micro-batch 常使激活成为主要瓶颈；缩短序列、采用长度分桶、梯度累积、activation checkpointing 和高效 attention 往往更直接。\n\n模型状态过大时可采用 bf16/混合精度、ZeRO 或 FSDP 分片、张量/流水线并行；CPU/NVMe offload 能继续降显存，但会引入传输瓶颈。量化、LoRA 等是否适用取决于训练目标和硬件支持。\n\n每次修改都要同时比较峰值显存、token/s、通信等待、数值稳定性和最终质量；能跑起来不代表训练配置有效。",
        "followup": "为什么把 global batch 拆成 micro-batch 加梯度累积，可能改变训练吞吐却不必改变有效 batch？",
    },
    "q0101": {
        "kaodian": "考察自然语言数据查询 Agent 的语义层、最小权限、查询验证、报告可追溯和人工审批。",
        "framework": "1) 认证后按租户/角色加载允许的数据语义；2) 将请求映射为受约束的查询计划；3) 校验表、列、过滤、成本和只读策略；4) 在受限连接上执行并生成带来源的报告；5) 记录审计、评测和异常兜底。",
        "answer": "自然语言报表 Agent 不应让模型直接拥有任意数据库权限。入口先认证并确定租户、角色和允许的数据域；语义层提供受控的指标、维度、表关系和业务定义，模型只生成结构化查询计划或受限 SQL，而不是猜测全库 schema。\n\n执行前做语法、表列白名单、行级权限、参数化、查询成本/时间限制和只读校验；高风险或写操作必须走独立审批。查询在最小权限账号和隔离资源上运行，结果再由模板或模型生成报告，并附上时间范围、过滤条件、数据版本和可复查的查询摘要。\n\n需要对 SQL 正确性、权限绕过、聚合口径和幻觉解释分别评测，记录审计日志，并在无法确定口径时追问或转人工。",
        "followup": "为什么“只限制模型 prompt”不能替代数据库侧的最小权限和查询校验？",
    },
    "q0062": {
        "kaodian": "考察大规模对话历史的分层存储、选择性检索、权限过滤和长会话质量验证。",
        "framework": "1) 将当前工作状态与长期历史分开；2) 把事实、偏好、事件和原文按类型存储；3) 以时间、主题、实体和 ACL 过滤后检索；4) 对热数据做缓存和索引治理；5) 用长会话回归验证召回与遗忘。",
        "answer": "历史很大时，不应把所有轮次塞回 prompt。保留当前任务所需的短窗口和结构化状态，把原文、事件、用户偏好和可复用事实持久化到适合的存储中；需要时先按租户、权限、时间、主题或实体过滤，再做文本/向量检索和重排。\n\n索引设计要考虑写入频率、删除/过期、数据分区和缓存。摘要只能作为辅助索引或工作状态，重要原文应保留可回查引用，避免摘要错误永久污染记忆。\n\n验证应覆盖跨很长时间的事实召回、已撤销偏好的删除、不同用户之间的隔离和检索噪声；只有命中率高并不代表 Agent 能在正确时机使用记忆。",
        "followup": "如何防止一个用户的长期记忆因为向量相似而被另一个用户检索到？",
    },
    "q1095": {
        "kaodian": "考察 Agent 工具的能力分类、结构化契约、最小权限和高风险操作边界。",
        "framework": "1) 按检索、计算、代码执行、业务写入和通信分类；2) 为每项能力定义名称、Schema、权限和副作用；3) 给模型最小候选工具集；4) 在运行时校验参数、配额和审批；5) 记录结果摘要与审计。",
        "answer": "Agent 常见工具包括：检索/浏览和知识库查询、计算与代码执行、文件处理、数据库/分析查询、业务 API、消息与工单、以及监控和运维接口。工具的价值不在于“越多越强”，而在于把模型无法可靠完成的外部读取、计算或受控副作用封装成可验证的接口。\n\n每个工具应声明输入/输出 Schema、权限范围、幂等性、超时、成本和是否有副作用。代码执行沙箱可以运行受限计算或验证脚本；数据库工具应默认只读、带行数/时间限制和租户过滤。它们都不能直接授予宿主或生产库的宽泛权限。\n\n运行时需要校验参数、限制工具集合和调用次数，对写操作预览并要求确认，同时记录可脱敏审计信息。",
        "followup": "为什么工具说明清楚仍不能省略服务端参数校验？",
    },
    "q1096": {
        "kaodian": "考察 Agent 工作记忆、会话/事件记忆、长期语义记忆和程序性状态的边界。",
        "framework": "1) 区分当前上下文与持久化信息；2) 说明会话事件、用户偏好/事实和工作流状态；3) 为每类定义写入条件、TTL 与权限；4) 检索时按任务和 ACL 过滤；5) 处理冲突、遗忘和可更正性。",
        "answer": "工作记忆是当前 prompt 中正在处理的目标、最近对话和工具结果，生命周期短、读取快；会话或事件记忆记录发生过什么，如一次工单处理的步骤；长期语义记忆保存经确认的用户偏好、业务事实或知识，并应带来源、时间和权限；程序性状态则保存工作流进度、待办和幂等键。\n\n不能因为内容“看起来重要”就永久写入。应定义谁能写、何时过期、如何更正/删除，以及事实冲突时的来源优先级。长期记忆检索也要先做身份和权限过滤，再按当前任务选择少量证据。\n\n是否有效要用真实多轮任务评估：该记住的能否在正确时机召回，不该记住的能否过期或被撤销，并且不泄露到其他用户。",
        "followup": "用户改变偏好后，如何避免旧记忆与新记忆同时干扰回答？",
    },
    "q1139": {
        "kaodian": "考察代码 Agent 用结构化定位与按需读取控制上下文，而不是一次性灌入整个仓库。",
        "framework": "1) 先建立仓库地图、模块边界和构建入口；2) 用符号、文本搜索和代码图定位候选；3) 分段读取并保留路径/行号证据；4) 将大输出摘要化、外置并可回读；5) 用测试和编译验证结论。",
        "answer": "代码 Agent 面对大仓库时应先缩小问题：根据任务找入口、错误信息、符号、依赖图或构建配置，再用文本搜索、LSP/AST 或代码图定位定义和调用链。只读取当前假设所需的文件片段，把路径、提交版本和行号作为可回查证据。\n\n构建日志、测试输出和大文件应分页、截断并保留外部引用；上下文里只放当前计划、关键证据和未解决问题。必要时用结构化摘要记录模块关系，而不是把整仓库摘要化后永不验证。\n\n每轮修改后运行最窄的测试、类型检查或编译，用工具结果修正下一轮检索；模型生成的“调用链”不能代替实际代码验证。",
        "followup": "为什么代码语义检索的候选结果还必须回到原文件和符号引用验证？",
    },
    "q2877": {
        "kaodian": "考察 Coding Agent 的需求确认、计划审批、最小授权执行和可验证交付闭环。",
        "framework": "1) 澄清目标、范围、验收标准和禁区；2) 调研现有代码并提出计划与风险；3) 对高影响步骤取得确认；4) 按小步修改、测试和复核执行；5) 交付 diff、验证证据和遗留风险。",
        "answer": "带规划的 Coding Agent 应先把自然语言需求收敛为可验收的问题：确认目标、非目标、接口/兼容性、数据影响和测试标准。随后读取仓库证据，给出分步计划、可能影响的文件、风险和需要确认的选择；计划不是一次性承诺，遇到新证据可以更新。\n\n执行阶段只授予当前步骤需要的文件、命令和外部权限。每个小改动后运行相应测试或静态检查，高风险操作先展示预览或等待人工批准；不要让“会先问清楚”变成无法停止的自动改动。\n\n最终交付应说明已改内容、验证结果、未覆盖场景和可回滚方式，让用户能独立审查，而不是只输出一段生成说明。",
        "followup": "哪些代码操作即使计划已批准，仍应在执行前要求一次额外确认？",
    },
    "q2100": {
        "kaodian": "考察 Agent 触发数据库删除时的最小权限、预览确认、事务/备份和审计边界。",
        "framework": "1) 默认读写分离并禁止宽泛 DELETE；2) 解析并校验目标、WHERE 条件、租户和影响行数；3) 先 dry-run/预览；4) 对可逆操作用事务或软删除并准备恢复；5) 经授权确认后执行并审计。",
        "answer": "Agent 不应拥有可以任意执行 `DELETE` 的生产权限。数据库账户和工具 Schema 要区分只读、受限写入和管理操作；删除请求必须明确表、租户、筛选条件和预计影响范围，缺少 `WHERE`、跨租户或超出阈值时应拒绝。\n\n先执行只读预览或 dry-run，展示待影响记录数和不可逆风险；能用软删除、状态迁移或可回滚事务的场景优先采用。真正提交前应由具备权限的人确认，涉及保留/合规数据还要走相应审批和备份策略。\n\n执行后记录请求人、批准、SQL/参数的安全摘要、结果和恢复线索，并对异常行数或失败告警。模型的自然语言判断不能替代数据库约束和服务端策略。",
        "followup": "为什么即使 SQL 语法正确，也要把“影响行数阈值”作为独立拦截条件？",
    },
    "q0072": {
        "kaodian": "考察 Parent-Document Retrieval 如何用小块提高召回定位、用父文档恢复生成上下文。",
        "framework": "1) 子块作为检索单元并携带父文档 ID；2) 召回后聚合或展开父段落；3) 保留标题、层级、ACL 和版本元数据；4) 控制展开长度与重复；5) 用证据召回和回答忠实度验证。",
        "answer": "Parent-Document Retrieval 通常将文档切成较小的子块用于 embedding 和召回，子块命中后再返回其所属的父段落、章节或相邻上下文给生成模型。小块减少主题混杂，有利于精确定位；父内容又避免模型只看到一句碎片而误解条件或范围。\n\n实现中要保存 child-to-parent 映射、文档版本、标题路径和权限信息。多个子块命中同一父文档时需要去重、限制展开长度，并在文档更新时同步重建映射；不能因为“父文档”就把整篇长文无节制塞入上下文。\n\n是否值得采用应比较子块 Recall@k、父证据完整性、上下文 token、延迟和最终回答的引用/忠实度，而不是默认所有 RAG 都需要两级索引。",
        "followup": "父文档过长时，如何只展开命中子块附近的可解释上下文？",
    },
    "q1530": {
        "kaodian": "考察 RAG 索引需围绕数据形态、查询、过滤、更新和权限设计，而不是只调向量库参数。",
        "framework": "1) 明确文档解析、切分和元数据；2) 选择向量、关键词或混合检索；3) 设计过滤、分区、ACL 与版本；4) 依据规模选择索引并治理增量更新；5) 用离线和线上指标验证。",
        "answer": "RAG 索引优化从数据和查询开始：解析时保留标题层级、时间、来源、语言、租户和 ACL，切分时兼顾语义完整性与检索粒度。向量索引适合语义召回，倒排/关键词索引适合精确术语、编号和过滤；很多业务需要融合检索和重排。\n\n索引结构还要支持增量写入、删除、版本切换和权限过滤。大规模数据可按租户、领域或时间分区，避免先全库检索再过滤；更新频繁时要评估嵌入重算、索引构建和一致性延迟。\n\n验证不能只看 ANN QPS，应在真实问题上比较证据 Recall@k、过滤正确性、p95 延迟、索引新鲜度、成本和最终回答忠实度。",
        "followup": "为什么把 ACL 过滤放在召回之后，可能同时带来安全和质量问题？",
    },
    "q2030": {
        "kaodian": "考察 Flat、HNSW、IVF、PQ 等索引的基本机制和无固定最优的选型原则。",
        "framework": "1) Flat 精确搜索作为质量基线；2) HNSW 用图换内存与构建成本；3) IVF 用聚类缩小候选；4) PQ/压缩降低内存并可能损失召回；5) 在真实过滤和更新负载下评测。",
        "answer": "常见向量索引包括 Flat、HNSW、IVF 和 PQ 的组合。Flat 逐向量精确比较，质量基线高但大规模延迟和成本高；HNSW 用多层近邻图加速近似搜索，通常召回好但图边占内存、构建和删除维护更重；IVF 先把向量聚类，查询只搜索部分倒排桶；PQ 用码本压缩向量以节省内存和带宽，但会引入量化误差。\n\n没有脱离数据分布的“最好”索引。选择受数据量、内存、目标 recall、过滤条件、更新/删除频率、硬件和延迟 SLO 共同影响。可以用 Flat 或高预算配置建立质量基线，再调 HNSW 的图/搜索参数或 IVF 的桶数/探测数。\n\n评测要同时记录 Recall@k、p95/p99、内存、构建时间、写入/删除成本和带过滤查询的结果。",
        "followup": "为什么只在无过滤的随机查询上调高 Recall，可能无法代表线上效果？",
    },
    "q2043": {
        "kaodian": "考察向量索引选型应从业务约束和可复现实验得出，而不是照搬项目或厂商结论。",
        "framework": "1) 明确数据规模、维度、增长和更新模式；2) 定义召回、延迟、内存和成本目标；3) 评估过滤、分区和多租户；4) 选择候选并建立 Flat/高召回基线；5) 灰度和持续回归。",
        "answer": "选择向量索引前先描述约束：向量数量和维度、是否必须常驻内存、更新/删除频率、过滤条件、多租户隔离、目标 Recall@k 和 p95 延迟。小规模或质量敏感场景可先用 Flat；内存充足且重视低延迟/高召回时评估 HNSW；规模更大或内存紧张时评估 IVF、PQ 或磁盘型方案。\n\n过滤和更新经常改变结论：先检索再过滤可能导致有效候选不足，频繁删除也会增加某些图索引维护成本。因此要用真实 query、真实 metadata 和目标硬件做基准，而不是只引用供应商宣传数值。\n\n上线时保留索引版本、嵌入模型版本和可回滚构建流程，持续观察召回、延迟、内存和索引新鲜度。",
        "followup": "向量模型升级后，为什么通常需要把索引版本与 embedding 版本一起切换？",
    },
})


# Fifth-pass follow-up: title-similarity candidates were manually checked.
# Only pairs whose teaching scope substantially overlaps are merged here.
EXTRA_MERGED_INTO.update({
    "q1555": "q1589",       # MHA limitations plus MQA/GQA/Flash Attention.
    "q1867": "q1894",       # async throw/capture is a subset of the Promise question.
    "q1875": "q3139",       # EventSource versus fetch streaming.
    "q3759": "q1069",       # AdamW versus Adam.
    "q1065": "q1492",       # DeepSpeed ZeRO stages.
    "q3216": "q1423",       # LLM architecture overview.
    "q2111": "q1394",       # General Agent safety guardrails.
    "q2586": "q2387",       # JavaScript class versus function.
})

EXTRA_MOVE_TO.update({
    "q1589": "llm-basics",
    "q1894": "frontend",
    "q3139": "frontend",
    "q3486": "rag",
})

EXTRA_TITLE_REWRITES.update({
    "q1492": "DeepSpeed ZeRO-1/2/3 分别分片什么训练状态？如何影响显存与通信？",
    "q3486": "RAG 中检索召回不准和生成回答不实，分别如何诊断与调优？",
    "q3658": "数据库索引的原理是什么？实际项目中如何设计和验证索引？",
    "q3139": "EventSource 与 fetch + ReadableStream 有什么区别？如何选型？",
})

EXTRA_FIELD_FIXES.update({
    "q0457": {
        "framework": "1) 识别大 Key 对内存、网络、持久化、复制和事件循环延迟的影响；2) 按访问模式把一个大对象拆成多个独立 key；3) Cluster 只能分散已拆分的多个 key，不能自动拆分单个大 key；4) 用迁移、渐进删除或 UNLINK 降低在线风险；5) 通过内存、延迟和复制指标验证。",
    },
    "q1492": {
        "kaodian": "考察 ZeRO 各阶段分片的训练状态、显存节省与通信代价，并区分模型状态和激活显存。",
        "framework": "1) 先拆分参数、梯度、优化器状态、激活和临时 buffer；2) ZeRO-1 分片优化器状态；3) ZeRO-2 再分片梯度；4) ZeRO-3 再分片参数并按层聚合；5) 比较显存、通信、带宽和重计算的取舍。",
    },
    "q3486": {
        "kaodian": "考察将 RAG 的检索质量问题与生成忠实性问题分开诊断、评测和治理的能力。",
        "framework": "1) 先用标注证据判断是漏召回、错召回还是生成未遵循证据；2) 检索侧检查解析、切分、查询、索引、召回和重排；3) 生成侧检查上下文、提示、引用与拒答策略；4) 分别以检索指标和忠实性指标验证；5) 用 bad case 回流持续改进。",
    },
    "q3658": {
        "kaodian": "考察 InnoDB 索引结构、查询模式驱动的索引设计，以及用执行计划和真实负载验证索引收益的能力。",
        "framework": "1) 说明聚簇索引与二级索引的基本路径；2) 根据等值、范围、排序和返回列设计联合/覆盖索引；3) 用 EXPLAIN、慢日志和实际数据分布验证；4) 识别回表、扫描行数、排序和临时表等代价；5) 平衡写入放大、存储和维护成本。",
    },
})

# Canonical merge targets also move with their source topic; keeping this
# explicit prevents a source/target pair from being split across domains.
EXTRA_MOVE_TO.update({
    "q1537": "frontend",
    "q3860": "rag",
    "q3876": "llm-basics",
})

EXTRA_TITLE_REWRITES.update({
    "q1537": "v-if 与 v-show 有什么区别？应如何按渲染与切换成本选型？",
    "q3860": "Bi-Encoder 与 Cross-Encoder 有什么区别？RAG 中如何组合？",
})

EXTRA_OVERRIDES.update({
    "q1537": {
        "kaodian": "考察 `v-if` 的条件渲染与 `v-show` 的 CSS 显隐，以及初始和频繁切换成本。",
        "framework": "1) `v-if` 控制是否创建/销毁子树；2) `v-show` 保留 DOM 并切换 display；3) 比较初始渲染、切换和状态保留；4) 考虑可访问性和动画；5) 以真实交互频率选型。",
        "answer": "`v-if` 为 false 时不会渲染对应子树（切换时创建或销毁），因此初始条件不常成立或子树昂贵时可避免无谓工作；代价是每次切换都要创建、挂载和销毁，并会重置局部状态。`v-show` 始终渲染元素，只通过 CSS `display` 控制可见性，初始开销更高但频繁显示/隐藏通常更平滑。\n\n选择还要考虑 DOM 是否应存在、表单/焦点状态、过渡动画、屏幕阅读器语义和组件生命周期。它们不是简单的性能开关，也不应和同元素上的 `v-for` 等指令混用后依赖隐式优先级。\n\n以实际条件命中率、子树成本和交互频率验证；复杂页面可拆分组件或延迟加载，而不是只在两个指令之间机械二选一。",
        "followup": "为什么频繁切换的大型表单使用 `v-if` 时，可能出现状态丢失和性能抖动？",
    },
    "q3860": {
        "kaodian": "考察 Bi-Encoder 的可预计算召回能力与 Cross-Encoder 的细粒度重排能力及两阶段组合。",
        "framework": "1) Bi-Encoder 分别编码 query 和文档；2) 向量索引快速召回；3) Cross-Encoder 联合编码 query-doc 对；4) 比较延迟、成本和精度；5) 用候选数、过滤和标注集确定组合。",
        "answer": "Bi-Encoder 分别把 query 和文档编码成向量，再用点积或余弦相似度检索。文档向量可离线建立索引，因此适合海量召回；代价是 query 与文档在编码阶段没有 token 级交互，细粒度条件、否定和数字约束可能损失。\n\nCross-Encoder 将 query 与单个候选文档联合输入模型，在编码时直接建模二者交互，通常更适合精细相关性判断；但它必须对每个候选在线前向计算，无法替代大规模首轮召回。\n\nRAG 常先用 Bi-Encoder 或混合检索召回一批候选，再用 Cross-Encoder 重排少量候选，最后展开证据给生成模型。候选数、延迟、过滤和 Recall/NDCG 应用真实数据调优。",
        "followup": "为什么 Cross-Encoder 通常放在 Top-k 重排，而不是对全库文档逐个打分？",
    },
})


# Sixth-pass metadata replacements.  They use distinct keys from the later
# fifth-pass tables, so both review passes remain independently readable.
EXTRA_OVERRIDES.update({
    "q1391": {
        "kaodian": "考察 Agent 如何把短句、歧义或缺槽位的请求安全地收敛为可执行任务。",
        "framework": "1) 判断意图、实体和约束是否足够；2) 使用会话上下文但标注不确定性；3) 低风险时给出可撤销默认，高风险时优先澄清；4) 一次只问最有信息量的问题；5) 记录澄清结果并验证最终动作。",
        "answer": "短问题并不一定需要追问；关键是判断缺失信息是否会改变结果或造成不可逆影响。先从当前会话、用户已确认的偏好和任务状态补全实体、时间、目标和约束，并把这种补全视为假设而不是事实。\n\n如果存在多个合理解释，或将触发写操作、付款、删除、对外发送等高风险动作，应明确给出少量候选或询问最关键的缺槽位。低风险的信息查询可以采用可撤销默认，并说明默认值；不要为了“显得主动”一次抛出完整表单。\n\n工程上将意图、槽位、置信度、证据来源和澄清轮次作为状态管理，设定超时或转人工机制，并用澄清后的任务成功率和误执行率评估策略。",
        "followup": "哪些操作即使模型置信度很高，也仍应要求用户显式确认？",
    },
    "q1492": {
        "kaodian": "考察 ZeRO 各阶段分片的训练状态、显存节省与通信代价，并区分模型状态和激活显存。",
        "framework": "1) 分清参数、梯度、优化器状态、激活和临时 buffer；2) ZeRO-1 只分片优化器状态；3) ZeRO-2 再分片梯度；4) ZeRO-3 再分片参数并按需聚合；5) 按网络、序列长度和吞吐实测取舍。",
        "answer": "ZeRO 的核心是消除数据并行中模型状态的重复副本。ZeRO-1 分片优化器状态；ZeRO-2 在此基础上分片梯度；ZeRO-3 再分片参数，计算某层时才在需要的 rank 间聚合该层参数。阶段越高，单卡保存的模型状态越少，但通信、预取、分片管理和实现复杂度通常越高。\n\nZeRO 主要解决参数、梯度和优化器状态的冗余，不会自动消除激活值、临时 workspace 或 KV 等其他内存。长序列或大 micro-batch 的 OOM 可能仍需通过 checkpointing、attention 优化、梯度累积或并行策略处理。\n\n选型要在具体硬件和训练配置上比较峰值显存、token/s、通信等待、收敛稳定性和故障恢复。不能把某个精度、优化器或数据并行度下的字节公式当作所有训练的通用结论。",
        "followup": "为什么 ZeRO-3 的显存更省，却可能在低带宽集群上降低吞吐？",
    },
    "q2417": {
        "kaodian": "考察 Cookie 是浏览器 HTTP 存储/自动携带机制，而 Token 是应用凭证，两者可组合使用但安全边界不同。",
        "framework": "1) 区分承载机制和凭证格式；2) 比较自动携带、作用域和跨端；3) 分析 XSS、CSRF 与令牌泄露；4) 说明会话状态、过期和撤销；5) 按客户端和威胁模型选择。",
        "answer": "Cookie 是浏览器按 Domain、Path、Secure、HttpOnly、SameSite 等规则存储并自动附带的 HTTP 机制；Token 是服务端签发的应用凭证，可能是 JWT，也可能是可在线撤销的 opaque token。Token 可以放在 Authorization 头、移动端安全存储或 Cookie 中，因此二者不是互斥概念。\n\nHttpOnly Cookie 可降低脚本直接读取凭证的风险，但浏览器自动携带也要求处理 CSRF，例如 SameSite、Origin/CSRF token 和正确的跨站策略。将 Token 放入可被脚本读取的存储会增加 XSS 泄露风险；JWT 通常是可验证而非天然加密，payload 不应放敏感信息。\n\n选择要看 Web、移动端或服务到服务场景，以及续期、撤销、设备管理和威胁模型。无论格式如何，都需要短期有效期、密钥轮换、TLS 和服务端授权校验。",
        "followup": "为什么把 JWT 放进 HttpOnly Cookie 后，仍要单独考虑 CSRF？",
    },
    "q4063": {
        "kaodian": "考察 Redis 性能来自内存、事件驱动、数据结构和命令复杂度的组合，而不是“单线程”这一句口号。",
        "framework": "1) 先看数据是否驻留内存及网络路径；2) 区分命令执行与 I/O 线程；3) 说明事件循环和非阻塞 I/O；4) 结合具体数据结构/命令复杂度；5) 用慢命令、延迟和资源指标定位瓶颈。",
        "answer": "Redis 许多常用操作快，首先因为工作集通常在内存中，避免了磁盘随机 I/O；其事件驱动、非阻塞网络 I/O 和较简单的 RESP 协议也降低了连接处理开销。核心命令执行路径长期以单线程串行化为主，这减少了共享数据结构上的锁竞争，但并不意味着所有 Redis 工作都只有一个线程：不同版本可使用 I/O 线程，持久化、删除等也可能由后台线程处理。\n\n性能还取决于命令和数据结构。小而受控的 String/Hash/Set 操作与一次遍历百万成员、超大 value、复杂 Lua 或阻塞命令的成本完全不同；持久化、复制、网络带宽、CPU、内存碎片和客户端输出缓冲也会成为瓶颈。\n\n排障应看命令延迟、slowlog、`LATENCY` 事件、CPU、网络、复制和内存指标，并按具体 workload 选择拆分、限流、批量或架构调整。",
        "followup": "为什么一个 O(N) 命令即使只执行一次，也可能影响同实例上的其他客户端？",
    },
    "q3056": {
        "kaodian": "考察 FlashAttention-2 的 IO/并行优化及接入时对硬件、dtype、掩码和数值回归的验证。",
        "framework": "1) 回顾标准 attention 的 HBM 读写瓶颈；2) 说明分块、在线 softmax 与 kernel 融合；3) 说明 FA2 的工作划分和并行优化；4) 检查模型/硬件/dtype/掩码兼容性；5) 用输出、显存和吞吐回归。",
        "answer": "FlashAttention 通过把 Q、K、V 分块放入片上存储、在线计算 softmax，避免把完整的注意力分数矩阵反复写回高带宽显存；它计算的是精确 attention，而不是用近似替换注意力。FlashAttention-2 进一步改进 GPU 工作划分和并行度，以降低非矩阵乘部分的开销。\n\n接入时先确认模型实现、GPU 架构、CUDA/内核版本、数据类型、head dimension、因果/填充掩码和变长 batch 是否受支持。某些组合会回退到普通实现，或因数值/掩码语义不同产生结果差异；不能只看配置名就假定已启用。\n\n用固定输入对比 logits/损失和 mask 行为，再在目标序列长度、batch 与硬件上测峰值显存、prefill/decoding 吞吐和 p95 延迟。速度收益取决于工作负载，不能承诺固定倍数。",
        "followup": "为什么验证 FlashAttention 时，既要对齐数值输出，也要覆盖变长和因果掩码样本？",
    },
    "q3751": {
        "kaodian": "考察单头自注意力的计算与多头通过多个子空间并行建模的差别。",
        "framework": "1) 给出单头 Q/K/V 加权聚合；2) 说明多头各自投影；3) 拼接后经输出投影；4) 区分多头不是多个输入序列；5) 比较表达、成本和 head 配置。",
        "answer": "Self-Attention 指同一序列中的位置用 Query、Key、Value 相互计算权重并聚合信息。单头注意力只在一个投影子空间内完成这种匹配；Multi-Head Attention 将表示投影到多个头，每个头独立计算 attention，再拼接并经过输出投影。\n\n多头让模型有机会在不同子空间学习不同的关系或特征，但不保证每个头都有清晰、互不重叠的“语义职责”。它增加投影、缓存和调度开销；在固定模型维度下，头数增加也会改变每个头的维度和 kernel 效率。\n\n是否需要或如何设置头数应通过质量、延迟、显存和可训练性验证，不能把注意力图可视化当作充分因果解释。",
        "followup": "为什么增加头数不等同于线性增加模型的表达能力？",
    },
    "q3877": {
        "kaodian": "考察点积与加法注意力的打分函数、计算特性和 Transformer 的工程取舍。",
        "framework": "1) 写出缩放点积和加法打分形式；2) 区分双线性与含非线性的函数族；3) 解释缩放与 softmax 数值范围；4) 说明矩阵乘并行效率；5) 不把常见选择说成普适最优。",
        "answer": "不能笼统视为等价：单层点积是双线性打分；加法注意力含非线性、可表示更一般打分函数；Transformer 主要因矩阵乘效率和扩展性选点积。缩放点积通常写作 `qk^T / sqrt(d_k)`，缩放有助于避免维度增大时分数方差过大而让 softmax 过早饱和。\n\n加法注意力常写作 `v^T tanh(W_q q + W_k k)`，会引入额外参数和逐元素非线性。它并非“必然更准”，也不能只用参数量比较；不同隐藏维度、任务和训练配置会影响结论。\n\nTransformer 使用点积的一个关键工程原因是 QK^T 和与 V 的乘法能高效映射到大规模矩阵乘和并行硬件。选型仍应对目标任务、序列长度、吞吐、内存和质量进行实测。",
        "followup": "为什么点积注意力在维度增大时通常需要除以 `sqrt(d_k)`？",
    },
    "q3879": {
        "kaodian": "考察多头是多个独立投影子空间，不把单个注意力图误读为确定的模型解释。",
        "framework": "1) 说明每头独立 Q/K/V 投影；2) 说明头的输出拼接和再投影；3) 分析冗余与分工都可能出现；4) 用消融、剪枝和任务指标验证；5) 区分相关性可视化与因果贡献。",
        "answer": "“多头”表示模型对同一输入使用多组独立的 Q/K/V 投影并行计算注意力，而不是有多个模型或多个物理输入。各头输出被拼接后再通过输出投影混合，因此一个头的模式也可能被后续层改写。\n\n训练后有些头会呈现局部、位置或特定关系模式，也可能存在冗余、近似重复或对任务贡献很小的头。仅凭一张 attention heatmap 不能证明“这个头理解了语法”或“该头不可替代”。\n\n验证某头作用应结合固定条件下的 head masking/ablation、剪枝后的质量变化、不同样本的一致性和训练种子，而不是把可视化相关性当作因果证据。",
        "followup": "为什么对单个头做消融时，还要关注其他头和后续层是否补偿了它？",
    },
    "q3791": {
        "kaodian": "考察 Transformer 的按层上下文表示与 RNN 递归状态在信息路径、并行性和长序列成本上的差异。",
        "framework": "1) 说明 RNN 逐步递推固定维度隐状态；2) 说明 Transformer 每层通过 attention 直接访问多个位置；3) 比较训练并行与生成时限制；4) 比较 O(n²) attention 和状态瓶颈；5) 结合任务和资源选型。",
        "answer": "RNN 在时间步之间递归传递一个固定维度的隐状态，后面的状态通过连续变换携带过去的信息；这形成顺序依赖，训练很难在时间维完全并行，远距离信息也需要经过很多步传播。\n\nTransformer 在每一层为各 token 维护上下文相关表示，并通过注意力让一个位置直接与多个其他位置交互。训练时同一层的多个位置可以并行计算，但标准全注意力的计算/内存会随序列长度二次增长；自回归 Transformer 在生成阶段仍需按 token 逐步解码。\n\n两者没有绝对替代关系。RNN/状态空间等递归模型在流式、长序列或资源受限场景仍可能合适；应按质量、延迟、记忆长度和硬件实测。",
        "followup": "为什么 Transformer 的训练可并行，却不能让普通自回归生成一次性产生全部 token？",
    },
    "q3848": {
        "kaodian": "考察归一化放置与位置编码是不同设计轴，以及它们对深层训练稳定性和外推的影响。",
        "framework": "1) 区分 Post-LN 与 Pre-LN 的残差位置；2) 说明深层梯度和训练稳定性取舍；3) 解释 RMSNorm 与 LayerNorm 的差别；4) 解释 RoPE 注入相对位置信息；5) 不把组合演进说成唯一因果链。",
        "answer": "Post-LN 通常在残差相加后做 LayerNorm，是原始 Transformer 的常见形式；Pre-LN 在子层输入处先归一化，再走残差路径。Pre-LN 往往让深层网络的优化更稳定，但不同初始化、学习率、残差缩放和训练目标都会影响最终质量，不能简单说某一形式永远更好。\n\nRMSNorm 主要按均方根缩放表示，不像 LayerNorm 那样显式中心化；它常用于降低部分计算并保持训练稳定性。RoPE 则是将位置信息以旋转方式注入 Q/K，使注意力分数携带相对位置关系。它是位置编码设计，而非归一化的替代物。\n\n许多 LLaMA 类实现采用 pre-norm 风格的 RMSNorm 与 RoPE，但这种组合应按模型规模、上下文长度、训练稳定性和推理质量进行消融验证。",
        "followup": "为什么讨论 RoPE 扩展长上下文时，还要分别考虑位置插值、训练分布和注意力实现？",
    },
    "q3849": {
        "kaodian": "考察 tokenizer 迁移如何处理词表行对齐、新增 token 初始化、继续训练与回归验证，避免绝对化结论。",
        "framework": "1) 比较旧新词表和特殊 token；2) 复用能按相同词串对齐的 embedding/输出行；3) 初始化新增或不匹配行；4) 继续预训练或适配以恢复分词分布；5) 用质量、安全和成本回归决定是否重训。",
        "answer": "更换 tokenizer 不能笼统视为“必须重训 embedding/输出层，否则完全乱码”。如果新旧词表中存在可按相同词串和语义对齐的 token，可以复用对应的输入 embedding 和输出层行；新增或不匹配的行需要合理初始化，并在继续预训练或适配阶段学习新的分词分布。\n\n词表变化越大、语言/代码覆盖变化越多、特殊 token 或聊天模板变化越显著，迁移风险就越高。是否需要全量重训取决于这些变化、可用数据、目标质量和架构约束，而不是一个固定规则。输出层是否与 embedding 绑定、是否有量化/分片也会影响实现。\n\n迁移后应在分词长度、生成质量、困惑度、格式遵循、安全回归和吞吐/成本上比较旧新版本，并保留能回滚的 tokenizer 与权重组合。",
        "followup": "为什么 tokenizer、模型权重和聊天模板应作为一个可回滚的版本组合发布？",
    },
    "q3799": {
        "kaodian": "考察对比学习的正负样本构造、难负例的收益与假负例风险。",
        "framework": "1) 定义希望拉近/拉远的表示关系；2) 构造可靠正例和多样负例；3) 逐步加入模型或检索挖掘的难负例；4) 控制假负例和标签泄漏；5) 用检索/分类和泛化集评估。",
        "answer": "对比学习通过让相关样本的向量更接近、无关样本更远离来学习判别性表示。随机负例往往太容易，模型很快就能区分；难负例与 query 表面相似但在关键条件、实体或语义上不相关，能迫使模型学习更细粒度的边界。\n\n难负例可来自当前模型检索结果、同主题文档、批内样本或人工构造，但必须检查假负例：真实相关文档被当作负例会把错误监督写入表示。挖掘策略也可能让模型过拟合某个检索器或数据分布。\n\n应逐步增加难度，保留随机/跨域负例，并在独立的检索、排序或下游任务上比较 Recall、NDCG、鲁棒性和偏差，而不是只看训练 loss。",
        "followup": "怎样从线上 click 或人工标注中区分“难负例”和“漏标的正例”？",
    },
    "q3923": {
        "kaodian": "考察训练研究需控制数据量、训练步数和计算预算，避免把资源差异误归因给方法。",
        "framework": "1) 明确比较对象与主要变量；2) 固定或报告数据、token、步数和 batch；3) 处理学习率与训练时长耦合；4) 使用多个种子和验证集；5) 报告成本、停止准则和局限。",
        "answer": "比较两种训练方法时，样本量和训练步数会直接影响数据覆盖、过拟合风险、优化进度和计算成本。如果方法 A 看了更多 token 或训练更久，质量差异可能来自资源而不是算法本身。\n\n研究设计应明确是固定数据、固定更新步数、固定 token 数、固定墙钟时间还是固定 FLOPs；这些约束不等价。学习率、batch、warmup 和调度通常也要随总训练长度调整，否则“控制变量”本身会制造不公平。\n\n至少报告数据版本、训练 token/steps、硬件、随机种子、早停/检查点选择和评测集，并在预算变化时观察缩放趋势。这样结论才知道适用于哪个资源区间。",
        "followup": "为什么固定训练 step 但改变 global batch，仍可能改变看到的数据量和优化行为？",
    },
    "q3926": {
        "kaodian": "考察 Pointwise、Pairwise 和 Triplet/Ranking 损失的监督信号与排序目标差异。",
        "framework": "1) Pointwise 独立预测样本分数/标签；2) Pairwise 学习正负相对顺序；3) Triplet 通过锚点、正例、负例设间隔；4) 比较样本构造和计算成本；5) 用真实排序指标选型。",
        "answer": "Pointwise 训练把每个样本独立当作分类或回归目标，例如预测点击概率或相关性分数；它实现简单、可利用绝对标签，但优化目标与列表排序不完全一致。Pairwise 训练直接约束同一 query 下正例应高于负例，强调相对顺序；Triplet 可视为以 anchor、positive、negative 构造相对距离/间隔的一类方法。\n\nPairwise/Triplet 的效果高度依赖正负样本和难例采样，候选组合数也会增加计算量；Pointwise 则容易被类分布和校准目标影响。还有 listwise 方法直接考虑整个候选列表。\n\n选择应看标注形式、线上排序目标、延迟和评测指标，如 NDCG、MRR、Recall，而不是把任一损失称为普适更高级。",
        "followup": "为什么 Pairwise 样本的构造方式会显著影响模型学到的排序边界？",
    },
    "q3853": {
        "kaodian": "考察学习率调度应从训练曲线、总 token/步数和稳定性验证得出，而不是照搬框架默认。",
        "framework": "1) 明确优化器、有效 batch 和总训练预算；2) 设置 warmup、主调度和最低学习率；3) 记录实际 LR、loss、梯度与验证指标；4) 一次只改变少量变量；5) 在目标任务和种子上回归。",
        "answer": "训练框架的 scheduler 只是执行配置，不能替你决定合适的学习率。先确定优化器、有效 batch、总训练 token/steps、参数是否冻结和目标任务，再选择线性、余弦、恒定或分段等调度策略；warmup 常用于降低训练初期不稳定，但比例没有通用固定值。\n\n训练中记录每一步实际学习率、训练/验证损失、梯度范数、溢出/跳步和任务指标。若调整总训练时长或 batch，通常需要重新检查学习率和 warmup，因为它们与优化步数耦合。\n\n比较配置时固定数据、模型和评测，避免同时改 scheduler、最大 LR、weight decay 和 batch 而无法归因。最终以目标质量、稳定性和资源成本选择，而不是以“用了某个 API”作为能力证明。",
        "followup": "为什么验证损失仍在下降时，也不能只凭这一点无限延长训练？",
    },
    "q3924": {
        "kaodian": "考察专业 Agent 需把领域任务、工具、知识、权限和评测闭环共同设计。",
        "framework": "1) 定义高价值任务和不可做边界；2) 组织受控领域知识与工具 Schema；3) 设计身份、权限、审批和兜底；4) 建立离线/线上任务评测；5) 从 bad case 迭代 Prompt、工具和流程。",
        "answer": "专业场景 Agent 的起点不是换一个更大的模型，而是明确谁在什么约束下完成什么任务，以及哪些结论必须转人工。例如医疗、金融、运维或法务场景要区分信息检索、草稿辅助、受控执行和最终决策的责任边界。\n\n领域知识需要版本、来源、权限和更新流程；工具要暴露最小必要能力并在服务端验证参数。工作流中加入高风险动作审批、引用/证据要求、失败回退和审计，而不是让模型自由生成后直接执行。\n\n评测集应覆盖真实任务、边界案例、权限拒绝、工具失败和领域专家 rubric。线上监控任务成功、人工接管、错误成本和数据泄露信号，再用已脱敏 bad case 迭代。",
        "followup": "为什么专业领域的“回答看起来专业”不能替代由专家定义的任务评测？",
    },
    "q3927": {
        "kaodian": "考察 AIOps 平台的目标、数据链路、诊断/自动化边界和人机协同。",
        "framework": "1) 接入指标、日志、trace、变更和告警；2) 统一实体、拓扑和时间关联；3) 做检测、聚类、关联与根因候选；4) 通过 runbook 和审批执行受控自动化；5) 用 MTTA/MTTR、误报和业务影响评估。",
        "answer": "AIOps 平台的目标是帮助运维从海量信号中发现异常、关联影响范围、缩短定位和恢复时间，而不是保证自动找到唯一根因。数据层接入指标、日志、trace、告警、配置/发布变更和服务拓扑，并对时间、服务、租户和版本进行统一关联。\n\n分析层可包含阈值/异常检测、告警去重聚类、依赖关联、检索和基于 runbook 的诊断建议。自动化执行应把低风险、幂等的操作封装为受控 runbook；涉及扩容、回滚、删除或流量切换时需要权限、预览和审批。\n\n平台效果要看告警有效率、MTTA/MTTR、人工接管、误报漏报和业务影响，持续用事故复盘校正数据质量和规则/模型。",
        "followup": "为什么缺少可靠服务拓扑时，告警关联和根因候选容易产生误导？",
    },
    "q3981": {
        "kaodian": "考察金标相关性标注的角色、标注准则、一致性控制和版本化评测治理。",
        "framework": "1) 明确 query、候选范围和相关性层级；2) 由熟悉业务的标注者或专家负责；3) 编写可操作 rubric 与反例；4) 双标、仲裁并量化一致性；5) 版本化保存依据、权限和更新记录。",
        "answer": "RAG 的金标不应由模型或单个开发者凭直觉决定。最合适的标注者通常是了解业务语义、文档权限和正确答案边界的领域人员；工程团队负责抽样、工具和质量控制。对于高风险领域，应由相应专家审核。\n\n先定义相关性：是“包含直接答案”“支持答案的一部分”还是“背景参考”，并明确版本、时间、语言和权限范围。每个 query 应有标注说明和反例；可采用双人标注、分歧仲裁和一致性统计，避免把模糊定义伪装成客观真值。\n\n金标、文档版本和 rubric 要版本化。文档更新、业务规则变化或线上 bad case 出现时，经过审核后增量更新评测集，而不是悄悄覆盖历史结果。",
        "followup": "为什么评测集中必须记录文档版本和权限范围，而不只保存文档 ID？",
    },
    "q3090": {
        "kaodian": "考察传统 RAG 与 Agentic RAG 的检索控制权、流程复杂度和适用边界。",
        "framework": "1) 描述传统固定检索-生成链路；2) 描述 Agent 按状态决定检索、工具和迭代；3) 比较可控性、延迟、成本和故障模式；4) 设置预算、终止和引用验证；5) 用任务分层评测决定是否引入 Agent。",
        "answer": "传统 RAG 通常是相对固定的流程：解析 query、检索/重排若干证据、把证据交给模型生成回答。它可预测、易评测，适合单跳问答或流程稳定的知识服务。\n\nAgentic RAG 把检索作为 Agent 可选择和迭代的工具：它可能先澄清问题、改写 query、多跳检索、调用数据库/浏览器、检查证据冲突，再决定回答或拒答。这样能处理开放任务，但也会增加延迟、token、循环、错误累积和权限攻击面。\n\n不应为了“智能”把所有 RAG 变成 Agent。只有固定链路难以覆盖的多步骤任务才值得增加状态机、预算、终止条件、来源验证和人机兜底，并用成功率、忠实度、成本和延迟比较收益。",
        "followup": "什么样的问答任务可先用固定 RAG，而无需加入 Agent 循环？",
    },
    "q3479": {
        "kaodian": "考察用模型维度、FFN 扩张倍数、序列长度和 GQA/MoE 等配置估算层内参数与 FLOPs。",
        "framework": "1) 明确 `d_model`、`d_ff`、层数、序列长度和头配置；2) 估算 attention 投影与 attention 矩阵计算；3) 估算普通/门控 FFN；4) 说明 GQA、MoE 和 KV cache 的变化；5) 用 profiler 校验实际 kernel 和通信成本。",
        "answer": "以标准稠密 decoder 层为例，若模型维度为 `d`，Q/K/V 和输出投影的参数量约为 `4d²`；普通两层 FFN 约为 `2d*d_ff`，门控 FFN（如 SwiGLU）约为 `3d*d_ff`。因此比例主要由 `d_ff/d` 决定，而不是一个固定的“五个结构比例”。\n\n每 token 的投影 FLOPs 也随这些矩阵大小增长；此外 attention 的 QK^T 和加权 V 项会随当前序列长度增长。GQA/MQA 会减少 K/V 投影和 KV Cache，MoE 则改变每 token 激活的 FFN 参数/计算，量化和并行还会改变实际瓶颈。\n\n估算用于建立量级直觉，真实部署仍要用模型配置、batch、prefill/decoding 阶段和 profiler 测吞吐、显存及通信。",
        "followup": "为什么长上下文 prefill 中，attention 矩阵计算的占比会高于短上下文 decoding？",
    },
    "q3788": {
        "kaodian": "考察数据分块仅在访问局部、可跳读或可并行处理时才可能降低 I/O，并识别其额外成本。",
        "framework": "1) 明确访问模式和存储介质；2) 比较整文件读取与按块定位；3) 说明块大小、对齐和索引；4) 分析小块带来的元数据、请求和放大；5) 用字节数、请求数和尾延迟验证。",
        "answer": "分块不会天然减少 I/O。它在只需读取对象的一小部分、可以按索引跳到相关块、能够流式处理或并行读取时，才可能减少传输/读取的总字节数和等待时间。例如列式文件按列块读取，或 RAG 只加载命中文档块。\n\n如果每次仍要扫完所有块，或者块太小导致大量系统调用、对象存储请求、索引查找和元数据开销，分块反而可能更慢。块太大又会把无关数据一起读入，造成读放大；压缩、缓存和底层页大小同样会影响结果。\n\n因此应基于真实查询分布选择块大小和索引，并测量读取字节、请求数、缓存命中、CPU 解压和 p95/p99，而不是把 chunking 当作普适优化。",
        "followup": "为什么对象存储上把块切得极小，常会提高而不是降低请求成本？",
    },
    "q3782": {
        "kaodian": "考察规则/模板与生成式模型在表达能力、确定性、维护成本和风险控制上的互补关系。",
        "framework": "1) 说明规则对明确、稳定约束的优势；2) 说明生成模型处理开放语言和长尾的能力；3) 比较可解释性、测试、成本与失败模式；4) 用结构化约束和校验组合；5) 按风险和变化频率分层选型。",
        "answer": "规则和模板在输入结构明确、业务逻辑稳定、结果必须可预测时更合适，例如权限校验、金额计算、固定格式渲染和合规拦截。它们可穷举测试、容易审计，但面对开放表达、长尾语义和持续变化的知识时维护成本会迅速上升。\n\n生成式模型擅长理解和生成自然语言、归纳未穷举的表达，但输出具有不确定性，可能幻觉、越权或格式错误。它不应直接替代确定性业务规则。\n\n常见做法是让模型做意图理解、摘要或候选草稿，把关键决策交给 Schema、规则引擎、检索证据和服务端校验；高风险动作再加入确认和人工审核。选择依据是错误代价、输入开放度、变化速度、延迟和可维护性。",
        "followup": "为什么“先由模型生成，再用规则校验”仍需要定义模型无法修复时的兜底路径？",
    },
    "q3789": {
        "kaodian": "考察 DeepSeek-V3/R1 报告中架构、训练系统和后训练方法的分工，以及避免把版本数据当作普适结论。",
        "framework": "1) 区分 V3 基座训练与 R1 推理后训练；2) 说明 MoE 的稀疏激活与负载均衡；3) 说明 MLA 对 KV Cache/带宽的影响；4) 说明 FP8、并行和 MTP 的训练系统作用；5) 用报告版本、评测、成本和约束做条件化结论。",
        "answer": "DeepSeek-V3 的技术报告描述了一组协同设计：MoE 用路由让每个 token 只激活部分专家，以较低的每 token 计算换取更大的总参数容量；MLA 压缩注意力的 KV 表示以降低长上下文推理的缓存和带宽压力；FP8 训练、并行/通信调度和 Multi-Token Prediction 则服务于训练效率与模型能力。这些机制各自解决不同瓶颈，不能把“MoE 参数多”或“FP8 更便宜”单独当成全部原因。\n\nDeepSeek-R1 报告讨论的是推理能力的后训练路径，包括基于可验证/规则奖励的强化学习、冷启动数据和后续训练阶段。GRPO 等方法的效果依赖任务、奖励、数据和训练实现；它不是所有应用都应照搬的通用配方。\n\n评价性能与成本时要固定报告版本、硬件、训练 token、评测集、吞吐和服务配置。论文中的训练资源或评测成绩是该报告条件下的结果，不应外推为其他模型、部署或未来版本的保证。",
        "followup": "为什么比较两个 MoE 服务的成本时，除了激活参数，还要测 KV Cache、batch、路由和硬件利用率？",
        "sources": [
            {"title": "DeepSeek-V3 Technical Report", "url": "https://arxiv.org/abs/2412.19437"},
            {"title": "DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning", "url": "https://arxiv.org/abs/2501.12948"},
        ],
    },
    "q3798": {
        "kaodian": "考察上下文相关表示如何通过条件化编码缓解一词多义，以及它与静态词向量的边界。",
        "framework": "1) 说明静态 embedding 一词一向量；2) 说明上下文模型按句子生成 token 表示；3) 用多义和长程语境举例；4) 说明 subword、位置和层选择影响；5) 用下游任务验证而非只看可视化。",
        "answer": "静态词向量为同一个词条分配固定向量，因此“苹果”在水果和公司语境中通常仍从同一初始词条表示出发。上下文相关模型会结合周围 token、位置和层级计算每次出现的表示，使相同词在不同句子中的向量可以不同，从而更容易表达多义、指代和组合语义。\n\n这不意味着模型总能正确消歧：训练数据、tokenizer、上下文长度、模型容量和任务微调都会影响结果。子词切分也使罕见词和形态变化有不同表现，不能把“一个词一个向量”的旧直觉直接套到 Transformer token 上。\n\n应通过词义消歧、检索、分类或真实下游任务评估表示质量，并检查不同语言、领域和长上下文条件下的退化。",
        "followup": "为什么同一 token 在不同 Transformer 层的表示也可能适合不同下游任务？",
    },
})

EXTRA_OVERRIDES.update({
    "q1385": {
        "kaodian": "考察 Agent 如何按任务逐步暴露工具/技能，降低上下文占用和错误调用风险。",
        "framework": "1) 将工具按领域、权限和任务阶段分组；2) 先暴露目录和简短能力摘要；3) 命中意图后再加载详细 Schema/示例；4) 在服务端再做权限和参数校验；5) 记录发现、选择和失败以优化目录。",
        "answer": "渐进式披露的目标是让模型在当前任务只看到少量相关工具，而不是把所有 Schema、示例和说明一次塞进 prompt。可以先提供工具目录、能力标签、权限和副作用摘要；模型或确定性路由选中某个领域后，再按需加载该领域的详细输入 Schema、边界和示例。\n\n分组可按业务领域、任务阶段、读写风险或租户权限进行。目录本身也要准确、可检索且受 ACL 过滤；模型选择工具只是建议，真正执行仍由服务端重新验证身份、参数、配额和审批条件。\n\n要对比全量暴露与按需加载的 token、正确选择率、漏选率、调用失败和延迟，并为找不到能力提供明确的澄清或人工兜底。",
        "followup": "为什么工具摘要中也要明确写出副作用和权限边界？",
    },
    "q1416": {
        "kaodian": "考察 Redis replication ID、offset 和 replication backlog 如何共同决定部分重同步或全量同步。",
        "framework": "1) 说明主节点复制流的 ID 和递增 offset；2) 从节点保存已处理的 ID/offset；3) 重连时通过 PSYNC 发送已知位置；4) 主节点判断 ID 与 backlog 覆盖范围；5) 解释切主后的第二 ID 和全量同步兜底。",
        "answer": "Redis 主节点为复制流维护 replication ID 和递增 offset；从节点记录自己已处理到的 replication ID/offset。连接中断后，从节点通过 PSYNC 告诉主节点自己最后看到的 ID 与 offset，主节点据此判断它是否仍能从 replication backlog 中补发缺失命令。\n\n当 ID 匹配且 offset 仍落在 backlog 可覆盖的范围内，可进行部分重同步；ID 不匹配、backlog 已覆盖不到该位置或其他条件不满足时，需要全量同步。发生故障转移时，旧主复制流与新主的历史衔接需要额外处理，Redis 会维护第二 replication ID 等信息帮助判断可延续的历史。\n\n具体诊断应查看 `INFO replication` 中的角色、ID、offset、backlog 和连接状态，并结合版本和故障转移时序；不要只比较一个 offset 数字就断定数据一定一致。",
        "followup": "为什么 backlog 太小会提高网络短暂抖动后触发全量同步的概率？",
    },
    "q1642": {
        "kaodian": "考察测试失败时区分原始返回、解析转换、断言语义和异步生命周期的证据链。",
        "framework": "1) 最小化复现并固定输入/环境；2) 同时打印原始值、类型和解析后值；3) 核对断言匹配器、期望值和序列化规则；4) 检查 fixture、mock、异步等待与清理；5) 增加覆盖该边界的回归测试。",
        "answer": "“返回值看起来正确”只说明其中一个观察点正确。先把测试缩成最小复现，分别记录被测函数的原始返回、经过 wrapper/serializer 后的值、实际类型、异常和断言看到的值。常见问题是字符串与对象、`None` 与缺失字段、浮点比较、日期时区或 matcher 语义不同。\n\n再检查 Harness 的生命周期：fixture 是否重置、mock 是否泄漏、异步任务是否真的 await、资源是否在断言前关闭或被重用。不要通过放宽断言来“修复”未知差异；应先明确产品契约。\n\n定位后在最靠近解析/断言边界处修复，并保留一个能同时验证值和类型、覆盖异步完成时机的回归用例。",
        "followup": "为什么在异步测试中，加入任意固定 sleep 往往会掩盖而不是解决生命周期问题？",
    },
    "q1670": {
        "kaodian": "考察会话凭证迁移的双读单写、短期兼容、撤销与安全回退，而不是无条件延长旧令牌。",
        "framework": "1) 盘点旧新凭证格式、签名、Cookie 作用域和用户覆盖；2) 先让服务端同时验证受限的旧/新版本；3) 成功使用旧凭证时签发新凭证；4) 设置迁移窗口、撤销和密钥轮换；5) 监控失败、异常复用和回滚。",
        "answer": "不中断登录的常见思路是“短期双读、逐步单写”：服务端在明确的迁移窗口内同时验证旧 JWT/会话凭证和新格式；用户持旧凭证成功访问后，按原有认证状态签发新的短期凭证，客户端随后只继续使用新格式。\n\n迁移前要核对签名算法和密钥、issuer/audience、过期时间、Cookie 的 Domain/Path/SameSite/Secure、跨站流程和设备类型。旧凭证不能因此无限延期；应设定截止时间、撤销/黑名单策略、密钥轮换和异常设备检测。对于已失效、疑似泄露或权限变化的会话，仍应要求重新认证。\n\n分阶段发布并监控验证失败、刷新失败、登录循环和异常 token 复用，保留可快速回滚的验证逻辑。JWT 只是凭证格式，不能替代会话撤销和服务端授权检查。",
        "followup": "为什么 Cookie 属性迁移可能让一部分用户“看似已登录但请求未带凭证”？",
    },
    "q1728": {
        "kaodian": "考察 DST 如何维护意图、槽位、上下文和不确定性，并按场景选择规则、模型或混合方案。",
        "framework": "1) 定义领域、意图、槽位和状态转移；2) 比较规则/表单、分类序列标注、LLM 和混合方案；3) 表达缺失、冲突和置信度；4) 用澄清问题补全关键槽位；5) 评估槽位准确、任务成功和跨轮一致性。",
        "answer": "对话状态跟踪（DST）把多轮对话中的当前目标、已知槽位、约束和未决问题维护为显式状态，例如订酒店时的城市、日期、预算和房型。传统领域较窄、流程固定时可用规则或表单状态机；覆盖面更广时可用意图分类、序列标注、检索或 LLM 抽取；生产中常将确定性规则、结构化 Schema 和模型理解组合。\n\n状态不应只保存一个猜测值，还要保存来源、置信度、更新时间和是否得到用户确认。冲突信息、否定、改口和多意图需要明确策略；高风险或关键槽位缺失时应问最小的澄清问题。\n\n评估既看 intent/slot F1，也看跨轮状态一致性、澄清轮数、误执行和最终任务成功率。",
        "followup": "用户把入住日期从“下周”改为具体日期时，状态系统应如何保留和覆盖信息？",
    },
    "q1754": {
        "kaodian": "考察固定输出格式需要模型引导、受约束生成、服务端解析和语义校验共同保证。",
        "framework": "1) 定义 JSON Schema/字段约束和错误处理；2) 使用 provider 的 structured output 或工具调用能力；3) 给出少量正反示例；4) 服务端严格解析、类型/范围/权限校验；5) 对失败进行受限重试或转人工。",
        "answer": "让 LLM 稳定输出固定格式，先把格式变成机器可执行的契约，例如 JSON Schema、枚举、必填字段、长度和数值范围。若模型接口支持 structured output、JSON mode 或 tool/function calling，应优先使用；prompt 中还应说明字段含义、空值策略和禁止输出的内容。\n\n模型输出仍是外部输入。服务端要做 JSON 解析、Schema 校验、业务语义校验和权限校验，不能因为文本看起来像 JSON 就直接执行。解析失败可将具体错误反馈给模型进行有限次数修复，超过上限则返回明确失败或转人工。\n\n用真实边界输入、长上下文、注入文本和多语言样本回归格式通过率与业务正确率；正则截取大段自由文本通常不是可靠的结构化协议。",
        "followup": "为什么 Schema 校验通过后，还需要验证日期、金额或资源 ID 是否符合业务权限？",
    },
    "q1760": {
        "kaodian": "考察查询改写在保留用户意图与约束的前提下补全检索表达，而不是编造事实。",
        "framework": "1) 识别口语、省略、同义和缺失实体；2) 结合已确认上下文补全可证实的信息；3) 歧义或高风险时先澄清；4) 生成一个或多个可追踪查询并保留原 query；5) 用检索指标和错误样本评估。",
        "answer": "查询改写把用户的口语化、简称或不完整表达转换成更适合检索的 query，例如补出已确认的产品名、时间范围、同义词或业务术语。它应保留原 query 和证据来源，避免把模型猜测的实体、政策或数字当成用户事实。\n\n可采用规则/词典、会话状态、检索反馈和 LLM 生成的组合。若缺失的信息会让检索空间完全不同，或涉及高风险决策，应先澄清而不是强行扩写；也可以生成多个受控候选后分别检索和重排。\n\n评估应比较改写前后的证据 Recall、NDCG、零结果率、错误扩展率和最终回答忠实度，并按领域维护词典和失败案例。",
        "followup": "为什么 query rewrite 后仍应让用户原始表达参与检索或审计？",
    },
    "q1790": {
        "kaodian": "考察意图归一化的 taxonomy、训练样本、阈值/澄清和版本治理。",
        "framework": "1) 定义互斥或可组合的业务意图与边界；2) 收集同义表达和反例；3) 用规则、分类器、向量或 LLM 路由；4) 对低置信/多意图进行澄清；5) 按线上漂移与误路由持续更新。",
        "answer": "意图归一化是把“报销流程是什么”“费用审批怎么操作”等不同说法映射到稳定的业务意图和槽位。第一步是建立可操作的 taxonomy：每个意图写清定义、正例、反例、所需槽位和与相邻意图的边界；分类不清时再换模型只会放大混乱。\n\n实现可用关键词/规则处理高精度模式，用分类器、向量检索或 LLM 覆盖开放表达，并让确定性业务规则做最后路由。低置信、多意图、超出 taxonomy 或会触发高风险动作的请求应澄清或转人工，而不是硬塞进最相近类别。\n\n上线后记录混淆矩阵、零匹配、澄清率和下游任务成功率，版本化 taxonomy 与样本，防止业务变化导致静默误路由。",
        "followup": "为什么只用向量相似度把 query 匹配到历史话术，容易把相邻意图混在一起？",
    },
    "q1859": {
        "kaodian": "考察 RAG 与微调分别改变推理时证据和模型行为，以及两者组合的条件。",
        "framework": "1) RAG 用外部、可更新证据补充上下文；2) 微调改变模型参数/行为；3) 比较知识时效、可引用性、成本和隐私；4) 说明可组合但各自有失败模式；5) 用任务评测决定。",
        "answer": "RAG 在推理时检索外部资料并把证据放入上下文，适合频繁更新、私有或需要引用来源的知识；它不改变基座参数，效果受解析、检索、重排和模型是否遵循证据共同影响。微调通过更新参数或适配器改变模型的行为、风格、格式遵循或特定任务能力，更适合稳定、可规模化的模式。\n\n微调不是可靠的实时知识库，RAG 也不能替代模型对任务格式、工具调用或领域语言的学习。两者可以组合：先微调改善行为和领域表达，再用 RAG 提供当前可追溯事实；也可能只需其中一种或原生 prompt/规则。\n\n选择基于知识更新频率、数据许可、引用要求、延迟/成本、可评测样本和错误代价，分别评估检索质量、行为质量和端到端任务成功。",
        "followup": "什么时候给模型接入一份经常变化的政策文档，比微调更容易审计和回滚？",
    },
    "q1937": {
        "kaodian": "考察从文档解析、切分、混合召回、重排到证据展开的完整定位链路。",
        "framework": "1) 清洗文档并保留结构、版本和元数据；2) 按语义/结构切分并建立父子关系；3) 用关键词和向量召回候选；4) 用重排和过滤确定段落；5) 展示来源并用金标评估。",
        "answer": "要定位相关段落，先让文档成为可检索的证据：解析标题、段落、表格和来源路径，按结构或语义切分，并保存父章节、版本、时间、语言和权限等元数据。查询侧可同时使用关键词/倒排和向量召回，精确术语、编号和自然语言语义各有优势。\n\n从候选中用交叉编码器或其他重排器判断 query 与段落的细粒度相关性，必要时展开命中段落的父级或相邻上下文，避免只给模型一句断章取义的文本。过滤和 ACL 应在正确的位置生效。\n\n用金标问题分别评估证据 Recall@k、重排质量、引用正确性和最终回答忠实度；不能只看模型最终答对了几次。",
        "followup": "为什么段落召回准确但父级上下文缺失，仍可能导致回答错误？",
    },
    "q1941": {
        "kaodian": "考察错误码注册表、实时证据、权限脱敏和受控下一步建议如何组成可靠的故障解释。",
        "framework": "1) 建立错误码的权威定义、版本和责任人；2) 用 trace/log/配置关联当前上下文；3) 区分已知模式和未知异常；4) 生成可验证、最小权限的建议；5) 对高风险动作加确认和审计。",
        "answer": "可靠的错误解释应先查权威错误码注册表，而不是让模型凭文字猜含义。注册表应提供码值、用户可见说明、技术原因、责任服务、严重级别、版本和推荐 runbook；实时 trace、日志和配置只补充当前请求的时间、依赖和影响范围。\n\nAgent 应区分“注册表已定义且证据匹配”“已定义但证据冲突”和“未知码/异常模式”。对未知情况明确不确定性，提出安全的收集信息步骤，而不是编造根因。输出时对 token、用户数据和内部细节做权限过滤和脱敏。\n\n下一步动作应是可审计、可回退且最小权限的，例如查看状态或重试；重启、切流、删除等操作需要预览、审批和人工确认。",
        "followup": "为什么错误码的文档版本必须与当前服务版本可关联？",
    },
    "q1962": {
        "kaodian": "考察关系图、表格和文本的数据结构差异，以及从强基线到专用模型的选型。",
        "framework": "1) 识别实体、边、时间和节点特征；2) 图任务可评估图算法/GNN；3) 表格任务先建立树模型/线性模型基线；4) 处理缺失、泄漏、类别和时间切分；5) 按部署约束与业务指标比较。",
        "answer": "关系网络的数据核心是实体及其边，例如社交关系、交易网络、依赖图或知识图谱；任务可能是节点分类、链路预测、社区发现或路径分析。图算法和图神经网络可以利用连接结构，但对采样、时序泄漏、冷启动和部署复杂度敏感。\n\n表格数据以行/列特征为主，常见任务是分类、回归、排序或异常检测。线性模型和树模型（如梯度提升树）往往是很强的起点；特征工程、缺失值、类别编码、时间切分和数据泄漏通常比“换深度模型”更决定效果。\n\n混合场景可把图特征聚合回表格，或使用图/表格模型组合。最终以真实业务验证、可解释性、延迟和维护成本选择。",
        "followup": "为什么交易风控数据按随机方式切训练/测试集，可能产生严重的时间泄漏？",
    },
    "q2250": {
        "kaodian": "考察权重衰减、学习率和调度如何与优化器、训练预算、参数组和验证指标协同。",
        "framework": "1) 明确优化器、数据规模、有效 batch 和总 token；2) 区分 L2 正则与 AdamW 的解耦权重衰减；3) 配置 warmup 和主调度；4) 对 norm/bias 等参数组审慎设置；5) 用学习曲线和任务指标验证。",
        "answer": "学习率决定每次更新的步幅，训练调度决定它随步骤如何变化；权重衰减用于约束参数规模，但在自适应优化器中应区分传统 L2 正则与 AdamW 的解耦 weight decay。它们都不是脱离模型、batch 和总训练预算的固定数字。\n\n实践中先固定数据、有效 batch、优化器和总 token/steps，再选择 warmup 加线性/余弦等调度作为起点。不同参数组（如 bias、归一化参数、预训练层或新加头）是否使用相同 weight decay 和学习率，需要基于模型和实验决定。\n\n记录实际学习率、训练/验证曲线、梯度稳定性和下游质量；一次只改变少量超参，并在相同预算和多个种子上比较，避免从单条 loss 曲线得出过强结论。",
        "followup": "为什么训练步数改变后，原来的 warmup 步数和最低学习率往往需要重新检查？",
    },
    "q2251": {
        "kaodian": "考察把模型文本转为受约束结构化实例时的 Schema、解析、语义校验和失败恢复。",
        "framework": "1) 定义机器可执行 Schema 与版本；2) 使用 structured output/tool calling 或受控生成；3) 解析后做类型、范围、关联和权限校验；4) 将具体错误用于有限重试；5) 安全地拒绝或转人工。",
        "answer": "把 LLM 输出用于程序逻辑时，应先定义明确的 Schema：字段、类型、枚举、必填项、嵌套关系和版本。若接口支持 JSON Schema、structured output 或工具调用，优先让模型按该契约输出；这能减少格式错误，但不能证明内容正确。\n\n服务端仍要解析并验证实例：类型和范围、引用 ID 是否存在、日期/金额是否合法、字段之间是否一致，以及调用者是否有权限。解析或业务校验失败时，把简洁、无敏感信息的错误反馈给模型进行有限次数修复；超过预算应返回失败或转人工。\n\n不要把自由文本经脆弱正则提取后直接执行。对于写操作，还应在结构化校验后增加预览、幂等键和确认机制。",
        "followup": "为什么“合法 JSON”不等于“可安全执行的业务请求”？",
    },
    "q2252": {
        "kaodian": "考察全量微调、参数高效微调、量化适配和后训练目标的选择边界。",
        "framework": "1) 明确要改善知识、行为、格式还是推理；2) 比较全量微调与 LoRA/Adapter 等 PEFT；3) 说明 QLoRA 的资源取舍；4) 区分 SFT、偏好优化和继续预训练；5) 用目标与通用能力回归选型。",
        "answer": "常见适配方式包括全量微调、参数高效微调（LoRA、Adapter、Prefix/Prompt Tuning 等）以及在低比特冻结基座上训练适配器的 QLoRA。全量微调可调整的自由度最大，但显存、存储、发布和灾难性遗忘风险也更高；PEFT 更省资源、便于多任务切换，但容量和部署方式需要验证。\n\n从训练目标看，监督微调（SFT）学习指令、格式或任务映射；偏好优化/强化学习用于相对偏好或可验证奖励；继续预训练更适合大量领域语料的分布适配。它们可组合，但不应把“微调”当成更新实时事实的唯一方法。\n\n选择依据是数据质量/规模、目标能力、硬件、延迟、合规和回归结果。需同时评估目标任务、通用能力、安全和成本，并保留数据与权重版本。",
        "followup": "为什么领域文档频繁更新时，RAG 往往仍比反复微调更容易追溯？",
    },
    "q2265": {
        "kaodian": "考察在记不清精确指标时，能否诚实说明证据、估算方法、边界和验证计划。",
        "framework": "1) 明确区分已确认数据与记忆/估算；2) 说明指标口径、时间范围和基线；3) 给出可复查的数据源或验证方法；4) 只陈述本人负责的部分；5) 不以虚构数字填补空白。",
        "answer": "记不清精确数字时，最好的做法不是猜一个“看起来合理”的百分比。可以先说明自己记得的事实边界，例如指标类型、比较方向、观察窗口和参与的环节；然后坦诚精确数值需要回查仪表盘、实验报告、PR 或复盘记录。\n\n如果面试需要估算，应说明估算公式、输入假设和可能误差，而不是把估算包装成线上结论。例如可以说“按请求量和单次时延估算量级，具体以当时的监控口径为准”。\n\n真正有说服力的是讲清指标如何定义、基线是什么、自己如何验证和根据结果做决策。诚实的边界比不可核验的漂亮数字更经得起追问。",
        "followup": "如何把“性能提升”拆成可复查的延迟、吞吐、错误率和成本指标？",
    },
    "q2595": {
        "kaodian": "考察 Vue 生命周期中响应式状态可用与真实 DOM 已挂载是不同阶段。",
        "framework": "1) 区分 Vue 2/3 API 和生命周期；2) 在 created/setup 后访问响应式状态；3) 说明异步回调触发时机不保证 DOM；4) 需要 DOM 时使用 mounted/onMounted 与 nextTick；5) 处理组件卸载和请求取消。",
        "answer": "在 Vue 的 `created`（Vue 2）或 setup 逻辑中，组件的响应式状态已经可以读写，因此异步请求回调通常可以更新 data/ref/computed 依赖。但 `created` 并不保证组件 DOM 已挂载；请求何时返回也不构成 DOM 已存在的保证。\n\n需要读取或操作真实 DOM 时，应在 `mounted`/`onMounted` 之后进行；状态更新导致的 DOM 刷新还需要等待 `nextTick`。如果请求在组件卸载后返回，应取消请求或忽略过期结果，避免更新无效组件或覆盖更晚的响应。\n\n具体行为也受 Vue 版本、SSR 和组件缓存影响，测试应覆盖快返回、慢返回、卸载和重复请求。",
        "followup": "为什么在更新响应式状态后立刻读取元素尺寸，常常需要等待 `nextTick`？",
    },
    "q2665": {
        "kaodian": "考察未知异步内容高度下的空间预留、稳定布局、渐进渲染与 CLS 度量。",
        "framework": "1) 优先从图片/媒体元数据预留 aspect-ratio；2) 对文本/卡片使用骨架、min-height 或 contain-intrinsic-size；3) 避免在顶部插入未预留内容；4) 在必要时使用虚拟列表/测量缓存；5) 用真实设备的 CLS 和交互体验验证。",
        "answer": "异步内容高度未知时，目标不是保证页面永不变化，而是避免内容加载后把用户正在阅读或点击的区域突然推开。图片、视频和广告位应尽早提供宽高或 `aspect-ratio`；卡片/文本可使用与真实内容接近的 skeleton、`min-height` 或 `contain-intrinsic-size` 预留空间。\n\n对于瀑布流或长列表，可在离屏时测量、缓存已知高度，或用虚拟列表减少同时布局的节点。新内容尽量追加在稳定区域，避免在视口顶部无预留插入；字体加载、图片解码和错误状态也应纳入设计。\n\n最后用真实网络、设备和内容长度监测 CLS、滚动跳动和交互中断。过度固定高度会产生空白或裁剪，需要在稳定性与信息密度间取舍。",
        "followup": "为什么仅在开发环境用固定短文案测试，容易漏掉生产中的 CLS 问题？",
    },
    "q2670": {
        "kaodian": "考察 React Hook state setter 如何调度更新、触发 render/commit，以及闭包和批处理边界。",
        "framework": "1) 调用 setter 将更新入队而非同步改变量；2) React 计算下一次 render；3) 状态/props 无变化时可能跳过子树工作；4) commit 后 effect 运行；5) 使用函数式更新和依赖声明避免陈旧闭包。",
        "answer": "`useState` 返回的 setter 会把状态更新请求交给 React 调度，而不是立即修改当前 render 中的变量。React 之后以新的 state/props 重新执行组件函数，比较并提交需要的 DOM 变化；在同一事件中的多次更新通常会被批处理。\n\n当前回调捕获的是创建它那次 render 的状态快照，因此连续更新依赖旧值时应使用函数式形式，如 `setCount(c => c + 1)`。DOM 已提交后的副作用放在 `useEffect` 或 `useLayoutEffect`，不要在 render 中做副作用。\n\n是否重渲染/跳过还受 state identity、memo、父组件和并发调度影响。理解时应区分“组件函数重新执行”“DOM 实际变更”和“effect 执行”三个阶段。",
        "followup": "为什么在一次点击回调中连续调用两次 `setCount(count + 1)` 可能只加一？",
    },
    "q2673": {
        "kaodian": "考察 HTTP/2 用二进制帧和多 stream 在一条 TCP 连接上复用请求，以及传输层队头阻塞边界。",
        "framework": "1) 说明连接、stream 与 frame 的层级；2) 多 stream 的帧可交错发送；3) 说明流级别的独立性和流控；4) 区分 HTTP/1.1 队头阻塞与 TCP 丢包影响；5) 说明 HTTP/3 的不同传输层。",
        "answer": "HTTP/2 在一条 TCP 连接上建立多个逻辑 stream，每个请求/响应的数据被切成带 stream ID 的二进制 frame。不同 stream 的 frame 可以交错发送，因此一个慢响应不必像 HTTP/1.1 单连接队列那样阻塞后续所有请求的应用层发送。\n\nHTTP/2 仍运行在同一条 TCP 字节流上：如果底层某个 TCP 包丢失，后续字节需要等待重传，其他 stream 也可能受传输层队头阻塞影响。流量控制、优先级和服务器/浏览器实现还会影响实际并发与公平性。\n\nHTTP/3 以 QUIC 为传输层，试图减少跨 stream 的传输层队头阻塞，但也引入不同的连接、迁移和部署考虑。不要把“HTTP/2 多路复用”理解成无限并发或必然更快。",
        "followup": "为什么大量大响应同时复用一条 HTTP/2 连接，仍可能影响小请求的尾延迟？",
    },
    "q2689": {
        "kaodian": "考察 Promise 的状态、then 链返回规则、thenable 吸收与异常传播。",
        "framework": "1) 说明 pending 到 fulfilled/rejected 的一次性转移；2) `then` 总返回新 Promise；3) 返回值、Promise/thenable 和 throw 的不同结果；4) 用 `catch` 处理前链异常；5) 处理未捕获 rejection 和并发组合。",
        "answer": "Promise 初始为 pending，之后只能一次性变为 fulfilled 或 rejected，状态不会再改变。`then` 不会修改原 Promise，而是返回一个新的 Promise：回调返回普通值时新 Promise fulfilled；返回另一个 Promise/thenable 时会等待其结果；回调抛出异常时新 Promise rejected。\n\n`catch(fn)` 可理解为 `then(undefined, fn)`，能够处理其前面链路中传播来的 rejection；处理函数若返回正常值，后续链可以恢复为 fulfilled。异步回调中的异常若没有接入 Promise 链，仍可能不会被同一个 catch 捕获。\n\n使用 `Promise.all`、`allSettled`、`race` 等组合时要明确失败语义、取消/超时策略和未处理 rejection 监控。",
        "followup": "为什么在 `then` 回调里忘记 `return` 一个异步操作，可能让后续链过早继续？",
    },
    "q2771": {
        "kaodian": "考察常见 HTTP 请求头按路由、内容协商、认证、缓存、来源和条件请求分组理解。",
        "framework": "1) 说明头字段由协议版本和应用决定；2) 路由/内容类如 Host、Content-Type、Accept；3) 认证/会话类如 Authorization、Cookie；4) 缓存和条件类如 Cache-Control、If-*；5) 来源和安全类如 Origin、Referer，避免把客户端头当可信身份。",
        "answer": "常见请求头可按用途理解：`Host`（在 HTTP/1.1 中用于虚拟主机路由）、`Content-Type`/`Content-Length`/`Content-Encoding` 描述请求体、`Accept`/`Accept-Language` 表示可接受的响应表示、`Authorization` 和 `Cookie` 承载认证信息、`Cache-Control` 与 `If-None-Match`/`If-Modified-Since` 支持缓存和条件请求。\n\n`User-Agent`、`Origin`、`Referer` 等可帮助兼容性、跨站策略或诊断，但客户端可伪造，不能作为唯一身份或权限依据。浏览器还会根据请求模式添加一些安全相关头，服务端应按 CORS、CSRF 和内容安全要求处理。\n\n不要机械背完整列表；调试时结合具体协议版本、浏览器/客户端、反向代理和接口契约，检查哪些头必须、哪些会被中间层改写或剥离。",
        "followup": "为什么服务端不应只依据 `Referer` 或 `User-Agent` 判断请求是否可信？",
    },
    "q2865": {
        "kaodian": "考察 LLM 可观测平台提供运行诊断，但业务质量仍需由端到端目标和真实结果验证。",
        "framework": "1) 列出平台可见的 trace、token、延迟、prompt 和工具事件；2) 定义业务成功、错误成本和人工接管；3) 构建离线金标与线上实验；4) 将 trace 与业务结果关联；5) 以 bad case 闭环改进。",
        "answer": "LLM 可观测平台能帮助看到一次请求使用了什么模型、prompt、检索片段、工具调用、token、延迟和异常，因此非常适合定位链路问题、成本异常和回归差异。但它无法自动知道回答是否真的解决了用户问题、执行是否合规，或业务结果是否正确。\n\n业务端需要定义自己的成功标准，例如工单一次解决率、报表口径正确率、人工复核通过率、投诉率或实际转化，并通过标注集、回放、A/B 实验和抽检验证。trace 应与这些结果关联，才能发现“链路看起来健康但任务失败”的模式。\n\n平台的内置评估、LLM-as-judge 或自动评分可以辅助筛查，却不应取代有版本、可审计的业务评测和高风险人工复核。",
        "followup": "为什么 token 降低和 p95 变好，仍可能伴随端到端任务成功率下降？",
    },
    "q3114": {
        "kaodian": "考察参数化知识、上下文证据和外部系统知识的更新、可追溯和可靠性边界。",
        "framework": "1) 参数化知识来自训练并随权重固化；2) 上下文知识是当前请求临时提供的证据；3) 外部知识来自检索、数据库或工具；4) 比较更新成本、时效、引用和权限；5) 用来源和验证约束回答。",
        "answer": "参数化知识是模型训练后编码在权重中的统计模式和事实关联，调用时无需外部检索但可能过时、难以精确删除或引用。上下文知识是 system/user prompt、工具结果或检索片段在当前请求中临时提供的信息，易更新且可附来源，但受窗口、检索和模型遵循能力限制。\n\n外部知识位于数据库、文档库、搜索、业务 API 等系统中，通常更适合最新、私有、可权限控制或需要精确计算的事实；它需要查询、可用性和访问控制设计。三者不是完全隔离：模型会解释上下文和工具结果，外部系统也可能被预先训练语料影响。\n\n对于高风险或时效事实，应优先访问权威外部来源、标注证据和时间，必要时拒答或转人工，而不是依赖模型记忆。",
        "followup": "为什么更新一份政策文档后，RAG 通常比重新训练模型更快获得可追溯的变化？",
    },
    "q3149": {
        "kaodian": "考察 AI 产品收入和利润同时受价值、定价、采用率、推理成本、获客和运营约束影响。",
        "framework": "1) 定义目标客户和可量化价值；2) 说明订阅、按量、席位或交易等收入模型；3) 分解推理/数据/人工/云资源等变动成本；4) 加入获客、支持、研发和合规成本；5) 以留存、毛利和单位经济模型验证。",
        "answer": "AI 产品收入首先取决于用户是否愿意为可验证的价值付费，例如节省的人力、提高的转化、降低的风险或新的内容/服务能力。定价可按席位、订阅、用量、结果或交易抽成设计，实际收入还受获客、激活、留存、扩张和合同条款影响。\n\n利润不等于收入减去一个模型 API 单价。变动成本可能包括推理 token、GPU/云资源、检索和存储、人工审核、第三方数据/工具；固定和半固定成本还包括研发、支持、销售、合规和安全。模型路由、缓存、限额和产品流程会同时影响成本与体验。\n\n应按客户/场景建立单位经济模型，观察毛利、留存、投诉/人工介入和规模下的边际成本，并用实验验证产品价值，而不是假设“AI 热度”自动转化为利润。",
        "followup": "为什么降低每次推理成本时，还要同时观察留存和人工复核成本？",
    },
    "q3161": {
        "kaodian": "考察能否用真实工程证据说明 AI 编程的使用边界、验证流程和个人责任。",
        "framework": "1) 说明 AI 用于哪些具体环节；2) 交代人负责的设计、审查和决策；3) 展示测试、静态检查、review 和发布证据；4) 说明安全、版权和敏感数据边界；5) 如实报告收益与失败案例。",
        "answer": "证明在生产工程中使用 AI 编程，不是说“让模型写了很多代码”，而是能讲清它在需求理解、代码定位、样板生成、测试、文档或排障中具体做了什么，以及哪些设计和最终决策仍由人负责。\n\n更可信的证据包括可审查的 diff、测试/编译/静态检查结果、代码评审记录、灰度与监控、缺陷复盘和可量化的开发周期变化。AI 输出必须经过与人工代码相同的安全、依赖、许可证、隐私和兼容性检查，不能因来源是模型而降低标准。\n\n回答时说明一个成功案例和一个被拒绝/修正的案例，标明指标口径和个人贡献。没有线上数据时如实说明原型或内部工具验证，不虚构生产规模。",
        "followup": "为什么 AI 生成代码通过单元测试后，仍可能需要安全、集成和负载验证？",
    },
})

EXTRA_OVERRIDES.update({
    "q0457": {
        "answer": "Redis 大 Key 是指单个 key 对应的数据量或元素数过大，例如数 MB 的 String、含大量成员的 Hash、Set 或 ZSet。它会放大内存占用、网络传输、持久化和复制开销；同步删除或过期还可能拉长事件循环的响应时间。\n\n根本治理是按业务访问模式拆分：把一个大集合或大 Hash 分桶为多个独立 key，分页或按需读取，避免把本应查询的数据整体塞进一个 value。Redis Cluster 可以把这些拆分后的多个 key 分布到不同槽位和节点，但不能自动把“一个大 key”拆到多台机器上。压缩 value 只能在 CPU、延迟和可查询性可接受时使用。\n\n处理既有大 Key 时，先通过采样、`MEMORY USAGE`、`--bigkeys` 或业务指标确认影响，再进行双写/迁移和逐步切流。删除大型复合结构可分批删除字段，或在合适场景使用 `UNLINK` 将释放工作交给异步 lazy-free；仍要观察内存、延迟与复制压力。",
        "followup": "为什么把一个大 Hash 拆成多个 key 后，才可能通过 Redis Cluster 分散单节点压力？",
    },
    "q3658": {
        "answer": "索引是用额外存储和写入维护成本换取更少的数据页访问。以 InnoDB 为例，聚簇索引的叶子节点保存整行数据；二级索引的叶子节点保存索引列和主键，因此通过二级索引取未覆盖的列时通常还需按主键回表。B+ 树适合磁盘页组织和范围扫描，但索引不是越多越好。\n\n设计先从真实查询模式出发：把稳定的等值过滤列放在联合索引前面，再考虑范围、排序和连接条件；如果能把查询所需返回列包含在索引中，可减少回表。最左前缀不是机械规则，范围条件、选择性、排序方向、数据分布和写入成本都要一起判断。避免在索引列上做不必要的函数或隐式转换，也不要为了消除所有 filesort 盲目增加宽索引。\n\n验证要看真实参数和数据量：使用 `EXPLAIN`/`EXPLAIN ANALYZE`、慢查询日志和压测观察扫描行数、实际耗时、回表、临时表和排序代价；上线后还要观察写入放大、磁盘和缓存命中率。一个具体业务表（例如 K 线或订单表）的字段和分区设计应由它自己的查询、保留和唯一性约束单独讨论。",
        "followup": "联合索引 `(a, b, c)` 在 `a = ? AND b > ? ORDER BY c` 的查询中，哪些部分通常能有效利用索引，哪些要结合执行计划确认？",
    },
})


# Final priority overlay for the seventh pass.  A few earlier review passes
# predate these canonical destinations, so resolve every merge chain here.
EXTRA_MERGED_INTO.update({
    "q0046": "q0274", "q1834": "q1929", "q2496": "q0324",
    "q3372": "q0088", "q2781": "q4081",
})

EXTRA_OVERRIDES.update({
    "q0615": {
        "kaodian": "考察 Linux 启动链路中固件、引导加载器、内核、initramfs 与用户空间服务管理的职责边界。",
        "framework": "1) 固件完成硬件初始化并选择启动介质；2) 引导加载器加载内核与可选 initramfs；3) 内核初始化驱动、内存和根文件系统；4) init/systemd 启动用户空间服务；5) 结合发行版和 UEFI/BIOS 差异说明。",
        "answer": "典型 Linux 启动从 BIOS 或 UEFI 的硬件初始化和启动项选择开始，随后由引导加载器（如 GRUB）加载内核镜像、内核参数以及可选的 initramfs。内核解压后初始化 CPU、内存管理、中断、驱动和早期文件系统；initramfs 可在真正的根文件系统可用前加载存储、加密或网络相关驱动并完成挂载准备。\n\n根文件系统切换后，内核启动 PID 1。现代发行版通常由 systemd 按依赖关系启动挂载、网络、日志和业务服务；较旧系统可能使用 SysV init。排障时可按阶段查看 UEFI/GRUB 配置、kernel command line、`dmesg`、initramfs、systemd unit 和服务日志，而不是把所有发行版说成完全相同的固定流程。",
        "followup": "为什么根文件系统位于加密盘或网络盘时，initramfs 往往不可省略？",
    },
    "q0647": {
        "answer": "虚拟内存让每个进程看到独立、连续的虚拟地址空间。CPU 的 MMU 通过页表把虚拟页映射到物理页框或文件页；未映射或权限不符时触发异常，由操作系统按需分配、加载或拒绝访问。它同时提供进程隔离、页级读写执行权限、共享库/共享内存、内存映射文件和按需分页等能力。\n\n交换空间只是内存压力下把不活跃匿名页暂时换出的可选后备机制，不等同于虚拟内存本身。虚拟地址空间很大也不表示物理内存无限；过度换页会造成严重抖动。设计和排障要分别观察地址空间、RSS、页缓存、缺页率、OOM 和 swap，而不要把“有虚拟内存”简化为“磁盘扩展内存”。",
        "followup": "为什么一个进程的虚拟地址很大，但它的实际 RSS 可能很小？",
    },
    "q4073": {
        "answer": "分页把虚拟地址空间切成固定大小的页，并通过页表映射到固定大小的物理页框；优点是分配和保护粒度统一、外部碎片小，代价是页表和页内碎片。现代通用系统通常以分页为主，并按需映射、换页和做权限控制。\n\n分段按逻辑区域（代码、数据、栈等）的基址和长度进行地址转换，段大小可变，能表达逻辑边界但容易产生外部碎片。x86-64 的长模式下普通地址转换主要依赖分页，传统分段大多不参与通用地址隔离，只有如 FS/GS 等用途仍有特殊意义。两者可在体系结构概念上组合，但不能把现代系统简单描述成“先完整分段、再完整分页”。",
        "followup": "页表的多级结构如何在大地址空间下减少常驻内存开销？",
    },
    "q3376": {
        "answer": "HTTP/1.0 以短连接为常见模式；HTTP/1.1 引入默认持久连接、Host、分块传输、缓存和更明确的语义，但单条连接上的请求仍容易受顺序和队头影响。HTTP/2 将报文拆成二进制帧，在一条 TCP 连接上复用多个 stream，并引入头部压缩和流控；底层 TCP 丢包仍可能影响同连接的其他 stream。\n\nHTTP/3 采用 QUIC（通常基于 UDP）承载 HTTP 语义，使不同 stream 的传输层丢包恢复更独立，并改进连接迁移和握手。版本不是绝对快慢排序：代理、TLS、网络丢包、连接数量、服务端实现和工作负载都会影响结果，应以浏览器网络面板和端到端指标验证。",
        "followup": "为什么 HTTP/2 已支持多路复用，HTTP/3 仍有减少队头阻塞的价值？",
    },
    "q0720": {
        "answer": "DNS 是应用层名称解析协议。客户端通常先查询本地缓存或 stub resolver；若没有命中，递归解析器代表客户端依次向根、顶级域和权威 DNS 服务器获取委派和最终记录，再按 TTL 缓存结果。权威服务器负责某个 zone 的真实记录，递归解析器负责替用户完成这条链路。\n\n实际解析还可能涉及 hosts 文件、企业 DNS、CNAME 链、负缓存、DNSSEC 和 CDN 的地理/EDNS 客户端子网策略。回答“属于哪一层”时应说明 DNS 在应用层，底层可使用 UDP、TCP 或加密的传输封装。",
        "followup": "为什么 TTL 过短会增加权威服务器压力，而过长又会延缓变更生效？",
    },
    "q0721": {
        "answer": "传统 DNS 查询和小型响应通常使用 UDP 53 端口，以降低连接建立开销；响应过大或被截断（TC 位）时，客户端可改用 TCP。区域传送通常使用 TCP，具体实现也会受 DNSSEC、EDNS 和服务器策略影响。\n\nDNS over TLS（DoT）和 DNS over HTTPS（DoH）分别把 DNS 放进 TLS/TCP 或 HTTPS 通道，主要改变客户端到解析器这一段的保密性和可观察性，不会让整个解析链天然私密。不要把“DNS 一定 UDP”或“一定 TCP”当作绝对结论。",
        "followup": "为什么 DNS 响应截断后通常需要 TCP 回退？",
    },
    "q0723": {
        "answer": "内核会根据协议和 socket 绑定信息把到达的数据交给正确的 socket。对 TCP 连接，通常由协议、本地地址和端口、远端地址和端口组成的四元组区分连接；多个客户端可以连接同一个服务端监听端口而不会混淆。UDP 的分发规则也会考虑本地绑定、连接状态、地址/端口复用及操作系统实现。\n\n应用进程并不是按“IP 地址”单独接收数据：监听 socket 先接受新连接，已建立连接对应独立的内核 socket/队列。排障可用 `ss`、`lsof`、抓包和服务端连接指标确认端口绑定、四元组、NAT 与负载均衡是否改变了路径。",
        "followup": "为什么同一台服务端能让大量 TCP 客户端同时使用同一个 443 端口？",
    },
    "q0730": {
        "answer": "可以。ping 主要使用 ICMP Echo，而 HTTP 是应用层协议，通常运行在 TCP 之上；防火墙、安全组、路由器或主机策略可以单独丢弃 ICMP，却允许 TCP 80/443 的连接。因此 ping 失败只能说明该 ICMP 探测失败，不能直接推出 Web 服务不可达。\n\n反过来，ICMP 正常也不能证明 HTTP 服务健康。排障应分别检查 DNS、路由、端口连通、TLS 握手、HTTP 状态、代理和应用日志，并使用与实际业务相同的协议做健康检查。",
        "followup": "为什么生产健康检查通常不应只依赖 ping？",
    },
    "q0767": {
        "answer": "TLS 中的随机值、密钥交换材料和最终会话密钥承担不同职责。在 TLS 1.2 的常见握手里，client_random、server_random 与预主密钥共同参与密钥派生；随机值可帮助避免密钥材料重复并绑定握手，但“有三个随机数所以更随机”不是严谨解释。\n\nTLS 1.3 通常使用临时 Diffie-Hellman 共享秘密，再通过 HKDF 派生握手和应用流量密钥；随机数、证书签名和 transcript 共同参与认证和绑定。前向保密来自临时密钥交换，而不是单靠随机字段数量。",
        "followup": "为什么泄露长期证书私钥不必然解密过去使用 ECDHE 的会话？",
    },
    "q0769": {
        "answer": "TLS 1.3 将许多握手消息合并，使客户端在第一个飞行包中就发送 key share，服务端响应后双方即可派生应用数据密钥，因此完整握手通常是 1-RTT。恢复会话时，客户端可在 0-RTT 中携带 early data 以减少等待，但服务器必须把它视为可能被重放的数据。\n\n0-RTT 不能用于非幂等写操作、付款或不可逆动作，服务端还要处理票据、过期、反重放和区域一致性。HTTP/3 使用 QUIC/TLS 也不意味着每次请求都一定 0-RTT；实际效果取决于是否有可用会话状态与网络路径。",
        "followup": "为什么 0-RTT 适合幂等读取，却不适合下单接口？",
    },
    "q0770": {
        "answer": "HTTPS 并不是按固定次数做“几次非对称、几次对称加密”。握手阶段使用证书签名验证服务器身份，并通过（通常是临时）密钥交换协商共享秘密；随后双方从该秘密派生对称流量密钥，用 AEAD 等机制保护 HTTP 记录的机密性和完整性。\n\n证书私钥主要用于签名/身份认证，应用数据通常不会用它逐条加密。不同 TLS 版本、密码套件、是否双向认证和会话恢复都会改变具体报文，理解时应区分认证、密钥交换、密钥派生和记录保护。",
        "followup": "为什么应用数据阶段通常使用对称加密，而不是持续使用证书公私钥加密？",
    },
    "q0773": {
        "answer": "HTTPS 在 TLS 建立后会保护 HTTP 请求路径、查询参数、请求头和正文，因此网络旁路者通常不能直接看到完整 URL 中的 path/query。不过连接仍会暴露一些元数据：目标 IP、端口、流量大小/时序，以及传统 TLS 中常见的 SNI；DNS 查询也可能暴露域名。ECH、DoH/DoT 等机制可以减少部分暴露，但不是所有部署都会使用。\n\n浏览器历史、服务端日志、代理、Referer 和页面脚本仍可能接触 URL，因此敏感凭证不应放在 URL 查询参数中。不能因为 HTTPS 存在就把“URL 一定完全不可见”当作安全边界。",
        "followup": "为什么把访问令牌放进 URL 查询参数，即使使用 HTTPS 也常被认为不安全？",
    },
    "q0775": {
        "answer": "浏览器的安全锁/证书状态通常表示当前连接的证书链能被受信任根验证、证书在有效期内、主机名匹配，并且 TLS 协商没有发现明显证书错误。它不等于网站业务可信、页面没有钓鱼内容、账户不会被盗，也不证明服务端没有漏洞。\n\n遇到证书问题应检查域名、SAN、链、时间、反向代理和证书轮换；用户教育上应避免把“绿色/安全”描述成对整个网站的背书。",
        "followup": "为什么合法证书的网站仍可能承载钓鱼页面？",
    },
    "q0776": {
        "answer": "自签名证书可以使用，但浏览器默认不信任其签发者，因此面向公网用户会显示警告。企业内网、开发测试或设备管理场景可建立私有 CA，把内部根证书安全分发到受管客户端，再由该 CA 签发服务证书；也可以在受控环境中显式信任一个自签名证书。\n\n面向公有互联网的服务通常应使用公共受信任 CA 签发的证书。无论哪种方式，都需要妥善保护私钥、校验主机名、设置有效期与轮换，并避免通过“忽略证书警告”绕过认证。",
        "followup": "私有 CA 与每台服务各自使用自签名证书相比，管理上有什么优势？",
    },
    "q0777": {
        "answer": "RPC 让程序以定义好的接口和消息格式调用远端服务，常见实现会处理序列化、服务发现、负载均衡、超时、重试、认证和观测。它能改善调用契约与开发体验，但不会把网络调用变成本地函数调用：远端可能超时、部分成功、重复执行、版本不兼容或被限流。\n\n设计 RPC 时要明确 deadline、取消、幂等键、重试预算、错误码、版本兼容和可观测 trace。对于跨服务写操作，重试和 exactly-once 语义必须由业务协议、去重或事务/补偿机制保证，而不是由 RPC 框架名称保证。",
        "followup": "为什么 RPC 客户端超时后，服务端操作仍可能已经成功？",
    },
    "q0800": {
        "answer": "TIME_WAIT 由主动关闭连接的一方进入，用于保证最后 ACK 的可靠传递并让旧报文在网络中自然失效。遇到数量多时，先确认谁主动关闭、是否存在短连接、请求是否经反向代理、端口范围是否紧张，以及是否真的影响文件描述符、端口或内存，而不是直接修改内核参数。\n\n治理通常优先复用连接（HTTP keep-alive、连接池）、让协议关闭方向符合设计、减少不必要的短连接和扩大资源容量。`tcp_tw_reuse` 等内核选项具有版本和网络拓扑边界，不能被当作普适的“清理 TIME_WAIT”开关；修改前需以目标内核文档和压测验证。",
        "followup": "为什么连接池往往比调低 TIME_WAIT 相关参数更可控？",
    },
    "q0801": {
        "answer": "服务端出现大量 TIME_WAIT，常见原因是它在大量连接中扮演主动关闭方，例如响应后主动断开、代理到上游使用短连接、健康检查频繁建立连接，或某些协议要求服务端先关闭。客户端也可能造成 TIME_WAIT，关键不是“服务端/客户端”的名称，而是谁发送了第一个 FIN。\n\n先用连接状态、抓包、代理日志和请求分布确认关闭方向与连接生命周期，再决定是否启用 keep-alive、连接池、HTTP/2/3、上游复用或调整负载均衡策略。不要把某个 Web 服务器的默认 keepalive 请求数当成跨版本、跨部署的固定解释。",
        "followup": "如何从抓包或连接状态判断哪一端主动关闭了 TCP 连接？",
    },
    "q0807": {
        "answer": "实时音视频通常偏向 UDP，因为等待丢失包重传可能比丢掉一个过期音视频帧更损害体验；WebRTC 等协议会在 UDP 之上实现拥塞控制、NACK、FEC、抖动缓冲、带宽估计和媒体编解码层的错误恢复。丢包可能表现为卡顿、马赛克、音频断续或码率下降，具体取决于丢包位置和恢复策略。\n\n这不是“视频一定 UDP”：网络、企业防火墙和回退策略可能使用 TCP/TLS/TURN。选型应以互动性、容错、网络可达性和端到端质量指标决定，而不是只按媒体类型下结论。",
        "followup": "为什么视频会议里过晚到达的完整帧也可能被直接丢弃？",
    },
    "q0817": {
        "answer": "MTU 是链路层一次可承载的最大 IP 包大小；MSS 是 TCP 在建立连接时协商的单个 TCP 段载荷上限，通常由路径 MTU 减去 IP 和 TCP 头部推导。应用写入很大的字节流时，TCP 会按 MSS 分段发送，这与 IP 层把一个已形成的大 IP 包再分片不同。\n\n路径 MTU 变化或封装开销会使实际可用 MSS 变小。应尽量通过 PMTUD、MSS clamping 和合理封装避免 IP 分片，因为任一分片丢失都会影响整包重组；不能说“超过 MSS 时 TCP 会做 IP 分片”。",
        "followup": "为什么 VPN 或隧道环境中常需要重新检查 MSS？",
    },
    "q0830": {
        "answer": "NAT 是地址转换机制，不是独立的应用协议。网关可把私网地址映射为公网地址；常见 NAPT/PAT 还会同时转换端口，使多台内部主机共享一个公网地址。设备维护映射状态，以便把返回流量转回对应的内部地址和端口。\n\nNAT 影响入站连接、P2P 打洞、日志追踪和协议中携带地址的场景，因此可能需要端口映射、STUN/TURN、ALG 或应用层设计配合。它不替代防火墙、身份认证或端到端加密。",
        "followup": "为什么 NAT 会使未建立映射的公网入站连接变得困难？",
    },
})


# Final fragment sweep after the generated corpus was rebuilt.  These entries
# had valid answers but copied transitional prose as their titles; restoring a
# direct question is preferable to silently retaining context-dependent text.
EXTRA_DROP_IDS.update({"q2848", "q3080"})
EXTRA_MERGED_INTO.update({"q3104": "q3212"})
EXTRA_MOVE_TO.update({
    "q1398": "agent", "q1637": "agent", "q1936": "rag", "q2002": "rag",
    "q2088": "behavioral", "q2452": "frontend", "q2662": "frontend",
    "q2702": "frontend", "q2765": "frontend", "q2792": "behavioral",
    "q3102": "behavioral", "q1633": "engineering",
})
EXTRA_TITLE_REWRITES.update({
    "q1398": "Agent 发生错误时，如何判断失败类型并向用户提供可操作的反馈？",
    "q1633": "如何建立日志、指标和链路追踪，主动发现数据库或服务请求异常？",
    "q1637": "Agent 如何对错误进行分类，并选择重试、降级、追问或失败返回？",
    "q1936": "企业知识库问答为何需要先检索相关片段，再交给模型生成？",
    "q2002": "长文档为何常需切块？切块、检索与长上下文如何取舍？",
    "q2088": "如何为目标岗位建立可复用的面试准备计划与项目叙事？",
    "q2249": "增加模型深度、宽度或结构复杂度如何影响容量、数据需求与部署成本？",
    "q2452": "前端框架如何实现数据与视图的双向绑定？",
    "q2662": "可视化平台如何通过中间表示和适配层与不同渲染引擎通信？",
    "q2702": "如何从边界、构建、测试和版本治理设计一套前端组件库？",
    "q2708": "可配置平台如何让用户在项目初始化时安全地选择模型、知识库、工具等资源？",
    "q2765": "SameSite=Strict、Lax、None 分别在什么跨站请求场景下携带 Cookie？",
    "q2792": "面试中如何清晰说明自己在多人项目中的职责边界与个人贡献？",
    "q3102": "如何从原理、边界、权衡与验证四个层次提升技术理解深度？",
})


# Factual hardening for the remaining high-frequency infrastructure and JVM
# questions.  These replace version-specific folklore with durable boundaries
# and direct the reader to inspect the configured implementation.
EXTRA_TITLE_REWRITES.update({"q0880": "三个人和三只鬼如何安全过河？请给出可验证的最少往返步骤。"})
EXTRA_OVERRIDES.update({
    "q0380": {
        "answer": "Redis String 的实际内存占用取决于 Redis 版本、对象编码、64/32 位构建、jemalloc 等分配器、键名长度和过期元数据。网上常见的“44 字节”只是在特定旧版本、64 位和特定分配器下的示例，不能当作所有实例的固定结论。\n\n容量规划应在目标版本和真实 key/value 分布上测量，例如采样使用 `MEMORY USAGE key`、`MEMORY STATS`、RDB/AOF 大小和业务指标；同时考虑小对象分配粒度、哈希表负载、复制缓冲和碎片率。",
        "followup": "为什么仅按 value 的字节长度估算 Redis 内存，往往会低估实际占用？",
    },
    "q0378": {
        "answer": "Redis 的 String 保存的是二进制安全字节序列；当内容可解析为整数时，内部可能使用整数编码，其他数值通常仍以字符串表示。`INCRBYFLOAT` 由 Redis 按其数值语义解析和格式化，客户端不应把它等同于某一种固定的 IEEE 754 内存布局。\n\n涉及金额、精确计数或跨系统对账时，应明确小数精度和舍入规则，常见做法是使用最小货币单位的整数或固定精度 decimal 方案，而不是依赖浮点字符串的显示结果。",
        "followup": "为什么金额累计通常更适合以分为单位的整数保存？",
    },
    "q0393": {
        "answer": "Redis Hash 会根据元素数量、字段和值的大小选择紧凑编码或普通哈希表。较新的 Redis 使用 listpack 作为紧凑表示，并由 `hash-max-listpack-*` 等配置控制阈值；旧版本可能使用 ziplist，因此不能把 ziplist 名称或阈值当作当前通用事实。\n\n紧凑编码节省小对象内存，但在元素变大或数量增多后会转换为更适合查找和更新的哈希表。排障和容量设计应查看目标 Redis 版本、配置与 `OBJECT ENCODING` 的实际结果。",
        "followup": "为什么紧凑编码的 Hash 在字段数变大后可能自动转换？",
    },
    "q0405": {
        "answer": "Redis ZSet 需要同时支持按 member 查 score 和按 score 范围有序遍历。跳表和各种平衡树都能提供近似的对数复杂度；Redis 选择跳表主要是实现简洁、范围遍历直接，并能与字典索引组合，不是因为跳表在所有 CPU 或缓存场景下天然更快。\n\n因此讨论应落在接口、内存、更新模式和版本实现上，而不是把某一种数据结构说成普适最优。实际大集合还要关注成员长度、更新频率、网络输出和命令时间复杂度。",
        "followup": "为什么 ZSet 既需要按 member 定位，也需要按 score 做范围查询？",
    },
    "q0417": {
        "answer": "RDB 是某一时刻数据集的快照，常由 `SAVE`、`BGSAVE`、`save` 配置触发的自动快照，或复制全量同步等特定流程产生。优雅关闭、`FLUSHALL`、从节点升主并不必然在所有版本和配置下创建 RDB；AOF 刷盘与重写又是另一条持久化路径。\n\n应结合当前 Redis 版本、`save`、AOF、复制拓扑和运维命令确认恢复点与数据丢失窗口。生产环境还应定期验证备份可恢复性，而不是只确认文件存在。",
        "followup": "RDB 与 AOF 同时启用时，恢复时应重点检查哪些时间点与文件完整性问题？",
    },
    "q0535": {
        "answer": "Redis 的 `MULTI`/`EXEC` 会先把命令入队，再在执行阶段连续串行执行，执行期间不会被其他客户端命令穿插。因此它提供了命令序列的隔离执行，但并不等于关系数据库的完整事务。\n\n它没有自动回滚：入队阶段的语法/命令错误会导致 EXEC 失败；执行阶段某条命令的运行时错误会单独返回错误，已经成功的命令不会撤销。需要乐观并发控制时可配合 `WATCH`，需要复杂原子逻辑时可用 Lua/Functions，并仍要设计幂等和错误处理。",
        "followup": "为什么 Redis 事务中一条运行时命令失败后，前面成功命令不会自动回滚？",
    },
    "q4062": {
        "answer": "Redis 过期键清理通常结合惰性删除和后台主动过期：访问键时检查 TTL，后台也会在时间预算内持续检查过期键。具体抽样、频率和自适应行为随版本与配置变化，不应背诵固定“每秒几次”的数字。\n\n内存淘汰只在设置 `maxmemory` 且达到上限时生效。标准策略包括 `noeviction`、`allkeys-lru`、`volatile-lru`、`allkeys-lfu`、`volatile-lfu`、`allkeys-random`、`volatile-random`、`volatile-ttl`；`volatile-*` 只考虑带 TTL 的键。选择应根据可重建性和命中价值，并监控淘汰、命中率、延迟与内存。",
        "followup": "为什么过期清理与 maxmemory 淘汰必须作为两套机制分别分析？",
    },
    "q4066": {
        "answer": "普通编码下，Redis ZSet 通常用字典建立 `member -> score` 的快速定位，同时用按 score 排序的跳表支持范围遍历；它们服务于不同访问路径，不能简单说“完全只存一份数据”。成员字符串可被共享引用，但索引节点、分值和元数据仍有额外成本。\n\n小 ZSet 可使用更紧凑的编码，阈值和单向转换细节受 Redis 版本和配置影响。设计时应通过目标版本的 `OBJECT ENCODING`、内存采样和命令延迟评估，而不是依赖固定的 128/64 一类常数。",
        "followup": "为什么按分数范围查询不能只依赖 member 到 score 的字典？",
    },
    "q0530": {
        "answer": "InnoDB 自增值的分配受 `innodb_autoinc_lock_mode`、语句类型和并发模式影响。不同模式会在连续性、并发度与基于语句复制的可预测性之间取舍；配置默认值也应以正在运行的 MySQL 版本和实例参数为准，不能把某个版本的默认值写成永久事实。\n\n即使单调递增，也不保证无间隙：事务回滚、失败插入、批量插入、并发预分配和重启等都可能留下空洞。业务主键若要求全局顺序、不可猜测或跨库唯一，应单独设计 ID 方案。",
        "followup": "为什么自增 ID 的间隙通常不应被业务解释为数据丢失？",
    },
    "q0536": {
        "answer": "四种 ANSI 隔离级别从弱到强通常讨论脏读、不可重复读和幻读：READ UNCOMMITTED 可读未提交数据；READ COMMITTED 每次普通读看到当时已提交版本；REPEATABLE READ 让同一事务中的一致性读复用快照；SERIALIZABLE 通过更强的锁定/串行化语义降低并发。实际行为还取决于数据库实现。\n\nInnoDB 默认常为 REPEATABLE READ，并通过 MVCC 与锁定读机制处理不同读路径。所谓“RR 完全杜绝幻读”必须说明是快照读还是当前读、是否有范围锁和索引条件；应结合 SQL、索引、事务边界与 `EXPLAIN`/锁等待观察，而非只背定义。",
        "followup": "为什么同一隔离级别下，快照读和 `SELECT ... FOR UPDATE` 可能看到不同结果？",
    },
    "q0537": {
        "answer": "在 InnoDB 中，SERIALIZABLE 会让普通 `SELECT` 倾向于采用锁定读语义，从而限制其他事务对相关记录或范围的并发修改；它并不等于“没有 MVCC”，而是通过更强约束提高可串行化程度。\n\n代价是锁等待、死锁和吞吐下降，尤其在热点或范围查询多的业务中更明显。选择前应先确认真正需要的异常模型，再用更细粒度的条件、索引、事务设计或显式锁解决，而不是把最高隔离级别当默认方案。",
        "followup": "为什么 SERIALIZABLE 在高并发范围查询下更容易造成锁等待？",
    },
    "q0543": {
        "answer": "READ COMMITTED 适合希望每条语句读取较新的已提交数据、并减少某些范围锁冲突的场景，例如大量短事务或与其他系统的读写协作；REPEATABLE READ 适合一个事务内需要稳定快照的场景。两者都需要根据业务不变量、SQL 模式和索引验证。\n\n不能把 RC 说成“只有记录锁”或“所有互联网公司都用”。外键、唯一约束、当前读和具体执行计划仍可能产生不同锁行为；切换隔离级别前要测试死锁率、重复读语义、复制/审计要求和业务补偿逻辑。",
        "followup": "为什么把隔离级别从 RR 改为 RC 前需要回归测试事务内多次读取的业务逻辑？",
    },
    "q0470": {
        "answer": "`IN` 与 `EXISTS` 的优先选择不应依赖“大表小表”的口诀。它们在许多简单查询中可被优化器改写为半连接或等价计划；实际性能受索引、选择性、相关子查询、返回列、统计信息和版本影响。\n\n先保证语义正确，尤其注意 `NOT IN` 遇到 NULL 的三值逻辑，再用真实参数执行 `EXPLAIN`/`EXPLAIN ANALYZE` 观察扫描行数和访问路径。若计划不理想，应先补齐索引、更新统计信息或改写查询，再谈语法形式。",
        "followup": "为什么 `NOT IN` 的子查询结果包含 NULL 时，常与直觉不符？",
    },
    "q0463": {
        "answer": "在 InnoDB 中，`COUNT(*)`、`COUNT(1)` 在没有 WHERE 时通常都需要扫描某个合适的索引，不能简单断言其中一种恒定更快。优化器会根据统计信息、覆盖索引和代价选择访问路径；带条件时更应关注谓词和索引。\n\n要计数的业务应通过真实数据量和执行计划验证。若需要频繁精确全表总数，单独维护汇总/计数策略可能比每次在线全量扫描更合适；近似统计又是另一种产品取舍。",
        "followup": "为什么 InnoDB 不像某些存储引擎那样总能 O(1) 返回精确行数？",
    },
    "q0464": {
        "answer": "`COUNT(primary_key)` 会忽略主键为 NULL 的行；若主键是 NOT NULL，它与 `COUNT(*)` 的结果相同。InnoDB 可能选择最窄且可覆盖的可用索引来扫描，但这取决于查询条件、统计信息和版本，不能把“总选 key_len 最小的索引”当规则。\n\n有多个二级索引时，应查看 `EXPLAIN` 的实际 key、rows 和 Extra；不要为了影响 COUNT 盲目新增索引，因为额外索引也会增加写放大和存储成本。",
        "followup": "为什么 `COUNT(nullable_column)` 的结果可能小于 `COUNT(*)`？",
    },
    "q0590": {
        "answer": "MySQL 异步复制中，主库提交不等待副本确认，因此延迟或故障时可能丢失尚未传到副本的事务。半同步复制会在满足配置的至少一个副本确认收到相关日志后再让主库提交返回，但它不自动等同于所有副本已执行，也不消除所有故障窗口。\n\n组复制/基于共识的方案有自己的成员、冲突检测和一致性语义，不能简单称为“第三种全同步模式”。选型要明确 RPO/RTO、读路由、故障切换、跨地域延迟和业务是否允许读旧数据。",
        "followup": "为什么半同步确认收到日志仍不等于从库已经执行完事务？",
    },
    "q0594": {
        "answer": "没有“到五百万或千万行就必须分表”的通用阈值。是否拆分取决于实际数据/索引容量、热点、p95 延迟、写入与归档速度、连接/IO、备份恢复窗口、租户隔离和运维复杂度。很多大表可先通过索引、分区、冷热归档、读写分离和查询治理解决。\n\n当单库/单表已无法满足明确 SLO，且分片键、跨分片查询、全局 ID、迁移与故障恢复都有可行设计时，再采用分库分表。必须先压测与制定扩容、再平衡和回滚流程。",
        "followup": "为什么分片键一旦选错，会让后续扩容和跨分片查询都变得困难？",
    },
    "q0596": {
        "answer": "把用户 ID 等编码进路由位可以让请求快速定位分片，但它会把节点数、哈希/取模规则、容量预留和扩容路径写进数据分布。所谓只能使用 2/4/8 个节点或绝不能平滑扩容，取决于具体编码和路由实现，不是该方法的普适定律。\n\n设计时应明确逻辑分片与物理节点映射、虚拟槽/一致性哈希、历史数据迁移、双写校验和回滚。若路由规则无法演进，短期省下的查询成本会转化为长期迁移风险。",
        "followup": "为什么逻辑分片数与物理数据库节点数分离，通常更利于扩容？",
    },
})

EXTRA_OVERRIDES.update({
    "q4020": {
        "answer": "Java 的强引用会阻止对象被回收；软引用通常在内存紧张时才会被清理；弱引用在下一次 GC 后即可失效；虚引用不能通过引用取得对象，常配合 `ReferenceQueue` 跟踪回收并协调堆外资源。选择时要考虑缓存命中、可预测性和资源释放，不能把软/弱引用当通用缓存框架。\n\n`ThreadLocalMap` 中弱引用的是 `ThreadLocal` key，value 仍被线程持有的 map 强引用。在线程池中，key 被回收后若不调用 `remove()`，value 可能存活到后续 map 清理或线程结束，因此使用完成应显式 `remove()`，尤其是大对象或敏感上下文。",
        "followup": "为什么在线程池任务中仅依赖 ThreadLocal key 被 GC 不足以防止 value 泄漏？",
    },
    "q4021": {
        "answer": "常见 `OutOfMemoryError` 包括 Java heap space（堆对象过多或泄漏）、Metaspace（类加载/动态代理过多）、Direct buffer memory（堆外缓冲）、unable to create native thread（线程/系统资源不足）和 GC overhead limit exceeded。`StackOverflowError` 通常来自深递归或栈空间耗尽，是不同于 OOM 的错误类型。\n\n排障先保存证据：启用 heap dump、记录 GC 日志和容器/OS 内存限制；再用 MAT 等工具看 dominator tree、结合线程栈、类加载与直接内存指标定位增长源。修复应回到对象生命周期、缓存上限、并发度和部署内存预算，而不是只增大堆。",
        "followup": "为什么容器内存限制可能导致 JVM 尚未达到 Xmx 就被系统杀死？",
    },
    "q4022": {
        "answer": "`synchronized` 在字节码层对应 `monitorenter`/`monitorexit`，实例锁依赖对象关联的 monitor，JVM 会根据竞争情况采用不同的轻量或重量级实现。JIT 还可能进行锁消除、锁粗化等优化。\n\n不要把“无锁→偏向→轻量→重量”的固定升级链当作所有 JDK 的长期事实：偏向锁已在较新的 JDK 中被移除，具体对象头和优化策略随版本、VM 和竞争模式变化。工程上应先保证临界区正确、避免长时间持锁，再用 JFR/线程栈/压测定位实际竞争。",
        "followup": "为什么讨论 synchronized 时应同时说明 JDK 版本和竞争工作负载？",
    },
    "q4029": {
        "answer": "Full GC 或退化回收的触发条件与收集器密切相关：老年代/元空间压力、显式 `System.gc()`、晋升失败、分配失败等都可能参与；CMS 的 concurrent mode failure、G1 的 evacuation failure 或其他退化路径也有各自条件。不能把某个收集器的术语套到所有 JVM。\n\n排查应先确认 JDK、GC 算法、堆/元空间参数和 GC 日志，再查看触发原因、停顿、晋升、存活对象和分配速率。治理可能是修复泄漏、降低对象分配、调整堆/region/并发参数或换收集器，必须基于实际日志验证。",
        "followup": "为什么看到一次 Full GC 后，第一步应先确认具体收集器和 GC 日志原因？",
    },
    "q1059": {
        "answer": "估算模型显存时至少要区分权重、量化元数据、KV cache、激活/临时 workspace、运行时碎片和并发请求。70B 参数模型即使按 4-bit 原始权重粗算也约为 35GB，实际部署还需要额外空间，因此不能泛称“4-bit 就能单卡跑 70B”。\n\nKV cache 随层数、隐藏维度、上下文长度和并发数增长，常在长上下文服务中成为主要瓶颈。应在目标引擎、上下文、batch 和硬件下实测峰值显存、首 token 和解码吞吐，再选择量化、并行、上下文上限和并发控制。",
        "followup": "为什么增加并发或上下文长度时，KV cache 往往比权重更快成为显存瓶颈？",
    },
    "q1212": {
        "answer": "不忠实回答或幻觉可能来自多处：训练知识过时、检索漏召回/错召回、上下文冲突或噪声、提示约束不足、工具结果错误、模型推理/解码不稳定，以及评测集与线上分布不一致。上下文冲突只是常见原因之一，不能预设为唯一主因。\n\n诊断要把链路拆开：先判定证据是否被正确取得，再判定模型是否遵循证据，最后检查工具和业务事实。分别记录检索 Recall、引用覆盖、忠实性、拒答质量和端到端成功率，用可追溯 bad case 回流修复。",
        "followup": "为什么检索命中正确证据后，模型仍可能给出与证据矛盾的回答？",
    },
    "q1594": {
        "answer": "数学推理、代码生成和软件工程任务应使用不同证据。数学可用 GSM8K 等带标准答案的基准并检查推导/最终答案；代码生成常用 pass@k、HumanEval、MBPP 等可执行单测；真实仓库修复可用 SWE-bench 一类任务并观察测试通过、补丁范围和回归。\n\n基准成绩不能替代业务评测：还要固定模型/提示/工具版本，覆盖安全、成本、延迟和失败样本，并防止训练集污染或测试集泄漏。不同任务的“正确”定义不一样，不能用一个分数概括模型能力。",
        "followup": "为什么代码任务同时报告 pass@k 和补丁质量/安全检查会更可靠？",
    },
    "q1320": {
        "answer": "BatchNorm 依赖 batch 维度的统计量，训练和推理时需要处理不同统计来源；LayerNorm 在单个样本的特征维度上归一化，不依赖同 batch 其他样本。RMSNorm 则以均方根缩放为主，不进行显式去均值。\n\n自回归 Transformer 常使用 LayerNorm 或 RMSNorm，因为序列长度、batch 和 token 位置变化大，且这些归一化更适合该架构的训练/推理路径；这不等于 Transformer 只能使用 LayerNorm。选型应结合模型结构、稳定性、吞吐和质量实验。",
        "followup": "为什么 BatchNorm 的 batch 统计在自回归生成和小 batch 训练中可能不稳定？",
    },
    "q1566": {
        "answer": "Qwen 既有稠密模型，也有 MoE 型号；不能把整个 Qwen 系列都描述成 MoE。MoE 用路由器为每个 token 选择少量专家，在总参数更大时保持较低的激活计算量，目标是在容量和推理成本之间取得平衡。\n\n代价包括专家负载不均、路由训练、跨设备通信、部署复杂度和小 batch 利用率。是否优于同预算稠密模型取决于任务、硬件、并发和训练质量，应通过吞吐、质量、尾延迟和稳定性评测决定。",
        "followup": "为什么 MoE 的总参数很大，却不代表每个 token 都计算所有参数？",
    },
    "q2014": {
        "answer": "模型能力受参数规模、数据质量与覆盖、训练 token/计算预算、架构、后训练和推理策略共同影响。不存在跨任务通用的“0.5B/7B 能力门槛”；较小模型在窄域、分类、抽取或工具路由中可能更合适，较大模型也可能因数据或提示不足表现不佳。\n\n部署还要考虑上下文、并发、延迟、显存、成本、安全和可维护性。应从任务评测和单位经济模型出发，先建立小/大模型、检索和规则的基线，再决定路由或微调方案。",
        "followup": "为什么在窄域高频分类任务中，小模型可能优于直接使用大模型？",
    },
    "q3776": {
        "answer": "双向注意力允许一个位置同时看到左右上下文，适合理解、分类和掩码语言建模；自回归生成则要求第 t 个 token 的预测只能依赖先前 token。若没有因果掩码，训练时模型会看到未来 token，推理生成时这些未来信息不存在，形成训练/推理不一致。\n\n因此普通双向编码器不能直接按 next-token 的方式稳定生成文本。可以通过加入因果掩码、使用 encoder-decoder 架构或改造训练目标支持生成，但不能只因模型使用 attention 就默认具备自回归能力。",
        "followup": "为什么因果掩码会使自回归模型的训练与生成可见信息一致？",
    },
    "q3783": {
        "answer": "Transformer 中 FFN 的参数量通常由隐藏维度和中间维度决定，Attention 的参数量由 Q/K/V/O 投影和头配置决定；哪个占更多并没有固定的“2/3”常数。计算量还随序列长度变化：Attention 的 token 间交互随长度增长更快，FFN 则更多是逐 token 的矩阵乘。\n\n比较时应在具体模型、序列长度、batch、dtype 和硬件上同时测参数、FLOPs、显存、吞吐和质量。降低 FFN 或 Attention 的容量都可能改变表达能力，不能只按参数比例做结论。",
        "followup": "为什么上下文长度增加时，Attention 的成本变化通常比 FFN 更敏感？",
    },
    "q3844": {
        "answer": "选择微调基座先明确任务、数据许可和评测目标：领域语言/代码覆盖、上下文长度、指令/工具能力、安全边界和许可证都要匹配。再评估可用显存、训练时间、推理延迟、量化和部署栈；不要把“24G 只能 7B”或某个厂商清单当作不变规则。\n\n从可复现基线开始，对候选模型用同一数据切分、训练预算和目标/回归集比较。小模型、LoRA/QLoRA、RAG、蒸馏或更大基座各有适用条件，最终以质量、成本、延迟与可维护性共同决定。",
        "followup": "为什么微调基座选型时，许可证和部署约束与离线指标同样重要？",
    },
    "q1194": {
        "answer": "流式协议的半段 JSON/DSL 不能靠“补一个括号再直接解析”来修复并执行。前端应把流按 framing 协议或增量 parser 缓冲，只有在确认一个完整 payload、长度和类型都通过 Schema 校验后，才进入渲染或工具调用路径；不完整内容只做安全文本展示或等待后续片段。\n\n渲染层应使用组件白名单、受限属性、错误边界和资源限额，未知/非法消息进入可观测的错误或降级状态，不能让任意模型输出执行脚本或导致整页崩溃。对工具动作还应在服务端再次做权限和语义校验。",
        "followup": "为什么“能解析成 JSON”仍不足以让前端直接执行一条工具指令？",
    },
    "q3332": {
        "answer": "OAuth 的关键优势是第三方应用不必直接收集和保存用户密码；用户在授权服务器完成认证后，客户端获得受范围、有效期和撤销机制约束的 access token，必要时使用 refresh token。它并不意味着“没人看到凭证”：token 本身通常是高价值 bearer credential。\n\n实现要保护 redirect URI、state/PKCE、scope、token 的安全存储、传输和轮换，并处理过期与撤销。Web 客户端还需结合 XSS/CSRF 威胁模型选择存放方式，不能把 OAuth 当作自动解决全部身份安全问题的协议。",
        "followup": "为什么 access token 泄露后，即使用户密码未泄露，仍可能造成严重风险？",
    },
    "q3634": {
        "answer": "手机号、身份证号、地址等低熵 PII 不适合直接用裸确定性 hash 做查询索引，因为攻击者可以枚举候选值并反查 hash。需要等值查询时，可在受保护密钥下计算 HMAC 或 pepper 参与的 blind index，并把密钥版本与索引记录在案。\n\n密文或原始 PII 应与索引分离存放，访问受最小权限、审计和脱敏控制；密钥轮换时支持新旧索引并存和渐进回填。模糊查询、去重与统计还需要单独评估泄露面，不能靠一个 hash 解决所有隐私需求。",
        "followup": "为什么对低熵手机号做 SHA-256 后仍容易被离线枚举？",
    },
    "q4130": {
        "answer": "已知 8 个球中恰有一个偏重时，最少 2 次称量即可：先把 8 个球分成 3、3、2 三组，称两组 3 个。若平衡，偏重球在剩余 2 个中，再称其中 1 个和一个正常球；若不平衡，偏重球在较重的 3 个中，第二次称其中 1 对，平衡则第三个偏重，不平衡则较重者偏重。\n\n每次天平称量有三种结果，两次最多区分 9 种状态，足以区分 8 个候选；这里依赖“异常球已知偏重”的前提。若不知偏轻还是偏重，信息量和最少次数会不同。",
        "followup": "为什么已知偏重与未知偏轻/偏重会导致不同的称量下界？",
    },
    "q0877": {
        "answer": "在连续转动的区间 `[00:00, 24:00)` 内，时针、分针和秒针三者严格重合只有 2 次：00:00:00 与 12:00:00；24:00 与 00:00 是同一边界，不重复计数。时针和分针在同一时间范围内会重合 22 次。\n\n题目必须说明是连续运动、统计区间和是否包含终点，否则“24 小时内”容易把同一时刻重复计数，或把两针重合误写成三针重合。",
        "followup": "为什么时分针重合次数比三针严格重合次数多得多？",
    },
    "q0880": {
        "answer": "以“三个人、三只鬼；船最多载两者；任一岸只要有人，鬼数不能多于人数”为约束，一条可验证序列是：鬼鬼过、鬼回、鬼鬼过、鬼回、人人过、人鬼回、人人过、鬼回、鬼鬼过、鬼回、鬼鬼过。每一步后检查两岸：若某岸有人，则人数都不少于鬼数。\n\n这类题的关键不是背步骤，而是先把状态表示为 `(左岸人, 左岸鬼, 船侧)`，枚举合法载客组合并排除会造成任一岸失衡的状态；这样才能验证最短路径或处理不同人数的变体。",
        "followup": "如何用状态图或 BFS 验证这条过河序列是否最短？",
    },
    "q0171": {
        "answer": "抢红包的核心是把金额、人数、幂等、并发扣减和审计拆开设计。金额生成可在满足总额、最小单位和剩余人数约束下随机分配；常见“二倍均值”只是控制单次金额范围的启发式，并不保证结果接近正态分布。钱数应使用整数最小货币单位，不能用二进制浮点累计。\n\n领取路径通常需要原子地判断资格、扣减剩余额度/名额并记录用户领取结果；可用数据库事务、缓存原子脚本或队列削峰，具体取决于一致性与流量。还要处理重复点击、超卖、退款/补偿、风控、过期和对账，最终以账务可追溯与压测结果验证。",
        "followup": "为什么红包金额计算与领取扣减都应避免使用浮点数？",
    },
})


# Rewrite the last conversational/project-specific titles found by the final
# self-contained-title sweep.  The retained answers teach a reusable concept,
# not an undocumented former project.
EXTRA_DROP_IDS.update({"q2307"})
EXTRA_MOVE_TO.update({
    "q1469": "behavioral", "q2131": "agent", "q2337": "safety", "q2634": "engineering",
    "q2884": "agent", "q3052": "llm-basics", "q3170": "frontend", "q3174": "behavioral",
    "q3179": "behavioral", "q3333": "frontend", "q3334": "frontend", "q3336": "os-network",
    "q3337": "engineering", "q3338": "os-network", "q3340": "engineering", "q3342": "mysql",
    "q3346": "engineering", "q3349": "frontend", "q3350": "engineering", "q3351": "safety",
    "q3958": "agent",
})
EXTRA_TITLE_REWRITES.update({
    "q1469": "产品需求如何从提出、澄清到开发、验证和迭代？",
    "q2131": "Agent 如何把复杂用户问题拆解为可执行、可验证的行动计划？",
    "q2337": "高风险事实问题如何交叉验证 AI 回答与权威来源？",
    "q2581": "Vue 组件触发 emit 后，父组件监听回调与后续代码的执行顺序如何确定？",
    "q2634": "执行时间长于调度周期的任务，如何防止定时重入和并发重复执行？",
    "q2660": "如何评估低代码平台的产品价值、工程质量与可维护性？",
    "q2666": "低代码平台如何用 JSON Schema 定义组件间的数据与事件联动？",
    "q2712": "前端如何处理敏感数据？加密、脱敏与访问控制的边界是什么？",
    "q2752": "低代码平台通常交付哪些产物？如何从 Schema 生成可运行页面？",
    "q2754": "低代码画布中组件宽高如何记录？应选择 px、百分比还是相对单位？",
    "q2774": "低代码组件资源中心如何管理组件版本、依赖和兼容性？",
    "q2782": "低代码平台的编辑态与预览态有哪些差异？如何共享 Schema 与渲染逻辑？",
    "q2818": "什么情况下需要为前端项目自定义 Webpack 配置？",
    "q2821": "前端构建中应如何分别处理 CSS、JavaScript、图片等资源？",
    "q2884": "深入理解 Agent 底层机制对自定义规划、记忆和工具控制有什么价值？",
    "q3052": "文本在 LLM 推理前如何分词、编码并放入计算设备？",
    "q3170": "如何解释 Vue 的 v-show，以及它与 v-if 的选型边界？",
    "q3174": "为什么有些人编码能力强却在技术面试中表现不佳？如何改善？",
    "q3179": "如何设计更能评估真实工程能力的技术面试？",
    "q3333": "前端应用为何需要本地持久化？它如何减轻网络重传与服务端压力？",
    "q3334": "前端本地持久化有哪些实现方式？localStorage 的边界是什么？",
    "q3336": "WebSocket 为什么常需要心跳？如何处理断线、重连和网络切换？",
    "q3337": "CDN 如何加速静态资源分发？缓存刷新与回源如何设计？",
    "q3338": "Web 服务如何正确部署 TLS 证书链并维护 HTTPS？",
    "q3340": "中文检索系统如何做分词、倒排索引与查询分析？",
    "q3342": "事务原子性是什么？数据库如何保证成功或整体回滚？",
    "q3343": "Vue 单页应用的构建、路由与部署架构如何设计？",
    "q3346": "服务端如何管理 Web Session 登录态？Cookie、存储与过期如何设计？",
    "q3349": "如何选择或集成 WYSIWYG 编辑器，并处理安全、扩展和内容存储？",
    "q3350": "AJAX 异步交互与服务端事务边界应如何设计？",
    "q3351": "Web 应用如何实现 OAuth 登录并处理回调、状态校验与令牌安全？",
    "q3354": "Vue 项目何时需要 jQuery？如何避免与响应式 DOM 管理冲突？",
    "q3958": "Agent 系统如何记录一次任务的完整执行轨迹以支持重放与审计？",
    "q0510": "应如何根据查询模式、选择性和写入成本选择建立索引的字段？",
    "q3339": "中文检索系统为何常用 Elasticsearch？分词与倒排索引如何发挥作用？",
    "q1350": "如何系统回答 AI Agent 或 RAG 项目中的最大工程挑战？",
})


# Final self-contained-title sweep: these were still readable only as a
# continuation of an interviewer dialogue.  Their retained answers are useful,
# but the titles now state the technical object or interview intent explicitly.
EXTRA_TITLE_REWRITES.update({
    "q3964": "在什么场景下应使用 Agent，而不是固定工作流与规则引擎？",
    "q1425": "如何在项目中实现受约束的模型路由？",
    "q2200": "如何量化并说明项目的质量保障成效？",
    "q2811": "如何回答“项目中遇到过哪些难点，以及如何解决？”",
    "q3213": "如何回答“项目是否上线、上线后发现哪些问题并如何解决？”",
    "q1503": "如何回答“项目落地过程中遇到过哪些棘手问题？”",
    "q3400": "项目中如何使用 Elasticsearch（ES）实现检索与分析？",
    "q2768": "React 在什么情况下更新虚拟 DOM 树？render 阶段如何工作？",
    "q2786": "低代码组件开发完成后，交付给平台的产物包包含哪些内容？",
    "q2719": "项目中如何使用 TypeScript 保障接口与状态的类型安全？",
    "q2557": "CORS 为什么需要预检请求（Preflight）？",
    "q2632": "父元素设置 opacity 后，为什么子元素不能通过 opacity: 1 恢复不透明？",
    "q2680": "Redux 的 dispatch 如何将 action 交给对应的 reducer 处理？",
    "q2701": "如何在面试中说明自己在一次迭代中负责的模块与贡献？",
    "q2762": "React 的 setState 是同步还是异步的？",
    "q2767": "大模型的权重与能力是如何更新的？完整训练流程是什么？",
    "q3005": "在技术面试中，为什么要说明某个技术区别对工程决策的重要性？",
    "q3150": "AI Agent 相关技术面试相对传统后端面试发生了哪些变化？",
    "q3394": "项目中如何创建线程池，为什么不建议直接使用 Executors？",
    "q2688": "低代码编辑器如何实现组件拖拽、边界检测、吸附与自动落位？",
})

EXTRA_FIELD_FIXES.update({
    "q2557": {"kaodian": "考察 CORS 预检的触发条件、授权流程，以及它与同源策略和请求副作用的关系。"},
    "q2632": {"kaodian": "考察 CSS opacity 的合成边界，以及实现“背景半透明、内容不透明”的正确分层方式。"},
    "q2680": {"kaodian": "考察 Redux 中 dispatch、根 reducer、combineReducers 与 action.type 的分发关系。"},
    "q2701": {"kaodian": "考察如何在项目经历面试中清晰说明模块边界、个人职责、结果与协作关系。"},
    "q2762": {"kaodian": "考察 React setState 的调用、批处理与提交时机，以及 React 版本和更新上下文的影响。"},
    "q2767": {"kaodian": "考察大模型权重更新的前向传播、反向传播、优化器和参数高效微调边界。"},
    "q3005": {"kaodian": "考察技术面试中如何把概念差异落到约束、选型、性能与正确性等工程决策。"},
    "q3150": {"kaodian": "考察 AI Agent 面试相对传统后端面试在编排、评测、成本和可靠性上的能力要求。"},
})


# Final transcript-fragment sweep: retain only standalone prompts and merge
# broad paraphrases into their narrower canonical questions.
EXTRA_DROP_IDS.update({"q2346", "q2869", "q3348"})
EXTRA_MERGED_INTO.update({
    "q3181": "q1203",
    "q1942": "q1548",
    "q2941": "q1385",
    "q2094": "q1441",
    "q2095": "q1441",
    "q3668": "q1441",
    "q3493": "q3547",
})
EXTRA_MOVE_TO.update({
    "q1731": "agent", "q1732": "agent", "q2930": "agent", "q2946": "agent",
    "q3119": "safety", "q3321": "frontend", "q3388": "behavioral",
    "q3670": "behavioral", "q2207": "behavioral",
})
EXTRA_TITLE_REWRITES.update({
    "q0080": "本地缓存与 Redis 组成多级缓存时，如何保持数据同步与最终一致？",
    "q1731": "任务型多轮对话如何维护状态，以正确解析指代和省略式输入？",
    "q1732": "对话式 AI 在信息不足时，如何用澄清问题把意图收敛到可执行分支？",
    "q1740": "AI Agent 或后端系统如何设计分层稳定性保障？",
    "q2930": "Agent 在任务执行中重新规划时，如何重注入目标、进度与新增约束？",
    "q2946": "多 Agent 协作中如何设计上下文隔离、最小可见性与结果汇总？",
    "q3119": "什么是数据主权？它与数据本地化、数据驻留和隐私保护有何区别？",
    "q3214": "大模型推理常用哪些加速框架与优化手段？应如何验证取舍？",
    "q3271": "如何回答“为什么选择这家公司或岗位”，避免只谈个人情怀？",
    "q3321": "meta viewport 与 http-equiv 分别有什么作用和使用边界？",
    "q3388": "面试官追问“还有吗？”时，如何结构化补充并诚实说明知识边界？",
    "q3670": "AI/RAG 面试如何从概念背诵提升到原理、选型与落地回答？",
    "q0752": "HTTP 服务如何在后续请求识别同一用户，并在集群中共享会话状态？",
    "q1588": "如何系统分析并优化生产环境中大模型服务的延迟、稳定性与成本？",
    "q2207": "如何通过学习其他编程语言的心智模型与生态，反哺 Java 工程能力？",
})
EXTRA_FIELD_FIXES.update({
    "q1731": {"kaodian": "考察任务型多轮对话的流程状态、槽位维护与省略/指代解析。"},
    "q1732": {"kaodian": "考察对话式 AI 在意图不确定或关键槽位缺失时的澄清策略与安全边界。"},
    "q1740": {"kaodian": "考察限流、超时、重试、熔断、幂等、降级和可观测性组成的分层稳定性设计。"},
    "q2930": {"kaodian": "考察 Agent 增量规划时如何压缩进度、重注入目标并避免重复执行已完成步骤。"},
    "q2946": {"kaodian": "考察多 Agent 的私有上下文、最小权限可见性、独立审查与编排器汇总机制。"},
    "q3119": {"kaodian": "考察跨区域数据治理中数据主权、数据驻留、本地化、隐私和访问控制的边界。"},
    "q3214": {"kaodian": "考察大模型推理的显存、计算、调度和通信瓶颈，以及基于评测的优化取舍。"},
    "q3271": {"kaodian": "考察如何用可核验的业务理解、岗位匹配和长期成长回答求职动机。"},
    "q3321": {"kaodian": "考察移动端 viewport 设置与 http-equiv 的用途、限制和现代替代方案。"},
    "q3388": {"kaodian": "考察技术面试追问时的结构化补充、诚实边界和话题引导能力。"},
    "q3670": {"kaodian": "考察 AI/RAG 面试中从概念到原理、选型、边界和真实落地验证的表达方式。"},
    "q0752": {"kaodian": "考察 Cookie/Session、令牌、共享会话存储和集群登录态的安全与扩展取舍。"},
})

EXTRA_OVERRIDES.update({
    "q0752": {
        "answer": "HTTP 本身无状态，服务端要在后续请求识别同一用户，常见做法是把一个受保护的凭证随请求带回。最常见的是 Cookie + 服务端 Session：登录成功后服务端生成不可预测的会话标识，浏览器通过 `Secure`、`HttpOnly`、合适的 `SameSite` Cookie 回传；服务端再用该标识读取用户会话。Cookie 中应保存不透明 ID，而不是敏感资料。\n\n集群部署时，不能假定会话只留在某台应用机器内存。可以把 Session 存到 Redis 或数据库等共享存储；也可在明确故障与扩容边界后使用粘性会话。共享存储需要高可用、过期清理、容量与故障演练，不能简单把它称作单点。\n\n另一条路径是签名令牌，例如 JWT。它能让服务端离线校验部分声明，减少每次查 Session 的需求，但 JWT 默认不是加密，也不天然解决登出、吊销、权限变更和泄露后的失效问题；高风险系统往往仍需短期令牌、轮换、撤销表或服务端状态。因此不能把 JWT 说成集群下必然优于 Session。选择应看是否需要即时撤销、权限实时性、浏览器/移动端威胁模型和运维成本。",
        "followup": "为什么把访问令牌放在浏览器 localStorage 与放在 HttpOnly Cookie 中，会面对不同的 XSS/CSRF 风险？",
    },
    "q3214": {
        "answer": "大模型加速先要定位瓶颈，而不是先堆框架：Prefill 常更受矩阵计算影响，逐 token Decode 往往更受显存带宽、KV Cache、排队和调度影响。先在真实上下文长度、并发和请求分布下记录 TTFT、TPOT、端到端 p95/p99、吞吐、显存、队列、错误率与单位成功请求成本。\n\n常用推理引擎包括 vLLM、TensorRT-LLM、TGI、SGLang 等；它们通常提供连续批处理、KV Cache 管理、并行和 kernel 优化。可选手段包括权重量化、GQA/MQA、分页或前缀复用的 KV Cache、张量/流水线并行、Prefill/Decode 分离、投机解码和缓存。每种手段都有条件：量化需要质量回归，批处理提高吞吐但可能恶化尾延迟，并行会增加通信成本，缓存要处理时效与隔离。\n\nFlashAttention 是 IO 感知的精确注意力实现：它避免物化完整注意力矩阵并减少高带宽显存访问和额外显存占用，但不把标准精确注意力的 O(n²) 计算复杂度改成线性。最终应固定模型、提示、硬件和负载，以任务成功率、安全回归、延迟、吞吐和成本共同比较，而不是只报告某个 token/s 数字。",
        "followup": "为什么在优化 LLM 服务时，需要把 Prefill 与 Decode 的指标和资源占用分开观察？",
    },
    "q3271": {
        "answer": "回答“为什么选择这家公司或岗位”时，重点不是证明自己喜欢某个品牌，而是说明这是一次有依据的双向选择。可以用“业务理解—岗位匹配—成长取舍”三步：先引用自己确认过的公开业务、产品或技术方向；再把其中一两个真实挑战与自己的经历、想发展的能力对应；最后说明自己也看重的协作方式、成长空间或约束。\n\n不要把未经验证的技术细节、市场数据或虚构项目成果说成事实，也不要把“我喜欢这个产品”当成全部理由。若信息有限，可以明确说哪些来自公开资料、哪些需要在面试中进一步了解，并反问团队当前最重要的目标和难题。这样既表达动机，也保留职业判断和真实性。",
        "followup": "如何把同一段“为什么选择公司”的回答，针对不同岗位的职责重点进行调整？",
    },
    "q3321": {
        "answer": "`<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">` 用于告诉移动浏览器按设备 CSS 宽度建立布局视口，避免桌面宽度页面被整体缩小；`viewport-fit=cover` 可配合安全区变量处理异形屏。不要轻易设置 `user-scalable=no` 或过窄的最大缩放，因为这会损害无障碍。\n\n`http-equiv` 是 HTML 中对少数响应行为的兼容性提示，例如 `refresh`；它不能替代真正的 HTTP 响应头。编码应优先写 `<meta charset=\"UTF-8\">`，缓存、安全策略、跳转和 CSP 等生产行为应尽可能由服务器响应头控制；某些 CSP 指令也只能通过响应头生效。两者都放在 `head` 中，但 viewport 解决页面布局，http-equiv 只是有限的协议兼容机制。",
        "followup": "为什么移动端页面只写响应式 CSS、却漏掉 viewport 时仍可能出现整体缩小？",
    },
    "q3119": {
        "answer": "数据主权讨论的是：数据的存放、访问、处理和跨境传输会受到相关司法辖区法律、合同和监管要求的约束。它不是单一技术属性，具体义务必须结合数据类型、主体、地区和当前法规由合规/法务确认。\n\n它与几个相近概念不同：数据驻留（data residency）强调数据实际存放在哪个区域；数据本地化（data localization）是某些场景下要求在特定区域存储或处理的规则；隐私保护关注个人信息的合法、透明、最小化处理与主体权利。它们可能重叠，但不能互相替代。\n\n工程上应维护数据分类和流转图，按区域与租户隔离数据平面，实施最小权限、加密与密钥管理、跨境访问审计、保留/删除策略和供应商评估。面对跨境、重要数据或敏感个人信息的实际场景，应先确定适用地区和业务事实，再走正式合规评审，而不是从一条通用面试答案推导法律结论。",
        "followup": "为什么“数据存放在某区域”不自动等于满足该区域所有的数据访问与跨境合规要求？",
    },
})
