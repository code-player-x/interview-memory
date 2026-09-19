# Java

> 题目数量：**53** ｜ 渲染时间：自动 ｜ 源：authored/java.jsonl

---

## 1. 如何用Spring AI Alibaba实现一个生产级RAG系统？

> 原题 ID：`q1926`

**高频程度**：★★★★

**考察点**：考察生产级 RAG 流水线的分阶段设计与工程化要点。

**回答框架**：

1) 文档接入与切分：DocumentReader + 语义/Token 切分，保留 metadata（来源/权限/版本），chunk 300~800 token、重叠 10%~20%；2) 向量化与存储：选 Embedding 模型与 VectorStore，建 HNSW/IVF 索引、做多租户隔离；3) 检索：向量召回 TopK，可叠加 BM25 混合召回与 Rerank；4) 生成：Prompt 组装 + 引用标注 + 结构化输出；5) 可观测与评估：召回率/命中率、降级与缓存。

**参考回答**：

用 Spring AI Alibaba 搭建生产级 RAG，核心是把「文档接入→切分→向量化→检索→重排→Prompt 组装→LLM 生成→评估与可观测」做成可配置、可降级、可观测的流水线，而不是简单调一次向量库查询。

生产级 RAG 可以类比成「开卷考试」：向量库是图书馆，检索是找资料，重排是挑最相关的几页，Prompt 是答题纸，LLM 是考生。Spring AI Alibaba 提供 ChatClient、EmbeddingModel、VectorStore、Advisor、DocumentReader/Transformer/Writer 等抽象，把这条链路标准化。

1) 文档接入与切分：用 DocumentReader 读取 PDF/Word/网页/数据库，按 TokenTextSplitter 或语义切分，保留 metadata（来源、标题、时间、权限、版本）。切分粒度通常 300~800 token，重叠 10%~20%，避免语义截断。

2) 向量化与存储：EmbeddingModel 选 DashScope text-embedding-v3 或本地 BGE，VectorStore 可用 AnalyticDB、Milvus、PGVector、Redis。生产上要建 HNSW/IVF 索引，并做多租户隔离（tenant_id 过滤）。

3) 检索：先做向量相似度召回 TopK（如 20），再叠加关键词 BM25 做混合检索，解决专有名词、编号、缩写召回差的问题。

4) 重排：用 Rerank 模型（如 gte-rerank、bge-reranker）对 TopK 精排，取 TopN（3~5）送给 LLM，显著提升准确率。

5) Prompt 组装与生成：用 Advisor 把检索结果注入 System/User 消息，要求模型「只依据上下文回答，无依据则说不知道」，并附引用来源。ChatClient 支持流式输出、多轮记忆、工具调用。

6) 生产化：加缓存（问题→答案、embedding 缓存）、限流熔断、异步索引、增量更新、权限过滤、敏感词过滤、幻觉检测、RAGAS 评估（faithfulness、answer relevancy、context precision/recall）、Trace 可观测（Micrometer/OpenTelemetry）。

7) 降级：向量库不可用时降级到关键词检索；LLM 超时降级到模板回答；重排失败直接跳过。

适用场景：企业知识库问答、客服、文档助手、代码问答。不适合强实时、强事务、纯结构化查询场景。

**常见追问**：RAG 检索效果差，你会优先调哪一环？

---

## 2. 如何将《SpringAI 智能面试平台+RAG知识库》实战项目写进简历？

> 原题 ID：`q1968`

**高频程度**：★★★

**考察点**：考察把 AI 项目写进简历的表达方法：痛点→方案→量化结果。

**回答框架**：

1) 一句话定位：用户、场景、价值；2) 技术方案：分层写清接入层、RAG 链路（切分/向量/召回/重排/Prompt）、业务能力（出题/追问/评分）；3) 量化结果：准确率、时延、成本、替代人工的比例；4) 突出个人负责的难点与取舍，避免罗列技术栈。

**参考回答**：

把项目写成‘业务痛点→技术方案→量化结果’的闭环，突出RAG链路与SpringAI工程化能力，而非罗列技术栈。

简历上写这个项目，核心是让面试官一眼看到你‘用AI解决了一个真实业务问题’，而不是‘我学过SpringAI’。建议按四段式组织：

1）项目一句话定位：例如‘基于SpringAI + RAG的智能面试平台，为HR提供岗位定制化出题、简历追问与自动评分，替代人工初筛’。点明用户、场景、价值。

2）技术方案（体现架构能力）：
- 接入层：Spring Boot + SpringAI，统一封装ChatClient、EmbeddingModel、VectorStore，屏蔽不同大模型厂商差异；
- RAG链路：文档解析（PDF/Word）→ 分块（按语义/标题，chunk 500~800 token，overlap 10%~20%）→ Embedding → 向量库（如Milvus/PgVector/Redis）→ 检索（向量+BM25混合召回）→ Rerank → 拼Prompt → LLM生成；
- 面试业务：题库/简历/岗位JD入库，按岗位检索出题；多轮追问用会话记忆（ChatMemory）；评分用结构化输出（JSON Schema/Function Calling）。

3）量化结果：检索命中率从X%提升到Y%、人工初筛耗时下降Z%、面试题生成采纳率、QPS/响应延迟（如P95<2s）、成本（token消耗下降）。没有真实数据就用合理估算并说明口径。

4）个人贡献：明确‘我负责了什么’，如设计分块与混合检索策略、解决幻觉与引用溯源、做流式输出（SSE）与降级。

通俗类比：RAG就像‘开卷考试’——LLM是考生，向量库是参考书，检索是翻书找答案，Rerank是挑出最相关的几页，Prompt是告诉考生‘只根据这几页回答并标注出处’。SpringAI则是把‘找书、翻书、答题’这套流程标准化成可插拔的组件。

**常见追问**：如果没有线上量化数据，简历上怎么写结果？

---

## 3. 工业级实战：深入理解 Spring 官方的 AI 抽象层，掌握如何通过统一的声明式接口对接通义千问、OpenAI 等主流模型？

> 原题 ID：`q1979`

**高频程度**：★★★

**考察点**：考察 Spring AI 分层抽象（Model/Client/Advisor）与声明式统一接口。

**回答框架**：

1) 底层 ChatModel/EmbeddingModel 是最小契约，各厂商各写实现；2) 中层 ChatClient 是声明式 Fluent API，业务面向它编程；3) 上层 Advisor 类似 Filter/AOP，可织入记忆、RAG、日志、限流、内容安全；4) 换模型只改配置，依赖注入与自动配置统一治理。

**参考回答**：

Spring AI 通过统一的声明式接口（ChatClient/ChatModel + Advisor + 结构化输出）屏蔽各家大模型差异，让业务代码只依赖抽象、切换模型只改配置。

Spring AI 的核心思想是『把大模型调用当成 Spring 里的一种普通资源』，用大家熟悉的依赖注入、自动配置、AOP 思路来治理 AI 调用。

1) 分层抽象：
- 底层 ChatModel/EmbeddingModel/ImageModel 接口：定义 call(Prompt)->ChatResponse 这类最小契约，OpenAI、通义千问（DashScope）、Ollama、Azure OpenAI 各写一个实现类。
- 中层 ChatClient：声明式、流式（Flux）的 Fluent API，类似 WebClient/RestClient 的定位，业务代码面向它编程。
- 上层 Advisor：类似 Servlet Filter / AOP 拦截器，可在调用前后织入记忆（ChatMemory）、RAG 检索（QuestionAnswerAdvisor）、日志、限流、内容安全。

2) 统一声明式接口的体现：
- 依赖 starter（如 spring-ai-openai-spring-boot-starter、spring-ai-dashscope-spring-boot-starter），通过 application.yml 配置 api-key、base-url、model 名，自动装配出对应 ChatModel Bean。
- 业务里注入 ChatClient，写 chatClient.prompt().user("...").call().content()，切换厂商时只改 pom 依赖和配置，代码零改动。
- 结构化输出：.entity(MyRecord.class) 让框架把模型返回的 JSON 反序列化成 Java 对象，内部用 BeanOutputConverter 生成 JSON Schema 提示词并解析。

3) 通俗类比：
- ChatModel 像 JDBC Driver，各家厂商各写驱动；ChatClient 像 JdbcTemplate/MyBatis，业务只写 SQL 式声明；Advisor 像 MyBatis 插件/Spring 拦截器，横切逻辑统一插拔。
- 换模型就像换数据库连接串，不用重写 DAO。

4) 适用场景：
- 需要多模型容灾/比价/合规切换（国内用通义，海外用 OpenAI）。
- 需要统一做 RAG、对话记忆、可观测性、限流的中台型 AI 应用。
- 不适合：需要用到某厂商独有能力（如特定 function call 细节、私有参数）时，抽象层可能覆盖不到，需要下沉到原生 SDK。

**常见追问**：Advisor 的执行顺序是怎么控制的？

---

## 4. 精通Java核心技术，熟悉JVM原理、多线程编程？

> 原题 ID：`q2227`

**高频程度**：★★★

**考察点**：考察「精通 Java」的能力边界：核心、JVM 原理、多线程。

**回答框架**：

1) Java 核心：集合/泛型/反射/IO-NIO/Stream，理解实现与复杂度（如 HashMap 数组+链表+红黑树）；2) JVM：类加载与双亲委派、运行时数据区、对象布局、GC（可达性、分代、G1/ZGC）、JIT 与逃逸分析；3) 多线程：JMM 与 happens-before、synchronized 锁升级、AQS、CAS、线程池、并发容器；4) 能定位 OOM/死锁/性能问题并调优。

**参考回答**：

精通Java核心技术意味着不仅会用API，更要理解JVM内存模型、类加载、GC与多线程并发底层机制，能定位OOM/死锁/性能问题并做调优。

‘精通Java核心技术，熟悉JVM原理、多线程编程’通常包含三层：
1) Java核心：集合、泛型、反射、IO/NIO、异常、Lambda/Stream，理解其实现与复杂度，例如HashMap的数组+链表+红黑树、扩容与hash扰动。
2) JVM原理：类加载（双亲委派、加载-验证-准备-解析-初始化）、运行时数据区（堆、栈、方法区/元空间、程序计数器、本地方法栈）、对象创建与内存布局、GC（可达性分析、分代收集、G1/CMS/ZGC、STW）、JIT与逃逸分析。
3) 多线程：JMM（主内存/工作内存、happens-before、volatile的可见性与禁止重排序）、synchronized锁升级、AQS与ReentrantLock、CAS与原子类、线程池参数与拒绝策略、并发容器（ConcurrentHashMap、CopyOnWriteArrayList）、CompletableFuture。
通俗类比：JVM像一家餐厅，堆是仓库（对象存放，GC是保洁），栈是每个服务员的点菜单（线程私有），方法区/元空间是菜谱和规则；多线程像多个服务员同时工作，JMM规定他们如何共享白板信息，锁是包间钥匙，volatile是‘最新公告必须立刻同步’。
适用场景：高并发服务、缓存、异步任务、大数据处理；排查CPU飙高、内存泄漏、频繁Full GC、死锁、线程池打满等问题。

**常见追问**：你说的「精通」，能举一个你实际排查过的线上问题吗？

---

## 5. 深入理解JVM底层原理、MySQL内核、分布式事务、高可用架构设计？

> 原题 ID：`q2228`

**高频程度**：★★★

**考察点**：考察对 JVM/MySQL/分布式事务/高可用四块的原理级理解与取舍。

**回答框架**：

1) JVM：内存结构、GC 收集器演进、类加载、调优取舍（吞吐 vs 停顿）；2) MySQL：InnoDB 架构（Buffer Pool/Change Buffer）、B+ 树索引与回表、redo/undo/binlog 与两阶段提交、隔离级别；3) 分布式事务：2PC/3PC、TCC、Saga、本地消息表与最终一致性；4) 高可用：集群、主从、限流熔断降级、多活与容灾。

**参考回答**：

从JVM内存模型与GC、MySQL存储引擎与事务日志、分布式事务一致性协议、高可用架构四个层面，讲清底层原理、数据流、取舍与扩展性。

一、JVM底层原理
1. 内存结构：堆（新生代Eden+S0/S1、老年代）、方法区（JDK8后元空间，本地内存）、虚拟机栈、本地方法栈、程序计数器。对象分配优先TLAB，大对象直接进老年代，长期存活对象晋升。
2. GC原理：可达性分析（GC Roots：栈引用、静态变量、常量、JNI引用）。分代收集：Minor GC复制算法，Full GC标记-清除/整理。常见收集器：CMS（并发标记清除，碎片、Concurrent Mode Failure）、G1（Region化，可预测停顿，SATB）、ZGC（染色指针+读屏障，亚毫秒停顿）。
3. 类加载：加载-验证-准备-解析-初始化，双亲委派打破场景（SPI、Tomcat）。
4. 调优取舍：吞吐量vs停顿时间，堆大小与GC频率，元空间OOM排查。

二、MySQL内核
1. InnoDB架构：Buffer Pool（LRU改进，分young/old区，防全表扫描污染）、Change Buffer、Log Buffer、自适应哈希。
2. 索引：B+树，聚簇索引叶子存行数据，二级索引存主键，回表；覆盖索引、最左前缀、索引下推。
3. 事务与日志：redo log（WAL，物理日志，循环写，crash-safe）、undo log（逻辑日志，MVCC+回滚）、binlog（Server层，逻辑日志，主从复制）。两阶段提交：prepare redo -> write binlog -> commit redo，保证主从一致。
4. 隔离级别：读未提交、读已提交（RC）、可重复读（RR，默认，MVCC+间隙锁防幻读）、串行化。MVCC：ReadView + undo版本链，RC每次读生成ReadView，RR事务首次读生成。
5. 锁：记录锁、间隙锁、临键锁、插入意向锁，死锁检测。

