"""Focused factual corrections found during the follow-up corpus review."""

from reviewed_reclassification_v3 import question


OVERRIDES = {
    "q0007": question(
        "Go 的 GMP 调度器与 channel 分别如何工作？",
        "G、M、P 的分工，以及 channel 的阻塞、复制和关闭语义。",
        ["G 是 goroutine，M 是操作系统线程，P 提供调度资源",
         "调度器利用本地队列、工作窃取、网络轮询和抢占",
         "无缓冲 channel 直接复制元素到接收方；有缓冲 channel 使用缓冲区",
         "发送到已关闭 channel 会 panic；并非每个 channel 都必须关闭"],
        """G 表示 goroutine，M 表示操作系统线程，P 表示执行 Go 代码所需的调度资源；M 通常要持有 P 才能运行 G。调度器结合本地可运行队列、工作窃取、网络轮询和抢占工作，P 的数量由 GOMAXPROCS 决定。

无缓冲 channel 需要发送和接收匹配。运行时可以直接把元素从发送方复制到接收方，省去中间缓冲区，但这仍是内存复制，并非“零拷贝”。有缓冲 channel 在缓冲区满时阻塞发送，在空时阻塞接收。关闭后发送会 panic；接收可读出剩余元素，之后得到零值且 ok=false。

是否关闭由生命周期协议决定。若消费者通过 context 取消或约定次数退出，不关闭 channel 也不必然永久阻塞；一般由唯一发送方或协调方负责关闭。""",
        "无缓冲 channel 直接交接时为什么仍有一次内存复制？",
        [("Go runtime chan.go", "https://go.dev/src/runtime/chan.go")],
    ),
    "q0394": question(
        "Redis Hash 查找一个 field 的复杂度是多少？",
        "区分紧凑编码的线性查找和 hashtable 的平均常数时间。",
        ["Redis 7 及之后的小 Hash 常用 listpack，旧版本可能用 ziplist",
         "紧凑编码查找通常是 O(N)",
         "hashtable 编码平均 O(1)，最坏情形可能退化",
         "用 OBJECT ENCODING 确认实际编码"],
        """HGET 等按 field 查找操作的成本取决于 Hash 对象的编码。紧凑编码顺序存储少量 field/value，查找通常要扫描，为 O(N)；Redis 7 及之后使用 listpack，Redis 6.2 及之前常见 ziplist。对象变大后可能转换为 hashtable，平均查找复杂度为 O(1)，但不能保证绝对最坏情况也是 O(1)。

应先确认 Redis 版本和 OBJECT ENCODING 的结果，不能把“只有 ZIPLIST/HASHTABLE”写成所有版本通用的结论。""",
        "小 Hash 为什么值得用线性查找的紧凑编码？",
        [("Redis OBJECT ENCODING", "https://redis.io/docs/latest/commands/object-encoding/")],
    ),
    "q0411": question(
        "Redis 为什么主要由单线程执行命令，仍能保持较高吞吐？",
        "内存访问、数据结构、事件循环和命令复杂度对吞吐与延迟的影响。",
        ["常见操作主要访问内存",
         "数据结构与非阻塞 I/O 减少等待",
         "命令串行化简化并发协调",
         "慢命令、大键和 CPU 密集操作仍可能阻塞事件循环"],
        """Redis 的常见读写主要在内存中完成，配合合适的数据结构、非阻塞套接字和 I/O 多路复用，单实例可以高效处理大量连接。主要命令串行执行也简化了共享数据结构的并发协调。

这不表示任何负载都快，也不能断言瓶颈永远是 I/O。复杂命令、大键或 Lua 脚本可能长时间占用命令执行线程；网络读写、协议解析和单核 CPU 也可能成为瓶颈。应结合慢日志、延迟、CPU 和网络指标定位。""",
        "一个复杂度较高的命令会怎样影响同实例的其他请求？",
    ),
    "q0412": question(
        "Redis 6 为什么引入可选的多线程 I/O？命令也会并行执行吗？",
        "区分客户端 I/O 的并行化与核心命令执行的串行语义。",
        ["I/O 线程可在部分高并发工作负载中分担网络读写",
         "默认主要分担写出；读取和解析需另外配置",
         "Redis 6 的核心命令执行仍主要在主线程",
         "是否启用由实际压测决定"],
        """Redis 6 增加可配置的 I/O 线程，是为了在部分高并发负载中利用多核处理客户端套接字 I/O。启用后默认主要分担写出；是否将读取和协议解析也交给 I/O 线程，由 io-threads-do-reads 控制。核心命令执行仍主要由主线程串行处理，不能把 I/O 多线程理解成多个线程同时修改同一数据结构。

这也不证明 Redis 永远受 I/O 限制。若瓶颈在慢命令或其他 CPU 工作，多线程 I/O 未必有收益，应结合实际压测判断。""",
        "为什么增加 I/O 线程不能解决慢命令阻塞？",
        [("Redis 6 redis.conf", "https://raw.githubusercontent.com/redis/redis/6.0/redis.conf")],
    ),
    "q0413": question(
        "Redis 6 的多线程 I/O 默认开启吗？如何配置？",
        "区分 io-threads 默认值 1 与默认不启用多线程 I/O。",
        ["默认不启用；io-threads 默认值是 1，不是 0",
         "设为大于 1 才引入额外 I/O 线程",
         "io-threads-do-reads 默认 no",
         "根据核心数和负载压测决定线程数"],
        """Redis 6 默认不启用多线程 I/O。io-threads 的默认值是 1，表示只用主线程；“默认 0 表示禁用”是错误的。可在配置文件中设 io-threads 4 等大于 1 的值启用额外 I/O 线程。

启用后默认主要分担客户端写出；io-threads-do-reads 默认 no，要分担读取和协议解析需按需设为 yes。命令执行仍主要在主线程。线程越多不一定越快，应结合机器核心数和请求特点压测。""",
        "io-threads=1 与 io-threads-do-reads=no 分别意味着什么？",
        [("Redis 6 redis.conf", "https://raw.githubusercontent.com/redis/redis/6.0/redis.conf")],
    ),
    "q0583": question(
        "MySQL 深分页为什么慢？如何用键集分页或延迟关联优化？",
        "OFFSET 代价、游标方向、稳定排序与覆盖索引的适用条件。",
        ["大 OFFSET 通常要处理并丢弃前面的行；回表次数取决于执行计划",
         "键集分页的比较方向必须与排序方向一致",
         "相同分数要以唯一 ID 打破并列",
         "随机跳页可考虑覆盖索引加延迟关联，并用 EXPLAIN ANALYZE 验证"],
        """ORDER BY score DESC, id DESC LIMIT 10000, 20 通常需要跳过大量候选记录。是否逐行回表取决于索引、查询列和执行计划，不能一概而论。覆盖索引可减少读取完整行的成本，但不能消除大偏移量本身。

只需“下一页”时，可采用键集分页，并在 score 后加唯一 ID 保证稳定次序。假设上一页最后一行是 (:last_score, :last_id)，且有匹配的索引：

```sql
SELECT id, score FROM t_player
WHERE score < :last_score
   OR (score = :last_score AND id < :last_id)
ORDER BY score DESC, id DESC
LIMIT 20;
```

随机跳到第 N 页时，可先用覆盖索引取目标页 ID，再与原表关联取完整行，减少回表，但仍需跳过前面的索引项。最终应以 EXPLAIN ANALYZE 和真实数据验证。""",
        "按 score 降序时，为什么下一页不能用 score > last_score？",
        [("MySQL LIMIT optimization", "https://dev.mysql.com/doc/refman/8.4/en/limit-optimization.html")],
    ),
    "q0588": question(
        "MySQL 与 MongoDB 各适合什么场景？如何比较事务与文档建模？",
        "关系模型、BSON 文档、索引、事务和查询方式的实际边界。",
        ["MySQL 使用关系表，MongoDB 使用 BSON 文档",
         "MongoDB 支持多文档事务",
         "灵活字段不等于不需要 schema 治理",
         "按访问模式和约束验证选型，不作绝对性能判断"],
        """MySQL 适合需要明确约束、复杂关联查询和成熟 SQL 事务的场景。MongoDB 是文档数据库，以 BSON 而非 XML 存储文档；字段可灵活演进，但生产系统仍需要应用侧约束、索引和必要的 schema 验证。

MongoDB 支持多文档事务，不能说“不支持事务”。文档建模常优先让一起读写的数据放在同一文档；也能通过聚合管道等能力做关联查询。选型时应看数据模型、主要查询、事务边界、扩容目标和运维经验，不能声称任何一方对所有非索引查询都更快。""",
        "什么数据适合嵌入同一文档，什么数据适合引用？",
        [("MongoDB BSON", "https://www.mongodb.com/docs/manual/reference/bson-types/"),
         ("MongoDB transactions", "https://www.mongodb.com/docs/manual/core/transactions/")],
    ),
    "q3401": question(
        "Elasticsearch 与 MySQL 做全文检索时，各自的优势和边界是什么？",
        "比较搜索引擎与 MySQL FULLTEXT，而非说 MySQL 只能 LIKE 扫描。",
        ["MySQL 支持 FULLTEXT、MATCH AGAINST 相关性与 ngram 分词器",
         "Elasticsearch 提供更丰富的分析器、相关性调优与分布式检索",
         "前导通配符 LIKE 难用普通 B+ 树索引是另一回事",
         "按检索复杂度、同步成本和规模选型"],
        """MySQL 不只有 B+ 树：InnoDB 支持 FULLTEXT 索引，可用 MATCH (...) AGAINST (...) 做全文检索和相关性计算，也提供 ngram 分词器。因此“全文只能用 LIKE '%词%' 扫描”和“没有相关性模型”都不成立。前导通配符 LIKE 难以利用普通 B+ 树索引，是另一个问题。

Elasticsearch 的分析器、查询组合、相关性调优、聚合与分片能力更丰富，适合复杂检索，但也带来索引同步、近实时可见性和运维成本。需求较简单时，MySQL FULLTEXT 可能已足够。应以真实查询和数据评测，而不是断言其中一方永远更快。""",
        "什么时候 MySQL FULLTEXT 已足够，什么时候值得增加 Elasticsearch？",
        [("MySQL full-text search", "https://dev.mysql.com/doc/refman/8.4/en/fulltext-natural-language.html"),
         ("MySQL ngram parser", "https://dev.mysql.com/doc/refman/8.4/en/fulltext-search-ngram.html")],
    ),
}
