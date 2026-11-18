"""Reviewed fixes for the 2026-09-26 audit; replayed after older corrections."""
from reviewed_reclassification_v3 import question


MERGED_INTO = {
    "q0398": "q0397",  # Redis resize: one shared rehash mechanism.
    "q3684": "q3683",  # RunnableSequence definition and repeated description.
    "q3288": "q2437",  # rem definition belongs with its reference-unit comparison.
    "q0861": "q0860",  # Same rope construction, with 75 minutes as a follow-up.
}

OVERRIDES = {
    "q2061": question(
        "可选调用 onOpen?.() 在什么情况下短路，什么情况下仍会报错？",
        "nullish 短路、可调用性与对象属性访问的边界。",
        ["仅在 null/undefined 时短路", "非函数值仍会抛 TypeError", "对象可空时另加 ?."],
        """`onOpen?.()` 表示可选调用，不是“只要不是函数就忽略”。

1. **null 或 undefined**：不调用，表达式结果为 undefined。
2. **可调用的值**：正常调用并返回其结果；函数自身抛出的异常仍会向外传播。
3. **其他非空值**：例如 42、false 或普通对象，调用会抛 TypeError。

```javascript
let onOpen;
onOpen?.(); // undefined
onOpen = () => "opened";
onOpen?.(); // "opened"
onOpen = 42;
// onOpen?.(); // TypeError: 不是函数
```

**对象可空与方法可空是两个检查点**

`obj.method?.()` 先读取 obj.method，因此 obj 为 null/undefined 时仍会报错。需要同时保护对象与方法时写 `obj?.method?.()`；但方法存在却不是函数时仍会报错。未声明的变量也不能靠可选链避免 ReferenceError。

与 `onOpen && onOpen()` 相比，可选调用只检查 null/undefined，不把 0、空字符串和 false 当作短路条件。""",
        "为什么 obj?.method?.() 仍不能保证永不抛异常？",
        [("MDN Optional chaining", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/Optional_chaining")],
    ),
    "q3108": question(
        "大模型服务吞吐不足时，如何优化批处理、并行度与调度？",
        "在线推理的批处理、KV cache、调度和延迟约束，而非训练梯度同步。",
        ["固定负载分布与延迟目标", "调批处理与 token 预算", "观察 KV cache 与抢占", "按瓶颈选择并行和调度策略"],
        """先明确这是在线推理服务：优化目标是在首 token 延迟（TTFT）和逐 token 延迟约束内，提高请求吞吐或输出 token 吞吐。

1. **定位瓶颈**：固定输入/输出长度分布和并发度，观察排队时间、TTFT、逐 token 延迟、GPU 利用率、显存和网络通信。不能只看平均 tokens/s。
2. **调整批处理**：连续批处理让已完成请求及时退出、新请求及时加入。调节并发序列数和每轮 token 预算；大批次可能提高吞吐，但也可能增加排队和单请求延迟。
3. **控制 KV cache 压力**：结合可用显存限制上下文长度与并发，检查缓存不足引发的抢占或重计算。前缀缓存只对可复用前缀有收益，不能假设所有请求都能命中。
4. **选择并行方式**：模型能放下时可增加独立副本分流；放不下或单请求计算受限时评估张量/流水并行。并行会引入通信与调度开销，跨机器尤其需要实测。
5. **平衡 prefill 与 decode**：长输入的 prefill 可能挤占正在生成请求的执行时间。分块 prefill 可交错两类工作；是否进一步分离部署，要连同 KV 传输成本与运维复杂度评估。

每次只改变一组参数，用相同负载比较吞吐、P95/P99 延迟、错误率和显存。梯度累积、学习率调整与反向 AllReduce 属于训练问题，不是这里的推理服务优化步骤。""",
        "为什么把并发数调大后，吞吐可能不升反降？",
        [("vLLM Optimization and Tuning", "https://docs.vllm.ai/en/latest/configuration/optimization/")],
    ),
    "q0940": question(
        "Kubernetes Service 如何通过 EndpointSlice 与数据平面把流量转发给后端 Pod？",
        "区分 Service 声明、EndpointSlice 维护和实际数据平面转发。",
        ["Service 定义入口与选择器", "控制器维护 EndpointSlice", "数据平面消费端点并转发", "说明无 selector 和 headless 的例外"],
        """以带 selector 的普通 ClusterIP Service 为例，过程可以分成三层。

1. **Service 定义入口**：声明稳定的虚拟 IP、服务端口、targetPort 和 Pod 选择器。Pod 重建后地址可以变化，客户端仍访问 Service 入口。
2. **控制平面维护 EndpointSlice**：EndpointSlice 控制器根据匹配的 Pod 及其状态，维护后端地址、端口和 ready 等条件；多个切片通过标签关联同一个 Service。它保存端点信息，不负责逐个转发请求。
3. **数据平面执行转发**：kube-proxy 监听 Service 与 EndpointSlice，并按其工作模式配置节点上的转发规则；也可以由替代的数据平面实现此职责。流量经节点网络规则选择合适后端，而不是让 API Server 代理每次请求。

**两个边界**

- 没有 selector 的 Service 不会自动获得按 Pod 选择器生成的端点，需要另外维护相应 EndpointSlice。
- Headless Service 不提供普通 ClusterIP 虚拟入口，通常由 DNS 返回后端地址，不能照搬上述虚拟 IP 转发路径。

旧 Endpoints 资源与 EndpointSlice 不是同一个 API；解释当前题目应围绕 EndpointSlice，旧实现只作为历史背景。""",
        "Pod 变为 NotReady 后，哪个组件更新端点，哪个组件改变转发行为？",
        [("Kubernetes EndpointSlices", "https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/"),
         ("Kubernetes Service", "https://kubernetes.io/docs/concepts/services-networking/service/")],
    ),
    "q2483": question(
        "Vue scoped 样式有哪些作用范围限制？Teleport 和 v-html 有什么区别？",
        "作用域属性、子组件边界和实际 DOM 祖先关系。",
        ["选择器与作用域属性配对", "区分子根节点和内部节点", "分别解释 Teleport 与 v-html", "克制使用 :deep"],
        """scoped 通过编译后的属性选择器限定匹配范围，例如 `.box[data-v-xxx]`。它不是 Shadow DOM，也不阻止继承或全局样式参与层叠。

1. **层叠与子组件**：增加属性选择器会改变权重。父组件的 scoped 样式可以作用于子组件根节点以便布局，但通常不会直接匹配子组件内部节点；需要穿透时可用 :deep，并限定外层容器。
2. **Teleport**：移动的是渲染后的 DOM 位置，并不会因此自动删除 scope 属性。直接匹配目标元素的 scoped 规则可以继续生效；若规则依赖原来的祖先结构，如 `.wrapper .dialog`，传送后祖先关系改变才可能导致失配。
3. **v-html 或手动创建节点**：这类内容没有经过对应模板编译，不会自动附加组件 scope 属性。可在受控容器下使用深度选择器或专门的样式规则；不可信 HTML 仍需独立处理注入风险。
4. **维护边界**：深度选择器不等于所有规则都变成全局，但会放宽匹配范围。优先使用组件提供的样式接口或 CSS 变量，避免依赖第三方组件内部 DOM。

排查顺序是检查实际 DOM 上的属性、祖先结构、编译后的选择器与层叠顺序，而不是一遇到 Teleport 就改成全局样式。""",
        "为什么 .dialog 能匹配传送后的元素，而 .wrapper .dialog 可能不能？",
        [("Vue SFC CSS Features", "https://vuejs.org/api/sfc-css-features"),
         ("Vue Teleport", "https://vuejs.org/guide/built-ins/teleport.html")],
    ),
    "q2409": question(
        "前端代码为什么常需要构建和打包？哪些情况下可以不打包？",
        "转换、依赖组织与性能优化的实际目的，避免把构建说成浏览器运行的必要条件。",
        ["原生代码可以直接运行", "非原生语法需要转换", "构建支持依赖和资源优化", "按项目规模选择工具"],
        """浏览器支持的 HTML、CSS、JavaScript 和原生 ES modules 可以直接运行；构建、打包并不是所有前端项目的必需步骤。

1. **代码转换**：TypeScript、JSX、Vue 单文件组件、SCSS 等开发格式通常需要转换。某种 JavaScript 语法是否要降级，取决于目标浏览器支持范围，而非只看语言年份。
2. **依赖与资源组织**：工具解析依赖、处理资源路径和环境配置，并可把浏览器不能直接消费的模块形式转换为可用产物。原生 ESM 本身不要求把所有模块合成一个文件。
3. **性能优化**：压缩、消除未使用代码、按需拆包、资源哈希等有助于减少传输和利用缓存；打包策略也可能带来过大的首屏包，需要实测。
4. **开发流程**：开发服务器、热更新和 Source Map 改善调试与协作，但这些收益不同于“浏览器不能执行源代码”。

简单静态页面或使用原生模块的小项目可以不打包；需要语法转换、复杂依赖和产物优化时再引入相应构建步骤。""",
        "构建与打包是否是同一件事？能否只转换语法而不合并模块？",
        [("MDN JavaScript modules", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Modules")],
    ),
    "q0782": question(
        "protobuf 为什么通常比较紧凑、高效？它的性能优势有哪些边界？",
        "字段编号、wire type、schema 与实际序列化成本。",
        ["用字段编号代替字段名", "按类型进行二进制编码", "schema 支持生成解析代码", "性能和流式边界不能绝对化"],
        """protobuf 的优势来自紧凑编码和 schema 驱动的读写，但不能保证对所有数据、语言和实现都比 JSON 更快。

1. **减少重复信息**：消息用字段编号标识字段，不重复传输字段名或完整 schema。tag 仍包含 wire type，因此“没有字段名”不等于“没有任何类型信息”。
2. **按类型编码**：小整数常可用 Varint 节省字节；字符串、字节串和嵌套消息等携带长度。不同类型有不同编码，不能把所有值都理解成变长整数。
3. **利用已知 schema**：生成代码或运行时描述信息可以按字段编号和类型解析，减少反复识别字段名等工作；具体效率仍受实现、分配和数据分布影响。
4. **明确使用边界**：要比较真实数据上的编码大小、CPU 和分配开销，而不是只凭二进制格式判断。连续传多条消息时还需要长度前缀等 framing，因为 protobuf 消息本身不自带整条消息的结束边界。

这些因素解释的是序列化格式的成本，不等于 gRPC 的流式 RPC 能力，也不表示超大消息一定可以低内存逐字段消费。""",
        "wire type 能否区分 string、bytes 和嵌套消息？为什么仍需要 schema？",
        [("Protobuf Encoding", "https://protobuf.dev/programming-guides/encoding/"),
         ("Protobuf Techniques", "https://protobuf.dev/programming-guides/techniques/")],
    ),
    "q0761": question(
        "HTTP 和 HTTPS 有什么区别？",
        "传输安全、身份校验和常见部署差异，不展开 TLS 握手细节。",
        ["HTTPS 为 HTTP 提供安全传输", "区分机密性、完整性与身份认证", "端口与证书是部署约定", "限定传输版本和安全边界"],
        """HTTPS 是通过安全传输使用 HTTP。通常说“HTTP 与 HTTPS 的区别”，是在比较明文 HTTP 与受 TLS 保护的 HTTP。

1. **机密性与完整性**：明文流量可被路径上的攻击者读取或篡改；HTTPS 加密并认证传输数据。
2. **服务端身份**：浏览器通常结合受信任证书链和域名验证对端身份。证书不证明网站内容真实，也不能防止用户主动访问相似域名的钓鱼站。
3. **常见部署**：URL 的默认端口分别是 80、443，但端口号不是安全保证。HTTPS 需要正确配置证书和安全协议。
4. **协议边界**：HTTP/1.1、HTTP/2 常以 TCP 承载，HTTPS 在其上使用 TLS；HTTP/3 使用 QUIC，不能把所有 HTTPS 都写成 TCP 上额外一层握手。

HTTPS 保护的是通信过程，不会自动修复服务端漏洞、恶意脚本或错误权限配置。握手消息与 0-RTT 风险属于 TLS 专题。""",
        "浏览器显示 HTTPS，是否代表这个网站的业务内容一定可信？",
        [("RFC 9110 HTTPS URI scheme", "https://www.rfc-editor.org/rfc/rfc9110.html#section-4.2.2"),
         ("RFC 9114 HTTP/3", "https://www.rfc-editor.org/rfc/rfc9114.html")],
    ),
    "q2834": question(
        "TLS 1.3 的证书握手如何建立安全连接？0-RTT 为什么需要额外防重放？",
        "TLS 1.3 密钥协商、身份认证、握手校验与早期数据的例外。",
        ["说明典型 1-RTT 证书握手", "区分密钥协商与签名认证", "理解 Finished", "限定 0-RTT 的使用"],
        """以下讨论典型的、无 HelloRetryRequest 的 TLS 1.3 证书认证完整握手，不混用 TLS 1.2 的消息顺序。

1. **协商密钥**：ClientHello 提供版本、算法和 key share；ServerHello 确定参数并返回服务端 key share。双方通过临时 (EC)DHE 与密钥派生得到握手密钥，而不是让服务端证书公钥直接加密业务数据。
2. **验证身份**：服务端发送加密的 EncryptedExtensions、Certificate 和 CertificateVerify 等消息。客户端检查证书链、域名等，并验证对握手上下文的签名。
3. **确认握手完整性**：双方用 Finished 验证协商记录与派生密钥，随后使用应用流量密钥保护数据。完整握手通常为 1-RTT；重试等情况会增加往返。
4. **单独看 0-RTT**：恢复会话时可用已有 PSK 派生早期密钥并提前发送数据，但早期数据没有与普通握手后数据相同的前向安全及跨连接防重放保证。服务端可以拒绝早期数据；应用不能仅依赖 TLS 防止重复执行，应限制允许的操作并处理重放与重试。

TLS 1.3 还支持 PSK 相关模式，不能概括为“所有模式都只用 ECDHE”。证书握手、会话恢复和早期数据的安全性质需要分别说明。""",
        "为什么支付或其他有副作用的操作不能不加约束地放进 0-RTT？",
        [("RFC 8446 TLS 1.3", "https://www.rfc-editor.org/rfc/rfc8446.html")],
    ),
    "q0397": question(
        "Redis 字典如何扩容、缩容，并通过渐进式 rehash 迁移数据？",
        "扩缩容目标不同，但共用迁移机制；具体阈值依版本和运行状态变化。",
        ["扩容缓解碰撞、缩容回收空桶", "准备新表并分批迁移", "迁移期间维护双表读写", "阈值与维护策略按版本核对"],
        """以 Redis 7.2 的字典实现为例，扩容和缩容都涉及换表与 rehash，区别主要是何时触发、目标容量多大。

1. **容量目标**：扩容增加桶数以降低负载和碰撞；缩容在元素较少时回收空桶空间。容量按实现规则取合适的 2 的幂，不能只根据旧表容量把所有版本的目标都写死。
2. **渐进式迁移**：分配新表后，通过 rehash 进度逐批迁移旧表中的桶，而不是一次搬完所有元素，降低长时间阻塞的风险。
3. **双表期间的操作**：查找与删除需要考虑两个表，新增通常写入新表。部分字典操作以及数据库字典的定时维护可推进迁移；暂停 rehash 等状态会影响进度。
4. **迁移完成**：释放旧表，让新表成为正常使用的表，再清理迁移状态。

扩缩容触发阈值、fork 子进程期间的 resize 策略和迁移预算应结合版本核对。渐进式分摊了整体成本，但单个桶较长时仍可能带来延迟，不能保证每一步严格常数时间。""",
        "为什么缩容与扩容需要不同的触发条件，以避免反复换表？",
        [("Redis 7.2 dict.c", "https://raw.githubusercontent.com/redis/redis/7.2/src/dict.c")],
    ),
    "q3683": question(
        "RunnableSequence 如何串联 LangChain Runnable？使用时有哪些边界？",
        "输入输出衔接与组合接口，不重复泛化为 Agent 架构。",
        ["顺序衔接各步输入输出", "用管道符组合", "支持调用/批处理/流式接口", "类型和流式兼容性仍需检查"],
        """RunnableSequence 把多个 Runnable 按顺序组合：前一步的输出作为后一步的输入，最后一步的输出作为整个序列的结果。

1. **定义顺序**：常见写法是 `prompt | model | parser`，表示提示模板、模型调用、结果解析三个步骤。序列对外仍是 Runnable。
2. **调用方式**：可以使用 invoke/ainvoke，也可以使用 batch 或 stream 等组合接口；每一步都必须能接收前一步产生的数据。
3. **流式边界**：整体暴露 stream 接口，不代表每个组件都能逐块处理。若中间步骤需要先收集完整输入，下游首块输出仍可能被阻塞。
4. **适用范围**：适合步骤顺序明确的处理链。组合器不会自动修复不兼容的数据结构，也不会仅因包含模型调用就变成自主规划 Agent。

回答重点是“如何串联和哪里需要检查”，不是再逐项复述 Runnable 的全部实现细节。""",
        "某一步必须等待完整输入，如何影响整条链的流式延迟？",
        [("LangChain RunnableSequence source", "https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/runnables/base.py")],
    ),
    "q2437": question(
        "rem 与 vw、vh 分别以什么为基准，应该怎样选择？",
        "根字号与视口尺寸两种参照系，以及缩放和动态视口的边界。",
        ["rem 参照根字号", "vw/vh 参照视口", "按字号缩放或视口布局选型", "注意移动浏览器视口变化"],
        """三种单位的关键区别是参照系，而不是谁能“自动适配所有屏幕”。

1. **rem**：通常相对于根元素 html 的计算字号。根字号为 16px 时，1.5rem 为 24px；根字号变化后，rem 尺寸随之变化，适合文字相关的间距和可缩放尺寸。1rem 并不恒等于 16px。
2. **vw、vh**：分别按视口宽、高的百分比计算。50vw 表示视口宽度的一半，适合直接依赖屏幕空间的布局，而不是随父元素宽度计算。
3. **选择方式**：需要跟随根字号缩放的内容优先考虑 rem；明确依赖视口比例的尺寸使用视口单位。也可用 clamp 等设置上下限，避免窄屏过小或宽屏无限放大。
4. **移动端边界**：浏览器工具栏会改变可见区域，100vh 不一定等于当前可见高度。需要区分小、大、动态视口单位，按布局目标选择 svh、lvh 或 dvh。

用 JavaScript 或 vw 改根字号是一种设计方案，不是 rem 本身会监听屏幕；也不能假定浏览器默认字号永远不变。""",
        "用户增大默认字号时，固定 px 根字号和继承用户字号的方案有什么区别？",
        [("MDN CSS length", "https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Values/length")],
    ),
    "q0860": question(
        "用燃烧速度不均匀的一小时绳，如何标记 15 分钟区间并计时 75 分钟？",
        "用点火和烧尽事件标记时间，明确 15 分钟允许预先准备。",
        ["说明理想燃烧假设", "两头烧得到 30 分钟", "再点第二根另一端得到 15 分钟区间", "增加一根两头烧得到总计 75 分钟"],
        """设有足够多根绳，每根从一端点燃到烧尽均需 60 分钟，沿绳燃速不均匀；采用经典题目的理想假设，两端同时燃烧不改变各段自身的燃烧性质。不能靠量长度切出固定分钟数。

**标记一个 15 分钟区间：允许先准备 30 分钟**

1. t=0 时，绳 A 两端同时点燃，绳 B 只点燃一端。
2. A 烧尽时是 t=30。此刻开始计目标区间，并点燃 B 的另一端。
3. B 剩余的单端燃烧时间为 30 分钟，两端一起烧只需 15 分钟，因此 B 烧尽是 t=45。

所标记的是 t=30 到 t=45，不是从第一次点火起的前 15 分钟。若题目要求 t=0 就开始目标计时，这个方案不满足该限制。

**从第一次点火起计时 75 分钟**

B 在 t=45 烧尽时，再把未使用的绳 C 两端同时点燃；C 用 30 分钟烧尽，此刻总计 75 分钟。两种问法共享同一组点火事件，不需要作为两道重复题分别背诵。""",
        "为什么“两头烧减半”不等于“把绳长切半就能计时半小时”？",
    ),
    "q2697": question(
        "如何实现前端列表项的上下拖拽排序，并保持视图与数据顺序一致？",
        "拖拽位置判断、数组移动、稳定 key 和顺序持久化。",
        ["记录被拖动项的稳定 ID", "根据目标位置计算插入点", "移动数据项并更新视图", "保存顺序并处理失败"],
        """拖拽排序应以数据数组的顺序为准，不只交换 DOM 或设置 CSS order。

1. **开始拖拽**：记录被拖动项的稳定 ID；渲染时也用稳定 ID 作 key，避免排序后组件状态错位。
2. **确定插入点**：根据指针与目标项的位置判断插到前面还是后面，可用占位符和位移预览。原生 HTML 拖放通常需要在 dragover 中阻止默认行为，才能接受 drop。
3. **提交数组移动**：从原位置移除元素，再插到目标位置，正确处理移除后索引变化。React 等状态管理场景创建新数组并更新状态；其余项保持相对顺序，而不是简单交换两项。
4. **持久化与兼容**：向后端保存 ID 顺序或排序字段，失败时恢复或提示重试。触摸与键盘操作需要另外设计，不能假定鼠标拖放天然覆盖所有设备。

已有拖拽库可负责手势和动画，但业务仍应负责数据更新、权限和保存结果。""",
        "为什么只修改 DOM 顺序，下一次框架渲染后可能恢复原状？",
        [("MDN Drag and Drop API", "https://developer.mozilla.org/en-US/docs/Web/API/HTML_Drag_and_Drop_API")],
    ),
    "q1965": question(
        "如何为固定工作流添加条件分支，而不把所有路径交给 Agent？",
        "显式分支与受限动态决策的职责划分。",
        ["将路由条件写成可测试规则", "限定每个分支的输入输出", "只对不确定子任务开放动态决策", "记录并验证实际路径"],
        """固定工作流不等于“所有输入只能走同一条链”。代码或配置完全可以预先定义条件分支、循环和失败回退。

1. **显式路由**：按已知条件选择分支，例如输入是否完整、是否需要查询受保护数据、缓存是否命中。规则清楚时，不必让模型猜测下一步。
2. **约束分支**：为各分支规定输入输出、权限、超时和错误处理；重试次数也由流程约束，避免形成无界循环。
3. **局部动态决策**：若某个子任务确实需要根据观察临时选择行动，可将它封装成有预算、有工具白名单的 Agent 节点。主流程继续负责入口、审批和结果校验。
4. **验证路由效果**：记录选择了哪个分支、耗时和失败原因，用代表性输入回归，判断分支是否减少无效处理。

关键是把确定性规则和不确定决策分别放在适合的层，而不是在“完全写死”和“全部自主”之间二选一。""",
        "模型参与分类路由时，怎样处理低置信度或不合法的路由输出？",
        [("Anthropic Building effective agents", "https://www.anthropic.com/engineering/building-effective-agents")],
    ),
    "q1647": question(
        "如何用 Python 的阻塞式标准输入实现一个可正常退出的终端聊天循环？",
        "input 读取、输出刷新、EOF/中断处理和并发边界。",
        ["每次读取一行", "过滤空输入并处理退出命令", "处理 EOF 与 KeyboardInterrupt", "不要把单线程阻塞等同于不能流式输出"],
        """最小循环是读取一行、处理消息、打印回复，再等待下一行。下面用回显代替模型调用，只演示终端交互与退出控制。

```python
def chat():
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\\n已退出", flush=True)
            break
        if text.lower() in {"exit", "quit"}:
            break
        if not text:
            continue
        reply = f"收到：{text}"
        print(reply, flush=True)

chat()
```

1. **阻塞范围**：input 等待输入时会阻塞当前执行线程，这个简单循环不会同时执行下一轮处理；不代表整个多线程进程都不能做其他工作。
2. **退出与异常**：input 遇到 EOF 抛 EOFError，用户中断可能抛 KeyboardInterrupt；明确处理即可避免反复重试退出事件。
3. **输出刷新**：输出重定向或需要逐块显示时应考虑缓冲。处理阶段可以逐块输出并 flush，阻塞式输入本身不禁止流式回复；若等待输入时也要接收异步推送，再引入独立输入线程或事件循环。

此例限定 Python input；不能把 Node.js readline 等异步接口统一描述成同步阻塞读取。""",
        "如果等待用户输入时也要显示服务端推送，应该怎样拆分输入与输出任务？",
        [("Python input", "https://docs.python.org/3/library/functions.html#input")],
    ),
}

TITLE_REWRITES = {qid: item["title"] for qid, item in OVERRIDES.items()}

# Repair already persisted first-space splits; the safer formatter prevents new
# ones but cannot infer the original title from an arbitrary existing paragraph.
HEADING_REPAIRS = {
    "q2832": [("**二、CSRF**\n\n防御手段", "**二、CSRF 防御手段**")],
    "q1894": [("**二、async**\n\n函数里 throw error 的捕获：", "**二、async 函数里 throw error 的捕获：**")],
    "q3151": [("**一、Promise**\n\n原理", "**一、Promise 原理**"),
              ("**二、EventEmitter**\n\n原理", "**二、EventEmitter 原理**")],
    "q3136": [("**四、为什么**\n\nChatGPT 用 SSE", "**四、为什么 ChatGPT 用 SSE**")],
    "q3705": [("**一、训练不收敛的排查顺序（先便宜后昂贵）**\n\n：", "**一、训练不收敛的排查顺序（先便宜后昂贵）：**")],
    "q1903": [("**二、常见瓶颈与对应手段(按四段归因)**\n\n：", "**二、常见瓶颈与对应手段(按四段归因)：**")],
    "q3483": [("**二、归因：**\n\n效果差在哪", "**二、归因：效果差在哪**")],
}