三、分布式事务
1. 理论：CAP（一致性、可用性、分区容忍，三选二，实际AP/CP取舍）、BASE（基本可用、软状态、最终一致）。
2. 方案：
   - 2PC/3PC：协调者，阻塞、单点，数据库XA。
   - TCC：Try-Confirm-Cancel，业务补偿，需幂等、防悬挂、空回滚。
   - 本地消息表：业务与消息同库事务，定时投递，最终一致。
   - 事务消息：RocketMQ半消息+回查。
   - Saga：长事务拆本地事务+补偿，适合长流程。
   - 最大努力通知：对账兜底。
3. 取舍：强一致（2PC）性能差；最终一致（消息、Saga）性能好但需幂等、对账、补偿。

四、高可用架构
1. 分层：接入层（DNS轮询、LVS/Keepalived、Nginx）、应用层（无状态、集群、限流熔断降级）、数据层（主从复制、MHA/MGR、分库分表、读写分离）。
2. 数据高可用：MySQL主从半同步/组复制，Redis哨兵/Cluster，Kafka多副本ISR。
3. 容灾：同城双活、异地多活，单元化，流量调度，数据同步（binlog、DTS）。
4. 取舍：一致性vs可用性，成本vs恢复时间（RTO/RPO）。

文字示意图：
客户端 -> DNS/LVS -> Nginx集群 -> 应用集群(无状态) -> 缓存/消息/DB(主从+分片)
JVM: 类加载 -> 运行时数据区 -> 执行引擎 -> GC
MySQL: 连接器 -> 分析器 -> 优化器 -> 执行器 -> InnoDB(Buffer Pool + redo/undo) + binlog
分布式事务: 业务 -> 本地事务+消息表 -> MQ -> 下游消费+幂等 -> 对账

**常见追问**：分布式事务里你更倾向哪种方案？为什么？

---

## 6. 优先成熟方案，不要盲目追新：企业级落地优先选择Spring AI、LangChain4j等成熟框架，不要自己从零实现核心逻辑？

> 原题 ID：`q2233`

**高频程度**：★★★

**考察点**：考察企业级 AI 落地的选型原则：优先成熟框架，聚焦差异化。

**回答框架**：

1) 核心逻辑包括多供应商适配、Prompt 管理、会话记忆、RAG、Tool Calling、结构化输出、流式、可观测与重试降级；2) 这些在 Spring AI/LangChain4j 已有生产验证，自研重复踩坑；3) 自研精力应放在业务编排与差异化能力；4) 选型看社区活跃度、供应商覆盖、技术栈契合、License 与可扩展点。

**参考回答**：

企业级 AI 落地应优先选用 Spring AI、LangChain4j 等成熟框架，把自研精力集中在业务编排与差异化能力上，而非从零实现模型调用、RAG、工具调用等核心逻辑。

在企业级落地中，AI 应用的核心逻辑包括：模型接入与多供应商适配、Prompt 模板管理、对话记忆、RAG（文档加载/切分/向量化/检索/重排）、Function/Tool Calling、结构化输出解析、流式响应、可观测性与重试降级等。这些能力在 Spring AI、LangChain4j、LangChain 等成熟框架中已有大量生产验证，自己从零实现会重复踩坑且维护成本极高。

以 Java 技术栈为例：Spring AI 提供 ChatClient、Advisor、VectorStore、EmbeddingModel、ToolCallback 等抽象，天然融入 Spring Boot 的自动配置、依赖注入与可观测体系；LangChain4j 提供 AiServices 声明式接口、ChatMemory、ContentRetriever、EmbeddingStore 等，对多模型供应商（OpenAI、Azure、通义、Ollama 等）有统一适配。选型时应评估：社区活跃度与版本迭代、供应商覆盖、与现有技术栈契合度、License、可扩展点（能否自定义 Retriever/Advisor）、可观测与评测支持。

正确姿势是：用框架承载通用能力，用自研承载业务价值。例如用 LangChain4j 的 AiServices 定义业务 Agent 接口，用 Spring AI 的 Advisor 统一注入租户上下文、审计日志、敏感词过滤；RAG 的切分策略、检索重排、Prompt 模板则结合业务语料做定制。同时保留抽象边界（如自定义 ModelClient 接口），避免业务代码与框架 API 深度耦合，便于后续替换或升级。

权衡点：框架抽象会带来一定性能开销与调试复杂度，遇到框架不支持的供应商特性或极端性能要求时，可在局部下沉到原生 SDK；但不应因此全盘自研。

**常见追问**：成熟框架不满足需求时，你的扩展策略是什么？

---

## 7. 什么是垃圾回收： JavaScript代码运行时，需要分配内存空间来储存变量和值？

> 原题 ID：`q2448`

**高频程度**：★★★

**考察点**：考察 JS/V8 垃圾回收机制与常见算法。

**回答框架**：

1) 基于可达性分析，从根对象出发标记活动对象；2) 标记-清除产生碎片；3) 标记-整理移动活动对象解决碎片；4) 分代回收：新生代 Scavenge/Cheney 复制，老生代标记-清除/整理结合。

**参考回答**：

垃圾回收（GC）是自动管理内存的机制，通过识别并回收程序中不再使用的内存空间，防止内存泄漏。在 JavaScript 中，GC 主要基于可达性分析，常见算法有标记-清除、标记-整理、分代回收等。

垃圾回收（Garbage Collection）是一种自动内存管理机制，它负责回收程序中不再使用的内存。在 JavaScript 中，内存分配发生在变量、对象、函数等创建时，而垃圾回收器会定期找出那些不再被引用的对象并释放其内存。

JavaScript 引擎（如 V8）主要采用可达性分析：从根对象（如全局对象、当前调用栈中的变量）出发，遍历所有引用，能到达的对象标记为活动对象，其余视为垃圾。

常见算法：
1. 标记-清除（Mark-Sweep）：从根开始标记所有可达对象，然后清除未标记对象。缺点是产生内存碎片。
2. 标记-整理（Mark-Compact）：在标记后，将活动对象向一端移动，然后清理边界外的内存，解决碎片问题。
3. 分代回收（Generational GC）：基于弱分代假说，将对象分为新生代和老生代。新生代使用 Scavenge 算法（将内存分为两个半区，复制存活对象），老生代使用标记-清除/整理。V8 中新生代采用 Cheney 算法，老生代采用标记-清除和标记-整理结合。

代码示例：
```javascript
let obj = { name: 'test' }; // 分配内存
obj = null; // 解除引用，对象成为垃圾
// 垃圾回收器会在某个时刻回收该对象
```

在 Go 语言中，垃圾回收也是自动的，但采用并发三色标记清除算法，与 JavaScript 有相似的可达性分析思想，但实现细节不同。

**常见追问**：V8 为什么要区分新生代和老生代？

---

## 8. java内存泄漏原理？

> 原题 ID：`q2498`

**高频程度**：★★★★★

**考察点**：考察 Java 内存泄漏的本质与常见场景。

**回答框架**：

1) 本质：对象已不再使用但仍被 GC Roots 强引用可达，GC 无法回收；2) 常见场景：静态集合只增不删、单例/线程池/ThreadLocal 持有短生命周期对象、监听器未注销、非静态内部类隐式持有外部类、资源未关闭；3) 排查：heap dump + MAT/jmap/jstat，看 dominator tree 与引用链。

**参考回答**：

Java 内存泄漏本质是对象已不再被程序使用，但仍被 GC Roots 可达的引用链强引用，导致 GC 无法回收，最终内存持续增长甚至 OOM。

Java 有垃圾回收，但 GC 判断对象能否回收的标准是“可达性分析”：从 GC Roots（栈帧局部变量、静态变量、常量、JNI 引用、活跃线程等）出发，沿引用链能到达的对象就是存活对象。内存泄漏不是对象“消失不了”，而是对象“还被错误地认为有用”。

通俗类比：GC 像保洁员，只清理“没有任何人还能找到”的垃圾。如果一根绳子从根节点一直拴着一个早已不用的箱子，保洁员就认为它还有用，不会清走。

常见场景：
1. 静态集合：static List 缓存对象，只加不删，生命周期与类加载器一样长。
2. 长生命周期对象持有短生命周期对象：单例、线程池、监听器、ThreadLocal 等。
3. 未注销监听器/回调：事件源长期存活，监听器无法释放。
4. 非静态内部类/匿名内部类：隐式持有外部类实例，若被长生命周期对象引用，外部类也无法回收。
5. 资源未关闭：数据库连接、IO、网络连接未 close，底层 native 内存或对象无法释放。
6. ThreadLocal 使用后未 remove：线程池线程复用，value 随线程长期存活，key 是弱引用但 value 是强引用，容易泄漏。
7. 缓存无淘汰策略：自己实现的 HashMap 缓存没有容量上限和过期策略。

与内存溢出的区别：泄漏是“该回收的没回收”，溢出是“内存真的不够用”。泄漏长期积累通常导致 OOM，但 OOM 不一定由泄漏引起。

排查思路：用 jps 找进程，jmap/jcmd 导出堆转储，MAT 或 VisualVM 分析支配树、GC Roots 路径；也可用 JProfiler、Arthas 等在线诊断。

**常见追问**：ThreadLocal 为什么会在用线程池时泄漏？

---

## 9. 对象头： 理解Java对象头中的Mark Word如何存储锁状态（无锁、偏向锁、轻量级锁、重量级锁），以及锁升级的过程？

> 原题 ID：`q2512`

**高频程度**：★★★★★

**考察点**：考察对象头 Mark Word 的锁状态编码与锁升级过程。

**回答框架**：

1) 对象头=Mark Word + Klass Pointer，Mark Word 复用存储 hashCode/分代年龄/锁状态/偏向线程；2) 低 2~3 位编码：001 无锁、101 偏向锁、00 轻量级锁、10 重量级锁、11 GC 标记；3) 升级路径：无锁→偏向（首次 CAS 记录线程）→轻量级（撤销偏向、栈上 Lock Record + CAS 自旋）→重量级（自旋失败或竞争激烈，指向 ObjectMonitor 并挂起）；4) 本质是按竞争程度选择同步代价，且单向不可降级。

**参考回答**：

Java对象头的Mark Word用最低2~3位标记锁状态，并随锁竞争从无锁→偏向锁→轻量级锁→重量级锁单向升级，本质是用空间换时间、按竞争程度选择同步代价。

一、对象头与Mark Word
HotSpot中普通对象由对象头、实例数据、对齐填充组成。对象头包含Mark Word和Klass Pointer。32位JVM的Mark Word为32bit，64位为64bit。它复用同一块内存保存不同运行态信息：hashCode、GC分代年龄、锁状态、偏向线程ID、偏向时间戳等。

二、锁状态编码
以64位为例，Mark Word低3位含义：
- 001：无锁，同时存hashCode、分代年龄、是否偏向锁标志0；
- 101：偏向锁，存偏向线程ID、Epoch、分代年龄、偏向标志1；
- 00：轻量级锁，存指向线程栈中Lock Record的指针；
- 10：重量级锁，存指向ObjectMonitor的指针；
- 11：GC标记，用于GC。

三、为什么需要锁升级
锁的代价不同：偏向锁几乎零开销，轻量级锁用CAS自旋避免阻塞，重量级锁依赖OS互斥量会挂起线程。JVM假设大多数锁不存在竞争或竞争很短，因此先尝试低成本方案，竞争加剧再升级，避免一上来就陷入内核态。

四、升级过程
1. 无锁→偏向锁：线程首次进入同步块，通过CAS把Mark Word的偏向线程ID改为自己。成功则后续同一线程进入无需CAS。
2. 偏向锁→轻量级锁：另一线程尝试获取偏向锁时，到达安全点撤销偏向锁，升级为轻量级锁。
3. 轻量级锁：线程在栈帧中建Lock Record，用CAS把Mark Word指向该记录。失败则自旋重试。
4. 轻量级锁→重量级锁：自旋超过阈值或竞争线程多，膨胀为ObjectMonitor，未抢到锁的线程进入EntryList阻塞，由OS调度。

五、通俗类比
Mark Word像门牌：无锁是空房；偏向锁是“已租给A”，A进出自由；轻量级锁是A临时外出，B来试钥匙，试几次不行就等；重量级锁是排队叫号，没叫到的人去休息室睡觉，由管理员唤醒。

六、适用场景
偏向锁适合单线程反复进入同步块；轻量级锁适合竞争少、临界区短；重量级锁适合竞争激烈、临界区长。JDK 15后偏向锁默认禁用并逐步移除，因为维护成本高、现代应用竞争模式变化。

**常见追问**：JDK 15 之后为什么默认关闭偏向锁？

---

## 10. synchronized 与 ReentrantLock 如何比较和选型？

> 原题 ID：`q2514`

**高频程度**：★★★★

**考察点**：考察 ReentrantLock 与 synchronized 的实现与能力对比。

**回答框架**：

1) ReentrantLock 基于 AQS 的 state + CLH 队列，是显式锁；2) synchronized 是 JVM 关键字，靠 monitorenter/monitorexit 与 Mark Word，自动释放；3) ReentrantLock 支持可中断、可超时、可公平、多 Condition；4) 代价是必须 finally unlock，否则会一直占锁。

**参考回答**：

ReentrantLock 是 JUC 提供的显式可重入互斥锁，相比 synchronized 更灵活（可中断、可超时、可公平、可多条件），但必须手动释放，适合需要高级锁控制的场景。

一、概念定义
ReentrantLock 位于 java.util.concurrent.locks 包，是基于 AQS（AbstractQueuedSynchronizer）实现的显式锁。所谓“可重入”，指同一线程可以重复获取同一把锁，每获取一次 state 加 1，释放一次减 1，减到 0 才真正释放。

通俗类比：synchronized 像酒店房卡自动续住，你进房间（加锁）后系统自动记录，出门（代码块结束）自动退房；ReentrantLock 像手动门禁，你刷卡进门后必须自己记得刷卡出门，忘了就会一直占着房间，别人进不来。

二、与 synchronized 的核心对比
1. 实现层面：synchronized 是 JVM 内置关键字，由 monitorenter/monitorexit 字节码和对象头 Mark Word 实现，JVM 会做锁升级（偏向锁→轻量级锁→重量级锁）；ReentrantLock 是 JDK 层面的 API，基于 AQS 的 CAS + CLH 队列实现。
2. 释放方式：synchronized 自动释放（异常也会释放）；ReentrantLock 必须在 finally 中 unlock()，否则死锁。
3. 可中断：lockInterruptibly() 允许等待锁的线程被中断，synchronized 不行。
4. 超时：tryLock(long, TimeUnit) 可避免无限等待，synchronized 不行。
5. 公平性：ReentrantLock 可构造公平锁（new ReentrantLock(true)），按等待顺序获取；synchronized 是非公平的。
6. 条件变量：ReentrantLock 可创建多个 Condition，实现精准唤醒（如生产者消费者按队列空/满分别等待）；synchronized 只有一个 wait/notify 集合。
7. 性能：JDK6 后 synchronized 优化后两者性能接近，低竞争下 synchronized 更简单；高竞争或需要高级功能时 ReentrantLock 更合适。

三、适用场景
- 需要可中断、可超时获取锁：如防止死锁、响应取消。
- 需要公平锁：避免线程饥饿。
- 需要多个等待条件：如阻塞队列、复杂同步。
- 需要跨方法加解锁：锁的获取和释放不在同一代码块。
否则优先用 synchronized，代码更简洁、不易出错。

四、简单例子
ReentrantLock lock = new ReentrantLock();
lock.lock();
try { /* 临界区 */ } finally { lock.unlock(); }

公平锁：new ReentrantLock(true)；条件变量：Condition notEmpty = lock.newCondition();

**常见追问**：AQS 的 state 在 ReentrantLock 里是怎么实现可重入的？

---

## 11. AI 时代，我们还要“背八股”吗？——一个Java应届生的深思与破局？

> 原题 ID：`q2517`

**高频程度**：★★★

**考察点**：考察 AI 时代八股的价值与学习方式转变。

**回答框架**：

1) 知识本身贬值，但知识形成的判断力升值；2) 面试官真正考的是「为什么」背后的数据结构、内存、并发与工程权衡；3) 不背的风险：AI 会幻觉，缺乏判断力会被带偏；4) 方法：把八股当索引，每个点追问三层为什么，并绑定项目踩坑。

**参考回答**：

要背，但要从背答案转向背原理与场景，把八股当作AI无法替代的底层认知骨架，用AI做陪练和验证而非答案来源。

这道题本质在问：大模型能秒答'HashMap扩容机制''JVM内存模型'，那记忆型知识还有没有价值？答案是：知识本身贬值了，但'知识形成的判断力'升值了。

类比：AI像一本随时可查的字典，但你不能靠查字典来写文章。面试官考八股，考的不是你能否复述'ArrayList默认容量10'，而是你是否理解'为什么是10''扩容1.5倍而不是2倍''为什么线程不安全'——这些追问背后是数据结构、内存、并发、工程权衡的认知。

为什么还要背：
1）面试筛选成本：面试官无法在40分钟内验证你的工程能力，八股是低成本的信号，答不出基础题会被直接判定'没系统学过'。
2）AI幻觉风险：大模型会一本正经胡说，比如把CMS说成G1的替代、把volatile说成保证原子性。没有底层判断力，你无法识别AI的错误，反而被带偏。
3）追问深度：AI给的是平均答案，面试官要的是你的思考路径。'为什么'类问题AI答得泛，你能结合项目讲出踩坑才加分。

破局方法：
- 把八股当'索引'而非'终点'：每个知识点追问三层为什么，比如synchronized→锁升级→偏向锁为何被废弃（JDK15后偏向锁默认关闭，因维护成本高于收益）。
- 用AI做苏格拉底式陪练：让AI扮演面试官追问，或让它故意给出错误答案让你纠错，训练鉴别力。
- 建立知识网络：把JVM、并发、MySQL、Redis串成'一次请求的生命周期'，而不是孤立背诵。
- 项目反哺：用八股解释你项目里的选型，比如为什么用ConcurrentHashMap而不是Collections.synchronizedMap。

适用场景：校招/初级岗八股权重高，因为缺乏工程履历；高级岗更看系统设计与落地，但底层原理仍是地基。

**常见追问**：你会怎么用 AI 练面试而不是依赖它？

---

## 12. 年轻代和老年代分别使用哪些垃圾回收算法？它们的优势和劣势是什么？请提供相关JVM参数示例？

> 原题 ID：`q2527`

**高频程度**：★★★★

**考察点**：考察分代收集算法选择与相关 JVM 参数。

**回答框架**：

1) 年轻代用复制算法（Eden:Survivor=8:1:1，Minor GC 复制存活对象，年龄阈值晋升）；2) 老年代用标记-清除或标记-整理（Major/Full GC）；3) 关键参数：-Xmn/-XX:NewRatio、-XX:SurvivorRatio、-XX:MaxTenuringThreshold、-XX:PretenureSizeThreshold；4) 权衡：复制无碎片但浪费空间，标记整理无碎片但开销大。

**参考回答**：

年轻代用复制算法（Minor GC），老年代用标记-清除或标记-整理（Major/Full GC），核心权衡是吞吐、停顿与内存碎片。

JVM 堆通常按分代设计：年轻代（Young Gen）分为 Eden 和两个 Survivor（S0/S1），默认比例 8:1:1；老年代（Old Gen/Tenured）存放长期存活对象。

1) 年轻代：复制算法（Copying）
原理：对象优先在 Eden 分配，Eden 满触发 Minor GC，把 Eden 和当前 Survivor 中存活对象复制到另一个空 Survivor，然后清空 Eden 和原 Survivor；对象每熬过一次 GC 年龄加 1，达到阈值（默认 15，-XX:MaxTenuringThreshold）晋升老年代。大对象可直接进入老年代（-XX:PretenureSizeThreshold）。
优势：只扫描存活对象、复制到连续空间，无碎片，分配可用指针碰撞（bump-the-pointer），效率高；适合“朝生夕死”的对象。
劣势：需要一块空闲 Survivor 作为复制空间，浪费 10% 左右堆；存活对象多时复制成本高；Survivor 放不下会触发分配担保，提前晋升老年代。

2) 老年代：标记-清除（Mark-Sweep）或标记-整理（Mark-Compact）
原理：老年代对象存活率高，不适合复制。CMS 使用标记-清除：初始标记、并发标记、重新标记、并发清除；G1 整体是标记-整理，局部 Region 之间复制；Parallel Old 使用标记-整理。
优势：标记-清除不需要额外复制空间，适合大对象和长生命周期对象；标记-整理能消除碎片，适合长期运行。
劣势：标记-清除产生内存碎片，可能触发 Full GC；标记-整理需要移动对象，停顿较长；并发回收会占用 CPU 并产生浮动垃圾。

3) 参数示例：
- 年轻代：-Xmn256m 或 -XX:NewRatio=2（老年代/年轻代=2:1）、-XX:SurvivorRatio=8、-XX:MaxTenuringThreshold=15、-XX:+UseSerialGC / -XX:+UseParNewGC / -XX:+UseParallelGC。
- 老年代：-XX:+UseConcMarkSweepGC（CMS）、-XX:CMSInitiatingOccupancyFraction=70、-XX:+UseCMSCompactAtFullCollection、-XX:+UseParallelOldGC、-XX:+UseG1GC、-XX:MaxGCPauseMillis=200。
- 典型组合：-Xms4g -Xmx4g -Xmn1g -XX:SurvivorRatio=8 -XX:MaxTenuringThreshold=15 -XX:+UseG1GC -XX:MaxGCPauseMillis=200。

注意：题目虽标注“后端八股（Go）”，但内容实际是 JVM/Java GC；若面试官问 Go，应回答 Go 的三色标记+混合写屏障、无分代，并说明与 JVM 分代的区别。

**常见追问**：什么情况下对象会直接进入老年代？

---

## 13. 谁会去背IOC的七八种实现方式？谁会去记JVM调优的32个参数？

> 原题 ID：`q3182`

**高频程度**：★★★

**考察点**：考察对「背实现方式/参数」的反讽背后真正的考察点。

**回答框架**：

1) IOC 本质是控制反转与依赖注入，实现方式（构造器/setter/字段/接口注入）只是形态差异；2) JVM 真正要记的是几类核心参数：堆大小、新生代比例、GC 选择、元空间、OOM dump；3) 调优方法论：明确目标→监控定位→小步调整→压测验证；4) 面试考的是理解与取舍，不是背诵数量。

**参考回答**：

面试考察的不是背诵实现方式或参数数量，而是能否理解 IOC 的本质（控制反转/依赖注入）和 JVM 调优的底层原理与调优方法论，并能在真实场景中按需查阅和取舍。

这句话本身是面试官对『八股文式背诵』的反讽。IOC 的实现方式（构造器注入、setter 注入、字段注入、接口注入、工厂模式、服务定位器、模板方法、AOP 等）并不需要背，因为它们的本质都是同一个：把对象创建和依赖装配的控制权从业务代码反转给容器。你只要理解『谁控制谁、反转了什么、为什么需要反转』，就能在需要时推导出具体实现。例如 Spring 的构造器注入本质是容器在 new Bean 时按类型/名称解析依赖并递归创建，字段注入只是反射赋值，setter 注入是容器调用 setter。JVM 调优的 32 个参数同理，真正要记的是几类核心参数：堆大小（-Xms/-Xmx）、新生代比例（-Xmn/-XX:NewRatio）、GC 选择（-XX:+UseG1GC 等）、元空间（-XX:MaxMetaspaceSize）、GC 日志与 OOM dump（-XX:+HeapDumpOnOutOfMemoryError）。调优方法论是：先明确目标（吞吐/延迟/内存占用），再通过监控（jstat、GC 日志、Arthas、JFR）定位瓶颈，最后小步调整并压测验证，而不是背参数。适用场景上，IOC 适合需要解耦、可测试、可替换实现的业务系统；JVM 调优适合高并发、大内存、对延迟敏感的服务，普通 CRUD 应用默认参数往往就够。

**常见追问**：现场给你一个 CPU 飙高的服务，你的调优步骤是什么？

---

## 14. synchronized 和 ReentrantLock 的区别，如何选择？

> 原题 ID：`q3392`

**高频程度**：★★★★★

**考察点**：考察 synchronized 与 ReentrantLock 的本质区别与选型。

**回答框架**：

1) 实现层：前者是 JVM 关键字 + Mark Word，后者是 AQS 的 state + CLH 队列；2) 释放：前者自动释放，后者必须 finally unlock；3) 功能：后者可中断、可超时、可公平、多 Condition，前者只有非公平；4) 选型：简单同步用 synchronized，需要高级能力用 ReentrantLock。

**参考回答**：

synchronized 是 JVM 内置的隐式可重入锁，ReentrantLock 是 JDK 层基于 AQS 的显式可重入锁，后者功能更灵活但需手动释放，选择取决于是否需要高级特性。

一、本质区别
1. 实现层面：synchronized 是 Java 关键字，由 JVM 通过 monitorenter/monitorexit 字节码指令实现，锁信息存在对象头 Mark Word 中；ReentrantLock 是 java.util.concurrent.locks 包下的类，基于 AQS（AbstractQueuedSynchronizer）的 state + CLH 队列实现，纯 Java 代码。
2. 锁的获取与释放：synchronized 自动加锁解锁，异常时 JVM 保证释放；ReentrantLock 必须手动 lock()/unlock()，且 unlock 要放在 finally 中，否则可能死锁。
3. 可重入性：两者都支持可重入。synchronized 通过对象头中的锁计数；ReentrantLock 通过 AQS 的 state 累加。

二、功能差异
1. 公平性：synchronized 只有非公平锁；ReentrantLock 可通过构造参数 new ReentrantLock(true) 选择公平锁（按等待队列顺序获取）。
2. 可中断：ReentrantLock 提供 lockInterruptibly()，等待锁时可响应中断；synchronized 等待时不可中断。
3. 超时尝试：ReentrantLock 提供 tryLock() 和 tryLock(long, TimeUnit)，可避免无限等待；synchronized 没有。
4. 条件变量：ReentrantLock 可绑定多个 Condition，实现精确唤醒（如生产者消费者中分别唤醒生产者/消费者）；synchronized 只能配合一个 wait/notify，唤醒随机。
5. 锁状态查询：ReentrantLock 提供 isLocked()、getHoldCount()、getQueueLength() 等监控方法；synchronized 无法直接查询。

三、性能与优化
早期 synchronized 是重量级锁，性能差；JDK 6 后引入偏向锁、轻量级锁、自旋锁、锁消除、锁粗化等优化，两者性能已接近。低竞争下 synchronized 因 JVM 优化甚至更优；高竞争或需要高级功能时 ReentrantLock 更合适。

四、通俗类比
synchronized 像酒店房卡：进门自动锁，出门自动开，简单但只能按固定规则；ReentrantLock 像带密码和定时功能的智能锁：可以设置等待时间、被中断、公平排队、多条件唤醒，但出门必须记得手动锁门（unlock），否则别人进不去。

五、如何选择
1. 优先用 synchronized：代码简洁、不易出错、JVM 持续优化，满足绝大多数场景。
2. 需要以下任一高级特性时选 ReentrantLock：可中断等待、超时获取、公平锁、多个条件变量、锁状态监控。
3. 注意：ReentrantLock 必须 finally 释放；公平锁会降低吞吐量，非必要不用。

【同源补充】来自同源题「synchronized 和 ReentrantLock 的区别？」
关键字 vs API、自动释放、可中断/超时/公平、Condition、tryLock
1) synchronized 是 JVM 内置关键字，自动释放；ReentrantLock 是 API 层面，需手动 unlock（finally）；2) Lock 支持可中断、超时获取、公平锁、多条件 Condition；3) synchronized 在竞争激烈时性能已接近 Lock；4) Lock 可尝试非阻塞 tryLock。

**常见追问**：什么场景下你必须用 ReentrantLock 而不能用 synchronized？

---

## 15. ThreadLocal 内存泄露问题是怎么导致的？

> 原题 ID：`q3393`

**高频程度**：★★★★★

**考察点**：考察 ThreadLocalMap 的弱引用 key 与强引用 value 导致泄漏的机理。

**回答框架**：

1) Thread 持有 ThreadLocalMap，Entry 的 key 是 ThreadLocal 弱引用、value 是强引用；2) 外部强引用消失后 key 被 GC 置 null，但 value 仍被 Entry 强引用；3) 线程长期存活（线程池核心线程）时 value 无法回收；4) 解决：用完显式 remove，或使用完让线程结束。

**参考回答**：

ThreadLocal 本身不泄露，泄露的是 ThreadLocalMap 中 key 为 null 的 Entry 所引用的 value，因为线程长期存活导致 value 无法回收。

ThreadLocal 为每个线程维护一份独立变量副本，底层是 Thread 内部的 ThreadLocalMap，key 是 ThreadLocal 对象（弱引用），value 是业务值（强引用）。

原理：
1. 每个 Thread 对象里有一个 threadLocals 字段，类型为 ThreadLocal.ThreadLocalMap。
2. ThreadLocalMap 的 Entry 继承 WeakReference>，即 key 是弱引用，value 是强引用。
3. 当外部对 ThreadLocal 的强引用消失后，GC 会回收 key，Entry 的 key 变成 null，但 value 仍被 Entry 强引用。
4. 如果线程一直存活（如线程池中的核心线程），这个 Entry 和 value 就无法被回收，造成内存泄露。

通俗类比：ThreadLocalMap 像每个线程自己的储物柜，ThreadLocal 是钥匙。钥匙被弱引用，主人丢了钥匙后，柜子上的锁芯（key）会被 GC 清掉，但柜子里的东西（value）还在，线程不结束，柜子不清理，东西就一直占地方。

为什么用弱引用：如果 key 是强引用，ThreadLocal 对象即使外部不用了也无法回收，泄露更严重。弱引用至少让 key 可被回收，配合 get/set/remove 时的清理逻辑（expungeStaleEntry）能回收部分 value。

正确做法：使用完 ThreadLocal 后必须调用 remove()，尤其在线程池场景。remove 会删除 Entry 并断开 value 强引用。

【同源补充】来自同源题「ThreadLocal 的原理与内存泄漏问题？」
ThreadLocalMap、弱引用 key、value 泄漏、remove()、线程池
每个线程有 ThreadLocalMap，key 是 ThreadLocal 弱引用，value 是线程局部变量。若 ThreadLocal 被回收而线程未结束，value 仍强引用导致泄漏。解决：用完调 remove() 清理。线程池场景尤需注意。

**常见追问**：ThreadLocalMap 的 key 为什么设计成弱引用？

---

## 16. 项目中如何创建线程池，为什么不建议直接使用 Executors？

> 原题 ID：`q3394`

**高频程度**：★★★★★

**考察点**：考察线程池的手动创建方式与 Executors 快捷工厂的风险。

**回答框架**：

1) 用 ThreadPoolExecutor 明确 core/max、队列、拒绝策略、线程工厂；2) 参数按任务类型定：CPU 密集≈核数+1，IO 密集按 QPS×耗时估算并发；3) 队列用有界避免堆积；4) Executors 的风险：newFixedThreadPool/newSingleThreadExecutor 用无界队列可能 OOM，newCachedThreadPool/newScheduledThreadPool 线程数无上限可能耗尽资源。

**参考回答**：

线程池应通过 ThreadPoolExecutor 手动构造，明确核心/最大线程数、队列、拒绝策略和线程工厂；Executors 的快捷工厂方法会使用无界队列或无限线程，容易导致 OOM 或资源耗尽。

背景：项目里通常会有异步任务、批量 IO、定时任务等场景，需要统一管理线程资源。我们的做法是封装一个 ThreadPoolExecutorFactory，基于 ThreadPoolExecutor 手动创建，并交给 Spring 管理生命周期。

核心参数决策：
1) corePoolSize / maximumPoolSize：按任务类型区分。CPU 密集型任务设为 CPU 核数 + 1；IO 密集型任务按 QPS、单任务平均耗时和可接受延迟估算，例如 QPS=200、平均耗时 50ms，则并发约 10，再留 2~3 倍余量。
2) workQueue：使用有界队列，如 ArrayBlockingQueue(200) 或 LinkedBlockingQueue(200)，避免任务无限堆积。
3) threadFactory：自定义命名，如 order-task-%d，并设置 daemon=false，便于日志排查和优雅停机。
4) rejectedExecutionHandler：核心业务用 CallerRunsPolicy 做背压，非核心任务用 AbortPolicy 并记录监控，避免拖垮主流程。
5) allowCoreThreadTimeOut(true) 或合理设置 keepAliveTime，回收空闲线程。

为什么不用 Executors：
- Executors.newFixedThreadPool 和 newSingleThreadExecutor 使用 LinkedBlockingQueue 无界队列，最大线程数等于核心线程数，任务堆积时不会扩容，最终 OOM。
- Executors.newCachedThreadPool 使用 SynchronousQueue，最大线程数为 Integer.MAX_VALUE，任务突增时会创建大量线程，导致 CPU 上下文切换和 OOM。
- Executors.newScheduledThreadPool 的 maximumPoolSize 也是 Integer.MAX_VALUE，同样有风险。
- 这些工厂方法隐藏了关键参数，无法按业务设置队列长度、拒绝策略和线程命名，不利于监控和故障定位。

实际例子：我们曾用 newFixedThreadPool 处理订单导出，流量高峰时队列堆积几十万任务，内存飙升，后来改为 ThreadPoolExecutor，核心 8、最大 16、队列 500、CallerRunsPolicy，并加监控，问题解决。

复盘：线程池不是越简单越好，必须结合任务特性、下游容量和失败策略来设计；同时要暴露活跃线程数、队列长度、拒绝次数等指标，配合动态调参。

**常见追问**：拒绝策略你会怎么选？CallerRunsPolicy 有什么副作用？

---

## 17. 策略模式的应用场景...顺带问了spring三大特性？

> 原题 ID：`q3546`

**高频程度**：★★★★

**考察点**：考察策略模式的应用场景与 Spring 三大特性。

**回答框架**：

1) 策略模式三要素：抽象策略接口、具体策略实现、上下文类；2) 价值：消除 if/else 膨胀、符合开闭原则、算法可单测可复用、运行时可切换；3) 场景：支付渠道、促销计算、限流算法、解析器选择、多租户差异；4) Spring 三大特性：IoC/DI、AOP、Bean 生命周期与作用域；5) 结合点：策略实现交给容器管理，用 Map<String, Strategy> 注入即可无 if/else 路由。

**参考回答**：

策略模式是把「可互换的算法族」各自封装成独立类、运行时按需注入替换，从而消除大量 if/else；Spring 三大特性（IoC/DI、AOP、Bean 生命周期与作用域管理）本质是「把对象的创建、装配、横切逻辑的控制权交给容器」，两者天然契合——策略实现类交给 Spring 管理，用 Map 注入即可实现无 if/else 的策略路由。

一、策略模式（Strategy Pattern）
1. 定义：定义一系列算法，把它们一个个封装起来，并且使它们可以相互替换，让算法的变化独立于使用它的客户端。
2. 通俗类比：去机场可以打车、坐地铁、坐大巴，目的地一样（同一个接口），出行方式（策略）可随时换。客户端只管说「我要去机场」，不关心怎么去。
3. 三要素：抽象策略接口（Strategy）、具体策略实现（ConcreteStrategy）、上下文/环境类（Context，持有策略引用并调用）。
4. 为什么用：
   - 消除 if/else 或 switch 分支膨胀，符合开闭原则（新增策略不改老代码）；
   - 算法可复用、可单测、可组合；
   - 运行时动态切换（如按用户等级、渠道、支付方式选不同费率/风控规则）。
5. 典型应用场景：
   - 支付渠道选择（微信/支付宝/银联）；
   - 促销/优惠券计算（满减、打折、N 元 M 件）；
   - 多种风控/限流算法（令牌桶、漏桶、滑动窗口）；
   - 文件/日志解析器（按格式选 parser）；
   - 排序/压缩算法切换；
   - 不同数据源或租户的差异化业务规则。
6. 与 Spring 结合的标准写法：
   - 定义接口 PayStrategy { String channel(); void pay(...); }
   - 每个实现类加 @Component，channel() 返回唯一标识；
   - 用构造器注入 List 或 Map（Spring 会自动把 beanName 作为 key 注入 Map）；
   - 初始化时转成 Map，调用时 map.get(channel).pay()，彻底去掉 if/else。
   注意：若用自定义 channel() 而非 beanName，需在 @PostConstruct 里手动构建映射，避免 key 冲突。
7. 与工厂模式的区别：工厂关注「创建哪个对象」，策略关注「用哪种行为」；实际常组合使用（工厂产出策略）。

二、Spring 三大特性（通常指 IoC/DI、AOP、以及 Bean 管理/生命周期，也有说法把「轻量级、非侵入、一站式」列为特性，面试中按主流理解答）
1. IoC（控制反转）与 DI（依赖注入）：
   - 传统方式：对象自己 new 依赖，控制权在自己手里；
   - IoC：把对象的创建与依赖装配交给 Spring 容器，控制权反转；
   - DI 是 IoC 的实现手段，方式有构造器注入（推荐，可保证不可变与必填）、setter 注入、字段注入（@Autowired，不推荐，难测试且掩盖依赖）；
   - 好处：解耦、易替换实现（正好支撑策略模式）、便于测试（可注入 mock）。
2. AOP（面向切面编程）：
   - 把日志、事务、权限、缓存、监控等横切关注点从业务代码中抽离；
   - 核心概念：切面 Aspect、连接点 JoinPoint、切点 Pointcut、通知 Advice（Before/After/Around 等）、织入 Weaving；
   - 实现：Spring AOP 基于运行时动态代理（JDK 接口代理 / CGLIB 子类代理），AspectJ 支持编译期/加载期织入；
   - 典型：@Transactional、@Cacheable、自定义注解 + 环绕通知做接口耗时统计。
3. Bean 管理（生命周期与作用域）：
   - 生命周期：实例化 → 属性填充 → Aware 回调 → BeanPostProcessor 前置 → @PostConstruct/InitializingBean → 后置处理（AOP 代理常在此生成）→ 使用 → @PreDestroy/DisposableBean 销毁；
   - 作用域：singleton（默认）、prototype、request、session、application、websocket；
   - 与策略模式的关系：策略实现类通常声明为 singleton，无状态、线程安全；若策略持有可变状态则需 prototype 或改为无状态设计。

三、两者结合的价值：Spring 的 DI 让策略的「注册与查找」自动化，AOP 可给所有策略统一加日志/监控/事务，Bean 生命周期保证策略在容器启动时完成注册，形成「可插拔、可观测、可扩展」的架构。

**常见追问**：用 Map 注入策略时，key 重复或策略缺失你怎么处理？

---

## 18. JVM了解吗，有什么组成？

> 原题 ID：`q3579`

**高频程度**：★★★★

**考察点**：考察 JVM 的整体组成与运行时数据区划分。

**回答框架**：

1) 类加载子系统：加载-验证-准备-解析-初始化，双亲委派；2) 运行时数据区：线程私有（程序计数器、虚拟机栈、本地方法栈）与线程共享（堆、方法区/元空间），外加直接内存；3) 执行引擎：解释器、JIT（C1/C2）、GC；4) 本地接口与本地方法库：JNI 调用 C/C++。

**参考回答**：

JVM 是运行 Java 字节码的虚拟计算机，主要由类加载子系统、运行时数据区、执行引擎和本地接口/本地方法库四部分组成。

JVM（Java Virtual Machine）本质是一个抽象计算机，屏蔽操作系统差异，让 Java 字节码“一次编译，到处运行”。

1) 类加载子系统：负责把 .class 文件加载到内存。流程为加载、验证、准备、解析、初始化；类加载器采用双亲委派模型（Bootstrap → Extension/Platform → Application → 自定义），保证核心类不被篡改。

2) 运行时数据区：
- 线程私有：程序计数器（当前字节码行号）、虚拟机栈（栈帧：局部变量表、操作数栈、动态链接、返回地址）、本地方法栈。
- 线程共享：堆（对象实例，分新生代 Eden/Survivor 和老年代）、方法区（JDK8 后由元空间 Metaspace 实现，存类元信息、常量、静态变量）。
- 直接内存：NIO 的 DirectByteBuffer 使用，不受堆大小限制但受物理内存限制。

3) 执行引擎：解释器逐条解释字节码；JIT 即时编译器（C1/C2）把热点代码编译为机器码；还有垃圾回收器负责自动内存管理。

4) 本地接口与本地方法库：JNI 调用 C/C++ 等本地方法，如 System.currentTimeMillis()、Object.hashCode()。

通俗类比：JVM 像一家餐厅。类加载器是采购员，把食材（class 文件）按规则买进来；运行时数据区是厨房和仓库（堆放食材、栈放当前做菜步骤）；执行引擎是厨师，边看菜谱（解释器）边把常做的菜提前练熟（JIT）；本地接口是外部供应商，需要特殊调料时打电话叫货。

**常见追问**：直接内存算不算 JVM 运行时数据区？为什么容易 OOM？

---

## 19. JDK 7 与 JDK 8 的 PermGen/Metaspace 和常见 GC 机制有哪些差异？

> 原题 ID：`q3580`

**高频程度**：★★★★

**考察点**：考察 JDK7 与 JDK8 在永久代/元空间与默认回收器上的差异及回收过程。

**回答框架**：

1) JDK7：永久代 PermGen 存类元数据，受 -XX:MaxPermSize 限制，易 OOM: PermGen space；2) JDK8：移除永久代改为本地内存的 Metaspace，由 -XX:MaxMetaspaceSize 控制；3) 字符串常量池 JDK7 已移到堆；4) 回收过程：新生代复制（Minor GC），老年代标记-清除/整理（Major/Full GC），G1 在 JDK9 成为默认。

**参考回答**：

JDK7 默认 Parallel Scavenge + Parallel Old（分代、吞吐优先），JDK8 默认改为 Parallel 相同但引入 Metaspace 取代 PermGen，且 G1 成为可选/后续默认方向；回收过程仍是新生代复制、老年代标记整理/标记清除。

先澄清：题目写的是 Go 分类，但问的是 JDK，这里按 JVM 回答。

1) JDK7 与 JDK8 的核心区别
- 永久代 PermGen -> 元空间 Metaspace：JDK7 中类元数据、字符串常量池（JDK7 已移到堆）、静态变量等放在永久代，受 -XX:MaxPermSize 限制，容易 OOM: PermGen space；JDK8 移除永久代，类元数据放到本地内存的 Metaspace，由 -XX:MaxMetaspaceSize 控制，默认不限，只受物理内存限制。
- 默认垃圾回收器：JDK7 默认新生代 Parallel Scavenge，老年代 Parallel Old（Server 模式）；JDK8 默认仍是 Parallel Scavenge + Parallel Old，但 G1 在 JDK7 已实验性引入，JDK8 逐步成熟，JDK9 后成为默认。
- 字符串常量池：JDK7 已从永久代移到堆；JDK8 延续。
- 其他：JDK8 移除 PermGen 相关参数，新增 Metaspace 参数；CMS 在 JDK8 仍可用但已标记废弃趋势。

2) 具体回收过程（以分代收集为例）
- 对象优先在 Eden 分配。Eden 满触发 Minor GC：存活对象复制到 Survivor（From/To），年龄 +1，达到阈值（默认 15，-XX:MaxTenuringThreshold）晋升老年代；大对象直接进老年代（-XX:PretenureSizeThreshold）。
- Survivor 中相同年龄对象总和超过一半，则大于等于该年龄的直接晋升（动态年龄判定）。
- 老年代满触发 Full GC/Major GC：Parallel Old 用标记-整理，CMS 用标记-清除（并发标记、重新标记、并发清除），会产生碎片。
- 空间分配担保：Minor GC 前检查老年代最大连续空间是否大于新生代所有对象总和或历次晋升平均大小，不满足则可能直接 Full GC。

3) 代码示例（观察 GC）
```java
public class GCDemo {
  public static void main(String[] args) {
    for (int i = 0; i < 100000; i++) {
      byte[] b = new byte[1024 * 100]; // 100KB
    }
  }
}
```
运行：`java -Xms20m -Xmx20m -Xmn10m -XX:+PrintGCDetails -XX:SurvivorRatio=8 GCDemo`，JDK7 会看到 ParOldGen/PermGen，JDK8 会看到 ParOldGen/Metaspace。

4) 与 Go 的对比（若面试官追问 Go）
Go 用并发三色标记 + 混合写屏障，无分代，STW 极短；JVM 分代收集，STW 相对更长。

**常见追问**：元空间默认不限制大小，会有什么风险？

---

## 20. Java 中常见的两种同步锁实现是什么？

> 原题 ID：`q3608`

**高频程度**：★★★★

**考察点**：考察 Java 两种同步锁实现（synchronized 与 Lock）的机制差异。

**回答框架**：

1) synchronized：JVM 关键字，基于对象监视器 monitor，monitorenter/monitorexit，异常自动释放，JDK6 后有偏向/轻量级锁等优化；2) Lock：JUC 接口，典型实现 ReentrantLock 基于 AQS，需显式 lock/unlock 并放 finally；3) Lock 支持公平锁、可中断 lockInterruptibly、超时 tryLock、多 Condition；4) 简单同步优先 synchronized。

**参考回答**：

Java 中常见的两种同步锁实现是 synchronized 关键字和 java.util.concurrent.locks.Lock 接口（典型实现 ReentrantLock）。

两者都能实现互斥同步，但机制和用法不同。

1) synchronized：JVM 内置关键字，基于对象监视器（monitor）实现。修饰实例方法锁当前对象，修饰静态方法锁 Class 对象，修饰代码块锁指定对象。进入时 monitorenter，退出时 monitorexit，异常也会自动释放。JDK 6 后引入偏向锁、轻量级锁、自旋、锁消除、锁粗化等优化，性能大幅提升。

2) Lock：JUC 包提供的接口，典型实现 ReentrantLock，基于 AQS（AbstractQueuedSynchronizer）实现。需要显式 lock()/unlock()，通常配合 try-finally 保证释放。相比 synchronized 更灵活：支持公平/非公平锁、可中断获取 lockInterruptibly()、超时获取 tryLock(timeout)、多个 Condition 条件队列。

通俗类比：synchronized 像自动门，进出自动开关，简单省心；Lock 像手动门，需要自己开和关，但能控制开关时机、排队规则和等待条件。

适用场景：简单同步优先 synchronized；需要超时、可中断、公平锁、多条件等待或更细粒度控制时用 ReentrantLock。

**常见追问**：tryLock 超时失败后你一般怎么处理？

---

## 21. Java 后端面试通常如何考察 JVM、并发与集合等基础能力？

> 原题 ID：`q3622`

**高频程度**：★★★

**考察点**：考察秋招 Java 后端对底层知识的考察范围与原因。

**回答框架**：

1) 原因：候选人供给大需拉开区分度、线上问题排查依赖原理、底层知识有明确深度梯度；2) 高频范围：JVM（内存区、GC、类加载、OOM 定位）、并发（JMM、volatile/synchronized、AQS、CAS、线程池、ThreadLocal）、集合（HashMap 扩容与红黑树、ConcurrentHashMap 演进）、语言特性（String 不可变、泛型擦除、反射、动态代理）。

**参考回答**：

秋招Java后端面试中底层知识（JVM、并发、集合、类加载、GC等）被高频问到，尤其大厂，因为它是区分‘会用API’和‘懂原理’的关键筛子。

结论：非常经常，且是核心考察项。原因有三：
1) 供给端：Java候选人极多，CRUD层面人人都会，面试官必须用底层知识拉开区分度；
2) 需求端：线上问题（OOM、CPU飙高、死锁、GC停顿、类冲突）排查依赖底层原理，不是背API能解决的；
3) 可验证性：底层知识有明确对错和深度梯度，适合做技术评级。

常见考察范围与典型问法：
- JVM：内存区域划分、对象创建过程、GC算法与收集器（CMS/G1/ZGC）、GC日志分析、OOM定位；
- 并发：JMM、volatile/synchronized原理、AQS、CAS、线程池参数与拒绝策略、ThreadLocal内存泄漏；
- 集合：HashMap扩容与红黑树、ConcurrentHashMap分段/CAS+synchronized演进；
- 类加载：双亲委派、打破双亲委派（SPI、Tomcat）、热部署；
- 语言特性：String不可变、泛型擦除、反射、动态代理。

通俗类比：底层知识像‘汽车原理’。会开车（写业务）能上路，但面试官想知道车为什么能跑、爆胎了你会不会修。大厂要的是能修车的人，不只是司机。

适用场景：校招/秋招、大厂/中厂后端、基础架构岗几乎必问；小公司或业务外包岗可能更偏框架使用。回答策略：先给结论，再讲原理，最后落到‘线上问题怎么排查’，形成闭环。

**常见追问**：你有没有通过底层原理定位过线上问题？具体讲讲。

---

## 22. 为什么从 Java 后端转 AI Agent 应用开发？

> 原题 ID：`q3954`

**高频程度**：★★★

**考察点**：考察 Java 后端转 AI Agent 的优势与需补齐的能力。

**回答框架**：

1) 可迁移的工程能力：Agent 应用本质是分布式系统，涉及 API 调用、会话状态、鉴权限流、异步编排、可观测；2) 需补齐：LLM 的概率性思维、Prompt/上下文工程、Agent 范式（ReAct、Plan-and-Execute、Function Calling）、评估体系；3) 类比：传统后端按图纸施工，Agent 开发像带一个不确定的实习生，要设计约束与反馈。

**参考回答**：

Java 后端转 AI Agent 开发的核心优势在于工程化能力可迁移，但需补齐 LLM 概率性思维、Prompt/上下文工程与 Agent 编排范式。

这道题本质是考察你对两个领域差异与迁移性的理解。

1) 为什么能转：Java 后端积累的工程能力在 Agent 应用层高度复用。Agent 应用本质是一个分布式系统：需要调用 LLM API（HTTP/RPC）、管理会话状态（Redis/DB）、做鉴权限流（网关）、异步编排（消息队列/线程池）、可观测性（日志/链路追踪/Trace）。这些正是 Java 后端的强项。Spring Boot + WebClient/OkHttp 调模型、用状态机或工作流引擎编排工具调用，都是熟悉的套路。

2) 为什么需要补课：LLM 是概率性组件，不是确定性函数。后端习惯的"输入确定→输出确定"被打破，同一 Prompt 可能返回不同结果，还会幻觉、超时、限流。所以要学：Prompt 工程（few-shot、CoT、结构化输出）、上下文窗口管理（截断/摘要/RAG 检索）、Agent 范式（ReAct、Plan-and-Execute、Function Calling/Tool Use）、评估（Eval、回归测试集）。

3) 通俗类比：传统后端像"按图纸施工的工程队"，每一步确定；Agent 开发像"带一个聪明但会走神的实习生"，你要设计好任务拆解、工具、检查点（guardrail）和兜底，而不是写死流程。

4) 适用场景：适合做企业级 Agent 平台、RAG 知识库、工作流编排、多 Agent 协作等偏工程落地的方向；纯算法训练/微调则需补 ML 基础。

**常见追问**：概率性组件怎么保证线上稳定性？

---

## 23. 你认为 Agent 应用开发和普通 Java 后端开发最大的区别是什么？

> 原题 ID：`q3955`

**高频程度**：★★★★

**考察点**：考察 Agent 应用与普通 Java 后端的本质差异。

**回答框架**：

1) 控制流：确定性代码 vs LLM 驱动的多步闭环，同一输入可能走不同路径；2) 核心资产：业务代码与数据库 vs Prompt/上下文、工具定义、记忆与检索；3) 正确性：单元测试与事务 vs 评测集、轨迹评估、LLM-as-judge 与概率性兜底；4) 运行时关注点：QPS/连接池/GC vs token 成本与延迟、上下文窗口、循环步数上限；5) 开发范式：写死逻辑 vs 设计约束与反馈。

**参考回答**：

普通 Java 后端是确定性的请求-响应流水线，Agent 应用是以 LLM 为决策核心、在不确定环境中自主规划并调用工具的多步闭环系统，开发范式从'写死逻辑'变成'设计约束与反馈'。

可以从五个维度对比。

1) 控制流：Java 后端是确定性代码，if/else、状态机、事务边界都由人写死，输入相同输出基本一致；Agent 是 LLM 驱动的循环（ReAct/Plan-Execute），下一步做什么由模型根据上下文动态决定，同一输入可能走不同路径。类比：Java 后端像按图纸施工的流水线，Agent 像给一个实习生目标+工具箱，让他自己想办法。

2) 核心资产：Java 后端核心是业务逻辑代码和数据库；Agent 的核心是 Prompt/上下文工程、工具定义（Function Calling schema）、记忆与检索（RAG）、以及模型选型。代码更多是'脚手架'，真正决定效果的是上下文里放了什么。

3) 正确性与测试：Java 靠单元测试、幂等、事务保证确定性正确；Agent 没有唯一正确答案，只能靠评测集（eval）、轨迹评估、LLM-as-judge、人工抽检来衡量成功率，且要接受概率性失败，做重试、降级、兜底。

4) 运行时特征：Java 关注 QPS、连接池、GC、事务；Agent 关注 token 成本与延迟、上下文窗口溢出、多轮循环的步数上限、工具调用失败与幻觉、并发下的会话隔离。延迟从毫秒级变成秒到分钟级，成本模型从 CPU 变成按 token 计费。

5) 工程重点：Java 后端重点是分层、解耦、高可用；Agent 重点是'约束与反馈'——用结构化输出、工具白名单、护栏（guardrail）、人工确认（human-in-the-loop）把不确定的模型框在安全边界内，并设计可观测性（trace 每一步 thought/action/observation）。

一句话：Java 后端是'消除不确定性'，Agent 开发是'管理不确定性'。

**常见追问**：Agent 的效果怎么像后端一样做「回归测试」？

---

## 24. Spring AI 在项目中主要用了哪些能力？哪些地方是你自己封装的？

> 原题 ID：`q3990`

**高频程度**：★★★★

**考察点**：考察 Spring AI 的工程落地能力与自研边界。

**回答框架**：

1) 原生能力：ChatClient 多模型对话与流式、Advisor 横切拦截、VectorStore 向量检索、Function Calling/ToolCallback、结构化输出、PromptTemplate；2) 自封装：多模型路由（按租户/成本/SLA 选模型并支持降级灰度）、Prompt 版本化与 A/B、RAG 检索后处理与重排、工具注册与权限、可观测（token/延迟/链路）。

**参考回答**：

Spring AI 主要用了 ChatClient 多模型对话、Advisor 拦截、RAG 向量检索、Function Calling 和结构化输出；自封装集中在多模型路由、Prompt 模板治理、RAG 检索后处理、工具注册与可观测性。

背景：项目是一个企业知识库问答 + 业务操作 Agent，需要接入 OpenAI、通义千问、本地 Ollama 等多模型，并支持流式输出、工具调用和权限隔离。

Spring AI 原生能力：
1) ChatClient/ChatModel：统一同步、流式对话接口，屏蔽不同厂商 API 差异。
2) Advisor：实现日志、限流、敏感词过滤、RAG 检索增强等横切逻辑，类似 AOP。
3) VectorStore：对接 PGVector/Redis/Milvus，做文档 embedding 与相似度检索。
4) Function Calling/ToolCallback：让模型调用内部业务接口，如查订单、发工单。
5) Structured Output：通过 BeanOutputConverter 把模型输出映射为 Java 对象。
6) PromptTemplate：管理系统提示词与变量填充。

自封装部分：
1) 多模型路由：根据租户、成本、SLA 选择模型，封装 ModelRouter，支持降级和灰度。
2) Prompt 治理：Prompt 版本化、A/B 测试、变量校验，避免硬编码。
3) RAG 增强：检索后做重排序、去重、上下文压缩、引用溯源，解决召回不准和 token 超限。
4) 工具注册中心：统一注册、鉴权、审计 ToolCallback，防止模型越权调用。
5) 可观测性：记录 token 消耗、首 token 延迟、工具调用链，接入 Micrometer + OpenTelemetry。
6) 会话记忆：基于 ChatMemory 封装多轮会话隔离与过期清理。

决策与复盘：初期直接用 ChatClient，后期发现多模型切换和 Prompt 散落导致维护困难，于是抽象路由层和 Prompt 中心；RAG 最初只做向量检索，效果差，加入 BM25 混合检索和 rerank 后准确率明显提升。

**常见追问**：多模型路由的降级判断依据是什么？

---

## 25. 常见的垃圾回收算法有哪些？

> 原题 ID：`q4016`

**高频程度**：★★★★★

**考察点**：考察常见 GC 算法的原理与碎片问题。

**回答框架**：

1) 标记-清除：标记存活后清除未标记，简单但有碎片；2) 标记-整理：清除后把存活对象向一端移动，无碎片但开销大；3) 复制算法：内存分两块，存活对象复制到另一块，无碎片、分配快但利用率低，适合新生代；4) 分代收集：新生代复制、老年代标记-整理/清除。

**参考回答**：

1) 标记-清除：标记存活对象后清除未标记对象，会产生内存碎片；2) 标记-整理：清除后把存活对象向一端移动，无碎片但开销大；3) 复制算法：把内存分两块，存活对象复制到另一块，适合新生代；4) 分代收集：新生代用复制（Minor GC），老年代用标记-整理/清除（Major/Full GC）。

**常见追问**：为什么新生代适合复制算法？

---

## 26. G1、CMS、ZGC 三种垃圾回收器有什么区别？

> 原题 ID：`q4017`

**高频程度**：★★★★

**考察点**：考察 CMS/G1/ZGC 的目标、算法与停顿时长差异。

**回答框架**：

1) CMS：以最短停顿为目标，并发标记清除，有碎片、对 CPU 敏感、有 Concurrent Mode Failure；2) G1：堆分 Region、可预测停顿模型（MaxGCPauseMillis）、SATB 并发标记、JDK9 后默认，兼顾吞吐与延迟；3) ZGC：染色指针+读屏障，几乎全并发、停顿 < 10ms（亚毫秒级），支持超大堆，适合低延迟大内存。

**参考回答**：

CMS 以获取最短停顿为目标，并发标记清除，但会产生碎片、对 CPU 敏感；G1 把堆划分为 Region，可预测停顿模型，兼顾吞吐与延迟，JDK9 后默认；ZGC 是低延迟回收器（停顿 < 10ms），基于染色指针和读屏障，支持超大堆，几乎全并发。

**常见追问**：ZGC 的停顿为什么与堆大小基本无关？

---

## 27. 对象从创建到可以被 GC 的过程是怎样的？

> 原题 ID：`q4018`

**高频程度**：★★★★

**考察点**：考察对象创建流程与「可被 GC 回收」的判定过程。

**回答框架**：

1) 类加载检查；2) 分配内存（指针碰撞或空闲列表，TLAB 优先）；3) 初始化零值；4) 设置对象头（Mark Word + 类型指针）；5) 执行构造函数；6) 存活判定用可达性分析（GC Roots 引用链），不可达对象经过 finalize 最多一次后回收。

**参考回答**：

1) 类加载检查；2) 分配内存（指针碰撞或空闲列表）；3) 初始化零值；4) 设置对象头（Mark Word、类型指针）；5) 执行  构造函数。对象存活判定用可达性分析（GC Roots 引用链），经历回收标记、finalize 最多一次后回收。

**常见追问**：finalize 为什么被废弃？现在用什么替代？

---

## 28. 什么是双亲委派模型？为什么需要它？

> 原题 ID：`q4019`

**高频程度**：★★★★★

**考察点**：考察双亲委派模型的定义、层级与作用。

**回答框架**：

1) 收到加载请求先委派父加载器，父加载器无法完成才自己加载；2) 层级自顶向下：Bootstrap→Extension/Platform→Application→自定义；3) 好处：避免类重复加载、防止核心类库被篡改（沙箱安全）；4) 打破场景：SPI（线程上下文类加载器）、Tomcat 的 WebApp 隔离、OSGi。

**参考回答**：

类加载器收到加载请求时，先委派父加载器加载，父加载器无法完成才自己加载。自顶向下：Bootstrap→Extension→Application。好处：避免类重复加载、防止核心 API 被篡改（如自定义 java.lang.String 不会被加载）。

**常见追问**：Tomcat 为什么要打破双亲委派？

---

## 29. Java 中四种引用类型及其区别？ThreadLocal 的弱引用边界是什么？

> 原题 ID：`q4020`

**高频程度**：★★★★

**考察点**：考察四种引用类型的回收时机与典型用途。

**回答框架**：

1) 强引用：普通 new，只要有引用链就不回收；2) 软引用：内存不足时回收，适合缓存；3) 弱引用：下次 GC 必回收，如 ThreadLocal 的 key；4) 虚引用：最弱，仅用于跟踪对象被回收（配合 ReferenceQueue），常用于堆外内存清理。

**参考回答**：

Java 的强引用会阻止对象被回收；软引用通常在内存紧张时才会被清理；弱引用在下一次 GC 后即可失效；虚引用不能通过引用取得对象，常配合 `ReferenceQueue` 跟踪回收并协调堆外资源。选择时要考虑缓存命中、可预测性和资源释放，不能把软/弱引用当通用缓存框架。

`ThreadLocalMap` 中弱引用的是 `ThreadLocal` key，value 仍被线程持有的 map 强引用。在线程池中，key 被回收后若不调用 `remove()`，value 可能存活到后续 map 清理或线程结束，因此使用完成应显式 `remove()`，尤其是大对象或敏感上下文。

**常见追问**：为什么在线程池任务中仅依赖 ThreadLocal key 被 GC 不足以防止 value 泄漏？

---

## 30. Java 中常见 OutOfMemoryError 类型有哪些？如何排查？

> 原题 ID：`q4021`

**高频程度**：★★★★★

**考察点**：考察 OOM 的类型划分与排查手段。

**回答框架**：

1) 类型：堆溢出（对象过多/泄漏）、元空间溢出（类过多、动态代理）、栈溢出（死递归、栈过小）、直接内存溢出（NIO）、GC overhead limit exceeded；2) 排查：-XX:+HeapDumpOnOutOfMemoryError 导出 dump 后用 MAT 看 dominator tree，jstat 看 GC 趋势，jmap/jstack 看内存与线程。

**参考回答**：

常见 `OutOfMemoryError` 包括 Java heap space（堆对象过多或泄漏）、Metaspace（类加载/动态代理过多）、Direct buffer memory（堆外缓冲）、unable to create native thread（线程/系统资源不足）和 GC overhead limit exceeded。`StackOverflowError` 通常来自深递归或栈空间耗尽，是不同于 OOM 的错误类型。

排障先保存证据：启用 heap dump、记录 GC 日志和容器/OS 内存限制；再用 MAT 等工具看 dominator tree、结合线程栈、类加载与直接内存指标定位增长源。修复应回到对象生命周期、缓存上限、并发度和部署内存预算，而不是只增大堆。

**常见追问**：为什么容器内存限制可能导致 JVM 尚未达到 Xmx 就被系统杀死？

---

## 31. synchronized 的实现与锁优化如何随 JDK 版本变化？

> 原题 ID：`q4022`

**高频程度**：★★★★★

**考察点**：考察 synchronized 的底层实现与锁升级。

**回答框架**：

1) 底层是对象头 Mark Word 中的锁状态与 monitor；2) 锁升级：无锁→偏向锁（CAS 记录线程）→轻量级锁（栈上 Lock Record + CAS 自旋）→重量级锁（ObjectMonitor，线程挂起）；3) 编译层面是 monitorenter/monitorexit；4) 还有锁消除、锁粗化等 JIT 优化。

**参考回答**：

`synchronized` 在字节码层对应 `monitorenter`/`monitorexit`，实例锁依赖对象关联的 monitor，JVM 会根据竞争情况采用不同的轻量或重量级实现。JIT 还可能进行锁消除、锁粗化等优化。

不要把“无锁→偏向→轻量→重量”的固定升级链当作所有 JDK 的长期事实：偏向锁已在较新的 JDK 中被移除，具体对象头和优化策略随版本、VM 和竞争模式变化。工程上应先保证临界区正确、避免长时间持锁，再用 JFR/线程栈/压测定位实际竞争。

**常见追问**：为什么讨论 synchronized 时应同时说明 JDK 版本和竞争工作负载？

---

## 32. volatile 的内存语义是什么？

> 原题 ID：`q4023`

**高频程度**：★★★★★

**考察点**：考察 volatile 的内存语义与底层实现。

**回答框架**：

1) 可见性：写立即刷主存、读从主存读；2) 有序性：通过内存屏障禁止特定重排序（写前插 StoreStore、写后插 StoreLoad 等）；3) 不保证原子性，i++ 仍不安全；4) 底层在 x86 上是 lock 前缀指令；5) 典型用途：状态标志位、双重检查锁单例。

**参考回答**：

volatile 保证：1) 可见性——写立即刷主存、读从主存取；2) 有序性——通过内存屏障禁止特定重排序；3) 不保证原子性。底层是 lock 前缀指令（x86 下）实现。典型用途：状态标志、双重检查单例。

**常见追问**：为什么双重检查单例里 volatile 是必需的？

---

## 33. 什么是 happens-before 原则？

> 原题 ID：`q4024`

**高频程度**：★★★★

**考察点**：考察 happens-before 原则的定义与常见规则。

**回答框架**：

1) 定义：A happens-before B 表示 A 的结果对 B 可见，是判断数据竞争与可见性的规则；2) 常见规则：程序顺序、volatile 写读、锁解锁-加锁、线程 start/join、传递性；3) 意义：把底层内存屏障抽象为可推理的规则，程序员不必直接关心屏障。

**参考回答**：

happens-before 是判断数据竞争的内存可见性规则：若 A happens-before B，则 A 的结果对 B 可见。规则包括：程序顺序、volatile 写读、锁解锁-加锁、线程 start/join、传递性。它避免了程序员直接关心底层内存屏障。

**常见追问**：happens-before 和时间上的先后是同一回事吗？

---

## 34. 字符串常量池在 JDK 中是如何演进的？

> 原题 ID：`q4025`

**高频程度**：★★★

**考察点**：考察字符串常量池的存放位置演进。

**回答框架**：

1) JDK6 及之前常量池在永久代；2) JDK7 移到堆中；3) JDK8 永久代被元空间取代，常量池仍在堆；4) String.intern() 入池，已有则返回已有引用；5) 演进目的是降低永久代 OOM 风险、便于 GC。

**参考回答**：

JDK6 及之前字符串常量池在永久代；JDK7 移到堆中；JDK8 永久代被元空间取代，常量池仍在堆。String.intern() 会把字符串入池，池中已有则返回已有引用。这样的演进减少了永久代 OOM 风险。

**常见追问**：大量使用 intern() 会有什么副作用？

---

## 35. 常用 JVM 调优参数有哪些？

> 原题 ID：`q4026`

**高频程度**：★★★★

**考察点**：考察常用 JVM 调优参数及调优方法。

**回答框架**：

1) 堆：-Xms/-Xmx（建议设为相等）、-Xmn/-XX:NewRatio；2) 元空间：-XX:MetaspaceSize/-XX:MaxMetaspaceSize；3) 回收器：-XX:+UseG1GC、-XX:MaxGCPauseMillis；4) 诊断：-XX:+HeapDumpOnOutOfMemoryError、GC 日志；5) 栈：-Xss。调优先看 GC 日志与监控再定策略。

**参考回答**：

-Xms/-Xmx 设置堆初始/最大；-Xmn 新生代大小；-XX:MetaspaceSize 元空间；-XX:+UseG1GC 选择回收器；-XX:MaxGCPauseMillis 目标停顿；-XX:+HeapDumpOnOutOfMemoryError；-Xss 线程栈大小。调优先看 GC 日志再定策略。

**常见追问**：-Xms 和 -Xmx 不设相等会有什么问题？

---

## 36. 方法区（元空间）存什么？和永久代区别？

> 原题 ID：`q4027`

**高频程度**：★★★★

**考察点**：考察方法区规范与永久代/元空间实现的区别。

**回答框架**：

1) 方法区是 JVM 规范中的概念，存类结构、运行时常量池、静态变量等；2) JDK7 及以前由永久代实现（在 JVM 内存内、有固定上限、易 OOM）；3) JDK8 起由元空间实现（本地内存、默认无上限、GC 条件不同）；4) JDK7 已将字符串常量池与静态变量移到堆。

**参考回答**：

方法区是规范，JDK8 之前实现是永久代（在 JVM 内存、有 GC、易 OOM），之后是元空间（使用本地内存、默认无上限、GC 条件不同）。存类结构、运行时常量池、静态变量（JDK7 后静态变量/常量池移到堆）。

**常见追问**：元空间也会 OOM 吗？什么场景？

---

## 37. Java 对象的创建一定在堆上吗？

> 原题 ID：`q4028`

**高频程度**：★★★★

**考察点**：考察逃逸分析与 JIT 优化对对象分配的优化。

**回答框架**：

1) 绝大多数对象仍在堆上分配；2) JIT 做逃逸分析：对象未逃逸出方法时可能做标量替换、栈上分配、同步消除；3) 好处是减少堆分配与 GC 压力；4) 这是「对象不一定在堆上」的优化，但属于实现细节、不可依赖。

**参考回答**：

绝大多数对象在堆上分配，但 JIT 会做逃逸分析：若对象未逃逸出方法，可能标量替换（拆成基本类型）、栈上分配、同步消除，避免堆分配与 GC 压力。这是『对象不一定在堆上』的优化。

**常见追问**：逃逸分析的优化为什么不能作为编程假设？

---

## 38. 哪些条件会触发特定 JVM 收集器的 Full GC 或降级路径？如何诊断？

> 原题 ID：`q4029`

**高频程度**：★★★★

**考察点**：考察 Full GC 的触发条件。

**回答框架**：

1) 老年代空间不足；2) 元空间不足；3) 显式 System.gc()（建议禁用以避免）；4) 新生代晋升平均大小大于老年代剩余空间（分配担保失败）；5) CMS 并发模式失败；6) G1 的 Mixed GC 失败。Full GC 停顿长，应通过调参和减少对象提升来规避。

**参考回答**：

Full GC 或退化回收的触发条件与收集器密切相关：老年代/元空间压力、显式 `System.gc()`、晋升失败、分配失败等都可能参与；CMS 的 concurrent mode failure、G1 的 evacuation failure 或其他退化路径也有各自条件。不能把某个收集器的术语套到所有 JVM。

排查应先确认 JDK、GC 算法、堆/元空间参数和 GC 日志，再查看触发原因、停顿、晋升、存活对象和分配速率。治理可能是修复泄漏、降低对象分配、调整堆/region/并发参数或换收集器，必须基于实际日志验证。

**常见追问**：为什么看到一次 Full GC 后，第一步应先确认具体收集器和 GC 日志原因？

---

## 39. 线程池的核心参数与执行流程？

> 原题 ID：`q4031`

**高频程度**：★★★★★

**考察点**：考察线程池核心参数与任务执行流程。

**回答框架**：

1) 七个参数：corePoolSize、maximumPoolSize、keepAliveTime、unit、workQueue、threadFactory、handler；2) 流程：任务来→核心线程未满则新建→核心满则入队→队满则开非核心线程→达最大则拒绝；3) 拒绝策略有 Abort/Discard/DiscardOldest/CallerRuns；4) 队列类型直接影响行为，建议有界队列。

**参考回答**：

参数：corePoolSize 核心线程、maximumPoolSize 最大、keepAliveTime 空闲存活、workQueue 队列、threadFactory、handler 拒绝策略。流程：任务来→核心线程满→入队→队满→开非核心线程→达最大→执行拒绝策略（Abort/Discard/DiscardOldest/CallerRuns）。

**常见追问**：为什么用无界队列时 maximumPoolSize 会失效？

---

## 40. 常见的线程池拒绝策略有哪些？

> 原题 ID：`q4032`

**高频程度**：★★★★

**考察点**：考察四种拒绝策略的语义与选型。

**回答框架**：

1) AbortPolicy：抛 RejectedExecutionException（默认）；2) DiscardPolicy：静默丢弃；3) DiscardOldestPolicy：丢弃队首最老任务后重试提交；4) CallerRunsPolicy：由提交任务的线程自己执行，形成负反馈背压；5) 也可自定义（落库、报警、降级）。

**参考回答**：

1) AbortPolicy：抛 RejectedExecutionException（默认）；2) DiscardPolicy：静默丢弃；3) DiscardOldestPolicy：丢弃队首最老任务重试；4) CallerRunsPolicy：由提交任务的线程自己执行，起到负反馈限流作用。也可自定义。

**常见追问**：CallerRunsPolicy 在什么情况下会拖垮调用方？

---

## 41. AQS（AbstractQueuedSynchronizer）的核心思想？

> 原题 ID：`q4034`

**高频程度**：★★★★★

**考察点**：考察 AQS 的设计思想与实现要点。

**回答框架**：

1) 用一个 volatile int state 表示同步状态，配合 CAS 修改；2) 一个 CLH 变体的双向队列存放阻塞线程；3) 获取失败入队并 park，释放时 unpark 后继；4) 支持独占（ReentrantLock）与共享（Semaphore/CountDownLatch）两种模式；5) 用模板方法把「是否可获取」留给子类实现。

**参考回答**：

AQS 用一个 volatile int state 表示同步状态，配一个 CLH 队列存放阻塞线程。获取资源失败入队并 park；释放时 unpark 队首。ReentrantLock（独占）、Semaphore/CountDownLatch（共享）都基于它实现。

**常见追问**：为什么 AQS 要把 state 和队列都做成模板方法？

---

## 42. ConcurrentHashMap 在 JDK7 和 JDK8 的实现区别？

> 原题 ID：`q4035`

**高频程度**：★★★★★

**考察点**：考察 ConcurrentHashMap 在 JDK7 与 JDK8 的实现演进。

**回答框架**：

1) JDK7：分段锁 Segment（继承 ReentrantLock），默认 16 段，锁粒度到段；2) JDK8：废弃 Segment，改为 Node 数组 + 链表/红黑树；3) 写操作 CAS 初始化 + synchronized 只锁桶头节点；4) 读操作基本无锁（Node 的 val 与 next 用 volatile）；5) 并发度显著提升，且链表过长会树化。

**参考回答**：

JDK7 用分段锁 Segment（继承 ReentrantLock），默认 16 段减小锁粒度；JDK8 废弃 Segment，用 Node 数组 + 链表/红黑树，写用 CAS + synchronized（只锁桶头节点），读无锁（volatile），并发度更高。

**常见追问**：JDK8 的 ConcurrentHashMap 扩容时怎么保证并发安全？

---

## 43. 什么是 CAS？ABA 问题如何解决？

> 原题 ID：`q4036`

**高频程度**：★★★★★

**考察点**：考察 CAS 原理与 ABA 问题。

**回答框架**：

1) CAS 是原子指令：比较内存值与预期值，相等则写入新值；2) 依赖 CPU 的 cmpxchg 与 JNI/Unsafe 实现；3) ABA 问题：值从 A→B→A，CAS 无法察觉中间变化；4) 解决：加版本号（AtomicStampedReference）或用时间戳标记。

**参考回答**：

CAS（Compare-And-Swap）是一条原子指令：比较内存值与预期值，相等则更新。ABA 问题是中间值从 A→B→A 导致 CAS 误判。解决：加版本号（AtomicStampedReference）或时间戳。

**常见追问**：除了版本号，还有什么方式能规避 ABA？

---

## 44. Java 中阻塞队列有哪些？使用场景？

> 原题 ID：`q4038`

**高频程度**：★★★

**考察点**：考察常用阻塞队列及适用场景。

**回答框架**：

1) ArrayBlockingQueue：有界数组、支持公平；2) LinkedBlockingQueue：链表、默认近似无界（易堆积）；3) SynchronousQueue：不存储、直接交付，用于 CachedThreadPool；4) PriorityBlockingQueue 优先级、DelayQueue 延迟、LinkedTransferQueue 传递；5) 主要用于生产者-消费者解耦与背压。

**参考回答**：

ArrayBlockingQueue（有界数组）、LinkedBlockingQueue（链表，默认无界）、SynchronousQueue（不存储，直接交付，用于 CachedThreadPool）、PriorityBlockingQueue（优先级）、DelayQueue（延迟）、LinkedTransferQueue。常用于生产者-消费者。

**常见追问**：线程池里用无界 LinkedBlockingQueue 有什么隐患？

---

## 45. CompletableFuture 解决了什么问题？

> 原题 ID：`q4039`

**高频程度**：★★★★

**考察点**：考察 CompletableFuture 的异步编排能力。

**回答框架**：

1) Future 只能阻塞 get，无法组合；2) CompletableFuture 提供 thenApply/thenAccept/thenRun 串联，thenCombine/applyToEither 聚合，allOf/anyOf 编排多任务；3) exceptionally/handle/whenComplete 处理异常；4) 可传入自定义线程池避免占用 ForkJoinPool 公共池。

**参考回答**：

CompletableFuture 提供声明式异步编排：thenApply/thenAccept/thenRun 串联，thenCombine/applyToEither 聚合，exceptionally/handle 异常处理，支持自定义线程池。相比 Future 只能阻塞 get，它支持回调与组合，适合多任务编排。

**常见追问**：CompletableFuture 用默认线程池会有什么风险？

---

## 46. volatile 和 synchronized 能互相替代吗？

> 原题 ID：`q4040`

**高频程度**：★★★★★

**考察点**：考察 volatile 与 synchronized 的能力边界。

**回答框架**：

1) volatile 保证可见性与有序性，但不保证原子性；2) synchronized 同时保证原子性、可见性、有序性（互斥）；3) i++、check-then-act 这类复合操作必须用锁或原子类；4) 两者不是替代关系，而是互补。

**参考回答**：

不能。volatile 保证可见性+有序性但不保证原子性（如 i++ 非原子）；synchronized 保证原子性+可见性+有序性（互斥）。单读单写标志位用 volatile 足够；复合操作（i++、check-then-act）必须用锁或原子类。

**常见追问**：volatile 修饰的 long/double 有什么特别之处？

---

## 47. Java 线程的状态有哪些？

> 原题 ID：`q4041`

**高频程度**：★★★★

**考察点**：考察 Java 线程的六种状态及转换。

**回答框架**：

1) NEW 新建未启动；2) RUNNABLE 可运行（含就绪与运行）；3) BLOCKED 等监视器锁；4) WAITING 无期限等待（wait/join/park）；5) TIMED_WAITING 带超时等待（sleep/带超时 wait）；6) TERMINATED 结束；7) 注意 BLOCKED 与 WAITING 的阻塞原因不同。

**参考回答**：

Thread.State：NEW、RUNNABLE（含就绪+运行）、BLOCKED（等监视器锁）、WAITING（wait/join/park 无期限）、TIMED_WAITING（sleep/带超时 wait）、TERMINATED。注意 BLOCKED 和 WAITING 是不同的阻塞原因。

**常见追问**：线程处于 WAITING 状态时 CPU 占用是高还是低？

---

## 48. 原子类（AtomicInteger 等）的实现原理？

> 原题 ID：`q4042`

**高频程度**：★★★★

**考察点**：考察原子类的实现原理与高竞争下的优化。

**回答框架**：

1) 底层用 Unsafe 的 CAS 自旋更新 volatile 变量，如 incrementAndGet 循环 compareAndSet；2) 优点是免锁、高并发；3) 缺点是高竞争下自旋空转、CPU 浪费；4) LongAdder 用分片 Cell 分散热点进一步降竞争，统计求和时再聚合。

**参考回答**：

底层用 Unsafe 的 CAS 循环（自旋）更新 volatile 变量。例如 incrementAndGet 循环 compareAndSet 直到成功。优点是免锁高并发，缺点是高竞争下自旋开销大。LongAdder 用分片 Cell 进一步降低竞争。

**常见追问**：LongAdder 为什么比 AtomicLong 更适合高并发计数？

---

## 49. wait/notify 为什么必须在 synchronized 内调用？

> 原题 ID：`q4043`

**高频程度**：★★★★

**考察点**：考察 wait/notify 与对象监视器的关系。

**回答框架**：

1) wait/notify 操作的是对象监视器 Monitor，必须先持有该对象锁，否则抛 IllegalMonitorStateException；2) wait 会释放锁并进入等待队列；3) notify 唤醒后线程需重新竞争锁才能继续；4) 因此必须写在 synchronized 块内，通常配合 while 循环判断条件防止虚假唤醒。

**参考回答**：

wait/notify 操作的是对象监视器（Monitor），必须在持有该对象锁时调用，否则抛 IllegalMonitorStateException。wait 会释放锁并进入等待队列，notify 唤醒后需重新竞争锁才能继续。

**常见追问**：为什么 wait 要用 while 而不是 if 包住？

---

## 50. 及其版本目录 (Version Catalog) 的灵活性，学习如何优雅地管理大型项目依赖？

> 原题 ID：`q1981`

**高频程度**：★★★

**考察点**：考察大型项目依赖治理能力：版本集中声明、bundle 批量引用、BOM 对齐、多目录拆分与冲突解决优先级。

**回答框架**：

1）版本集中：libs.versions.toml 的 versions/libraries/bundles/plugins 四段声明；
2）使用方式：libs.xxx 类型安全访问、alias 引用插件；
3）BOM 对齐：platform 与 enforcedPlatform 的区别；
4）多目录拆分：settings 中按域创建额外 catalog；
5）冲突解决顺序：BOM/platform 优先，其次 constraints，最后 resolutionStrategy。

**参考回答**：

大型多模块项目常见的问题是版本散落在各个 build.gradle 里、依赖冲突、升级成本高、不同团队重复声明。Gradle 7.0 之后引入了 Version Catalog，默认文件是 gradle/libs.versions.toml，通过 versions、libraries、bundles、plugins 四段声明，构建脚本里用 libs.xxx 做类型安全访问。我讲几个核心用法。第一是版本集中：在 versions 段定义 spring 和 kotlin 的版本号，在 libraries 段通过 version.ref 引用，这样升级一个数字就全项目生效，PR 里也能清晰审阅。第二是 bundle 批量引用：比如把 spring-core 和 spring-context 组成 spring bundle，依赖里一行 implementation(libs.bundles.spring) 就能引入一组库。第三是 BOM 对齐：用 platform(libs.spring.bom) 或者 enforcedPlatform 统一下传递依赖版本，前者可以被覆盖，后者是强制的，这个区别在排查冲突时很关键。第四是多目录拆分为团队所用：在 settings.gradle.kts 的 dependencyResolutionManagement 里用 from(files(...)) 创建额外的 catalog，比如给测试域单独建 testLibs，实现按域拆分。第五是冲突解决策略，我一般遵循一个优先级：优先用 platform 或 BOM 对齐，其次用 constraints 声明版本约束，最后才用 resolutionStrategy 强制版本，避免到处写 force 把真实冲突掩盖掉。难点与决策上我讲三点：版本冲突优先用 BOM 对齐；动态版本和 SNAPSHOT 虽然 catalog 支持，但会破坏可复现性，建议 CI 里配合 dependencyLocking 锁定；迁移成本上我建议先建 catalog 再逐模块替换，用脚本扫描硬编码坐标保证编译通过。复盘：集中之后升级一个版本号就全项目生效、PR 可审计，但要注意 IDE 同步、别名命名规范用 kebab-case，以及 catalog 与插件版本耦合时可能出现的循环问题。

**常见追问**：platform 和 enforcedPlatform 的差别？什么时候必须用 enforcedPlatform？

---

## 51. 自旋锁和互斥锁的区别是什么，你的项目里是怎么选的？

> 原题 ID：`q3537`

**高频程度**：★★★★

**考察点**：考察锁机制原理与选型判断：等待策略、上下文限制、开销、临界区长度与竞争程度，以及如何用测量数据做决策。

**回答框架**：

1）等待行为：自旋忙等不释放 CPU，互斥睡眠让出 CPU；
2）上下文限制：自旋可用于中断/原子上下文，互斥不能在中断上下文使用；
3）开销：自旋无上下文切换但浪费 CPU，互斥有两次切换但等待不占 CPU；
4）选型依据：临界区长度、是否可睡眠、竞争程度、上下文；
5）复盘：先测量再选锁，能用原子操作/无锁就不用锁。

**参考回答**：

自旋锁和互斥锁的核心区别在等待策略和适用场景，我讲五点。第一，等待行为。自旋锁在获取不到锁时会在循环里反复检查锁状态，也就是忙等，不释放 CPU；互斥锁获取不到时会进入睡眠，把 CPU 让给其他线程，等锁释放后再被唤醒。第二，上下文限制。自旋锁可以用在中断上下文、软中断和原子上下文，因为它不睡眠；互斥锁会睡眠，所以不能在中断上下文或持有自旋锁时使用，否则会导致睡眠死锁。第三，开销。自旋锁没有上下文切换开销，但会浪费 CPU；互斥锁有睡眠和唤醒两次上下文切换开销，但等待期间不占 CPU。第四，临界区长度。自旋锁适合极短的临界区，通常只有几条指令，比如改一个计数器或更新一个指针；互斥锁适合较长的临界区，或者临界区内可能发生阻塞，比如 I/O、内存分配、调用可能睡眠的函数。第五，竞争程度。低竞争时自旋锁很快；高竞争时自旋会浪费大量 CPU，还会加剧缓存行弹跳，此时互斥锁反而更合适。项目里的选择我举一个例子。背景：我在一个高并发网络服务中负责连接管理模块，每个连接有状态结构，多个工作线程会并发更新连接状态、引用计数和统计信息。我的决策是：对连接引用计数、状态标志位这种只改几个字段、临界区只有几条指令的场景，用自旋锁或原子操作，因为临界区极短，睡眠唤醒的开销远大于自旋等待，而且这些代码可能被中断处理路径调用，不能睡眠；对连接建立销毁、需要访问共享哈希表并可能触发内存分配或日志 I/O 的路径，用互斥锁，因为临界区较长且可能阻塞；对读多写少的配置表，用读写锁或无锁 RCU 思路，读侧几乎无开销。复盘有两点：一开始为了『高性能』把所有锁都换成自旋锁，结果在 64 核机器上高竞争时 CPU 大量空转，吞吐反而下降，后来用 perf 看 spin 占比，把长临界区改回互斥锁并缩小临界区，性能明显提升；另外我还踩过在持有自旋锁时调用可能睡眠的函数，导致系统不稳定，后来严格约束自旋锁内只做内存操作。最终原则是：先测量竞争和临界区长度，再选锁；能用原子操作或无锁结构就不用锁。

**常见追问**：MCS 锁相比 ticket 锁解决了什么问题？为什么？

---

## 52. 抽象类和接口的区别？

> 原题 ID：`q3505`

**高频程度**：★★★★

**考察点**：考察面向对象抽象手段的语义差异与语法约束，以及设计时的选择依据。

**回答框架**：

1) 语义：抽象类是 is-a 的模板，接口是 can-do 的契约；2) 语法：单继承 vs 多实现，字段与方法修饰符差异；3) 演化：Java 8 的 default 方法、Java 9 的 private 方法；4) 选择依据：有共享状态和模板逻辑用抽象类，只定义能力用接口。

**参考回答**：

抽象类和接口都是面向对象中用于抽象、解耦和多态的手段，但设计意图不同。第一，语义与关系：抽象类表示同一类事物的模板，强调 is-a，比如动物是抽象类，猫和狗继承它，共享 name、age 这些状态和 eat 这类通用行为；接口表示一种能力或契约，强调 can-do，比如会飞是接口，鸟、飞机、超人都能实现它，但它们并不属于同一继承体系。第二，语法限制（以 Java 为例）：继承数量上，类只能 extends 一个抽象类，但可以 implements 多个接口；成员变量上，抽象类可以有普通字段、静态字段和任意访问修饰符，接口的字段默认是 public static final 也就是常量；方法上，抽象类可以同时包含抽象方法和具体方法，接口在 Java 8 之前只能有 public abstract 方法，Java 8 增加了 default 和 static 方法，Java 9 又增加了 private 方法用于抽取内部复用；构造器上，抽象类有构造器供子类 super 调用，接口没有构造器；修饰符上，抽象方法可以是 protected 或 public，接口方法默认是 public。第三，设计选择依据：如果多个子类需要共享状态（字段）和复用通用实现，或者需要定义带构造流程的模板方法，用抽象类更合适；如果只是定义一组能力契约，让不相关的类型都能具备，或者需要多继承行为，用接口更合适。现代设计的倾向是接口优先、组合优于继承：用接口定义契约，用组合或默认方法复用实现，这样耦合更低、更容易测试和替换。另外在 Go 里没有类和继承，只有接口和结构体嵌入，接口是隐式实现的，这实际上把接口的契约作用发挥得更纯粹。

**常见追问**：那 Java 8 的 default 方法会不会让接口和抽象类的界限模糊了？

---

## 53. 公平锁和非公平锁哪个性能更好？为什么？

> 原题 ID：`q3623`

**高频程度**：★★★★★

**考察点**：面试官考察数据库原理与调优：索引结构/B+树、事务隔离与 MVCC、锁与死锁、慢 SQL 优化与执行计划；能否从‘为什么慢’推导到具体改法是关键。

**回答框架**：

① 源码层面：ReentrantLock的非公平锁在lock()方法中直接调用compareAndSetState(0,1)尝试获取锁，失败才进入acquire()；公平锁则先检查hasQueuedPredecessors()，确保没有前驱节点
2. 论文参考：非公平锁的性能优势在《Java并发编程实战》中有详细讨论，也符合操作系统中的锁优化策略（如自旋锁、偏向锁）。
3. 踩坑：非公平锁可能导致线程饥饿，但实际中由于线程调度和锁持有时间短，饥饿概率较低。另外，公平锁在锁释放时唤醒下一个线程，但该线程可能因为CPU调度延迟而未能及时获取锁，导致锁空闲，进一步降低性能。
4. 权衡：在需要严格顺序或避免饥饿的场景（如任务调度），公平锁更合适；在追求高吞吐量的场景（如Web服务器），非公平锁更优。
5. 误以为公平锁性能更好，因为公平锁避免了竞争，实际上竞争减少但上下文切换和唤醒开销更大。
6. 认为非公平锁一定导致饥饿，实际上在大多数场景下饥饿很少发生，且可以通过tryLock带超时来缓解。
7. 忽略锁的实现细节，如ReentrantLock默认是非公平锁，而synchronized在JDK1.6后也采用非公平锁策略。

**参考回答**：

通常非公平锁性能更好，因为它避免了线程唤醒后重新排队和上下文切换的开销，允许新线程直接抢占，提高了吞吐量。在Java中，ReentrantLock支持公平锁和非公平锁。公平锁严格按照FIFO顺序获取锁，非公平锁允许插队。性能差异主要源于： 1. 公平锁：当锁释放时，会唤醒等待队列头部的线程。被唤醒的线程需要从内核态返回到用户态，并重新竞争锁。如果此时有新的线程尝试获取锁，由于公平锁的机制，新线程会直接进入队列等待，不会抢占。但被唤醒的线程可能因为调度延迟未能及时获取锁，导致锁空闲时间增加。 2. 非公平锁：当锁释放时，会先尝试快速获取锁（CAS），如果成功则直接执行，无需唤醒等待线程。这减少了线程上下文切换和唤醒开销。同时，新来的线程可以直接抢占锁，提高了吞吐量。但可能导致等待队列中的线程饥饿。 实际测试表明，非公平锁的吞吐量通常比公平锁高一个数量级。例如，在高度竞争的场景下，非公平锁的吞吐量可能是公平锁的5-10倍。 但公平锁能保证线程获取锁的顺序，避免饥饿，适用于对公平性有要求的场景。

**常见追问**：高并发下死锁如何排查与避免？ 分库分表后跨分片查询和分布式事务怎么处理？

---
