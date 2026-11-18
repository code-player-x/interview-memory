# 项目与题库复查记录（2026-09-26）

> 本文保留修复前的审查快照；用户确认后，已完成下列问题的修复。当前结果、数据库备份及验收范围见[修复记录](/Users/didi/aiStudy/interview-memory/docs/project-fixes-2026-09-26.md)。下方数量和“未修复”描述不代表当前状态。

## 结论与范围

当前基本流程能跑通，但尚未达到“回答正确、每题独立、题间少重复”的验收标准。最先需要处理的是网页数据与源题库不一致、代码块渲染破坏，以及明确的题答错误。

本轮是审查：未修改业务代码、题库内容或正式数据库，未合并删题，未提交或推送。仅新增本报告。检查对象包含进入本轮前已有的未提交修改，不只检查 Git HEAD。

全量检查覆盖 26 个领域、2,586 道源题的结构、唯一性、生成文件对应关系与数据同步；语义审查采用全库候选扫描后人工复核高风险题与重复候选，**不等于逐句查证了全部 2,586 道答案**。下面只列有代码复现、明确原文或权威资料支持的发现。

## 1. 网页数据不同步：优先级 P1

只读检查正式 SQLite 数据库，结果如下：

| 项目 | 数量 |
| --- | ---: |
| authored 源题库 | 2,586 道 / 26 个领域 |
| 网页数据库 | 2,637 道 / 25 个分类 |
| 按完整标题精确匹配的题 | 2,257 道 |
| 同标题但答案文本不同 | 823 道 |
| 仅数据库存在的标题 | 380 个 |
| 仅源题库存在的标题 | 329 个 |

823 是答案文本差异数，并非 823 道错误答案；标题单侧存在也可能来自改名，不能直接据此删题。但数据库确实保留了源题库已修改的旧内容和上下文不完整的旧题，例如“个岗位分别是什么？”、“学习本项目你将获得什么？”等。因此，仅修改 Markdown/JSONL，不会自动改善网页里正在背的题。

代码原因：[import_questions_v2.py:156](/Users/didi/aiStudy/interview-memory/scripts/import_questions_v2.py:156) 默认只插入新标题，已有标题直接跳过，不更新答案；改名后的题则会作为新增，旧题保留。`--replace` 会删除并重建 questions_v2 批次，且存在学习记录关联时拒绝执行，不是通用的保留进度同步方案。

建议：先确认源题库修正完成，再备份并同步。已有学习记录时，应以稳定源 ID 建立映射、原位更新，单独处理改名/合并/移除，不能用总题数差值决定删除。虽然本次只读快照中相关学习记录表为空，仍应在实际同步前重新检查。

## 2. 已复现的代码与脚本问题

### C1 · P1：已有围栏代码块会被再次包裹，显示和复制内容不完整

位置：[frontend/app.js:188](/Users/didi/aiStudy/interview-memory/frontend/app.js:188)、[调用顺序:419](/Users/didi/aiStudy/interview-memory/frontend/app.js:419)。

`_wrapIndentedCode` 不识别当前是否在已有代码围栏内，会把其中连续缩进行重新包成围栏。用下面这段完整 Python 代码调用当前 `renderMarkdown`：

```python
def f():
    x = 1
    return x
```

实际生成的 `<code>` 和复制按钮数据只有 `def f():`，函数体变成普通段落，末尾出现多余反引号。扫描真实题库，45 道答案的已有围栏会被该函数再次修改，不只是构造样例。

修复方向：先保护已有围栏，启发式补围栏只作用于围栏外；补充完整代码文本、复制内容、多个代码块和嵌套缩进的回归测试。

受影响题号：q1514、q2439、q2443、q2547、q2575、q2817、q3359、q3382、q0240、q0241、q0242、q0243、q0246、q0253、q0254、q0260、q0273、q0274、q0282、q0284、q0305、q0307、q0313、q0317、q0322、q0345、q0330、q0600、q0364、q3580、q0184、q0209、q1986、q0476、q0323、q0359、q0365、q0724、q2801、q3303、q2999、q3856、q5005、q5037、q5052。

### C2 · P2：空白答卷被当成“题目不存在”，参考答案也丢失

位置：[backend/app.py:1100](/Users/didi/aiStudy/interview-memory/backend/app.py:1100)。

临时库创建有效题目后，向 `/api/quiz/submit` 提交 `user_answer: " "`，得到 `question_missing`、解释“题目不存在”、空参考答案。原因是 `_one` 把空回答和查不到题目都返回为 `q=None`，后面的“未作答”分支无法到达。

修复方向：区分不存在与未作答；空回答仍返回题目对象和参考答案，不写入作答/错题统计。

### C3 · P2：随机练习新一轮可能立即重复上一题

位置：[backend/app.py:1042](/Users/didi/aiStudy/interview-memory/backend/app.py:1042)。

临时库只有 ID 1、2 两题，按顺序已看 `2,1`，新一轮返回的必然是 1，与上一题相同。当前排除的是 `max(seen_in_filter)`，不是最近一题。

修复方向：显式传递最近题 ID，或保留输入序列的最后有效 ID；补覆盖两题及非升序完成一轮的测试。

### C4 · P2：判题服务返回错误字段类型时，作答接口返回 500

位置：[backend/judge.py:97](/Users/didi/aiStudy/interview-memory/backend/judge.py:97)、[Agent 分支:130](/Users/didi/aiStudy/interview-memory/backend/judge.py:130)。

模拟 Agent 返回 `{"is_correct":true,"explanation":{"not":"text"},"error_reason":""}`，有效题目的 `/api/answer` 实测返回 `500 Internal Server Error`。适配器只校验布尔值，其余字段直接传给数据库；异常发生在判题函数的兜底之外。

修复方向：在 Agent/LLM 适配器统一校验响应结构与文本字段，不合格结果进入 pending；保证整卷和单题均不会因一条异常响应失败。

### C5 · P2：嵌入实验把全零或 NaN 向量误判为“有区分度”

位置：[test_embed_discriminative.py:35](/Users/didi/aiStudy/interview-memory/crawler/scripts/test_embed_discriminative.py:35)。

离线替换 `embed` 返回值，分别让全部 17 个向量为 `[0,0]`、`[NaN,1]`，两种情况都输出 `OK 该模型对短中文有区分度。`，正常退出。零范数被替换为 1；NaN 与阈值比较全部为假，危险对计数为零。

修复方向：计算余弦前校验返回数量、维度一致性、数值有限性与非零范数；异常必须失败。现有两个测试仅覆盖正交向量和相同非零向量。即使校验通过，17 条短文本也只能作为冒烟检查，不能代替去重任务的正负样本准确率评估。

### C6 · P2：批量导入同一批内的重复题不会去重

位置：[backend/app.py:1683](/Users/didi/aiStudy/interview-memory/backend/app.py:1683)；文件批量导入的同类逻辑在 [785](/Users/didi/aiStudy/interview-memory/backend/app.py:785)。

向 `/api/questions/import-json` 同时提交两份完全相同题目，实测 `imported=2, skipped=0`，查询数据库确有两条。Session 配置 `autoflush=False`，第二次查重看不到尚未 flush 的第一条新增记录。

修复方向：维护批次内已见标题集合，并与数据库已有标题合并查重；两个批量入口都要覆盖同批重复、跨批重复和空标题。

### C7 · P2：已掌握题反馈“忘记”后，复习状态与错题掌握状态不一致

位置：[backend/app.py:1486](/Users/didi/aiStudy/interview-memory/backend/app.py:1486)。

临时库中已掌握题提交 `remembered=false`，复习计划回到 `stage=1, status=pending`，但错题条目的 `mastery` 仍是 `mastered`。当前条件显式跳过了已掌握条目的状态更新，导致待复习与错题筛选口径不同。

修复方向：忘记时同步恢复 reviewing；如果产品不允许已完成计划再反馈，应显式拒绝，不能部分更新。

### C8 · P2：待办/专注接口接受无效业务数据

位置：[backend/todo_routes.py:20](/Users/didi/aiStudy/interview-memory/backend/todo_routes.py:20)、[日期解析:37](/Users/didi/aiStudy/interview-memory/backend/todo_routes.py:37)、[专注开始:133](/Users/didi/aiStudy/interview-memory/backend/todo_routes.py:133)。

临时库直接 API 复现：空标题、`priority=-10`、无效日期 `2026-99-99` 返回 200，前两项被保存，日期被静默清空；`focus/start?minutes=-25` 返回 200 并保存负计划时长。这是后端校验缺失，不代表 UI 常规操作一定会生成这些输入。

修复方向：统一 trim 后非空校验、优先级/分钟数范围限制，无效日期返回明确 4xx，更新接口同样校验。

### C9 · P2：答案排版器用第一个空格切标题，破坏完整标题

位置：[answer_structure.py:160](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/answer_structure.py:160)。

q2834 的“一、HTTP 与 HTTPS 的区别”被拆成粗体“一、HTTP”和单独正文“与 HTTPS 的区别”；“二、HTTPS 的好处”等同样被拆开。将 Git HEAD 中原答案传入当前排版器，可以复现当前源题的这个结果。文本未丢失，但破坏了用户希望的清晰层级。

修复方向：空格不能作为标题结束的充分依据；保留完整短标题，无法可靠判断时保持原段落；补充含英文词与空格的中文标题回归测试。

## 3. 已确认的题目内容问题

### Q1 · q2061：可选链调用解释存在两处错误

位置：[frontend.md:6287](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/frontend.md:6287)。题面只是 `onOpen?.()`，也缺少明确提问。

答案声称“不是函数也静默返回 undefined”，且声称 `obj.method?.()` 在 `obj` 为 null 时也不报错。实测 `onOpen=42; onOpen?.()`、`obj=null; obj.method?.()` 均抛出 TypeError。可选调用只对 null/undefined 短路，不验证值是否可调用；对象本身可空时需要 `obj?.method?.()`。[MDN 可选链](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/Optional_chaining)

建议题面改为“可选调用 `onOpen?.()` 在什么情况下短路，什么情况下仍会报错？”，答案只解释该语法与边界。

### Q2 · q3108：推理服务问题用训练优化作答

位置：[llm-basics.md:5655](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/llm-basics.md:5655)。

题面问“大模型服务吞吐不足时，如何优化批处理、并行度与调度？”，答案主干却是 DDP/FSDP、梯度累积、优化器状态、反向 AllReduce、训练收敛和训练 7B 的例子。PyTorch 对 DDP 的说明也明确围绕分布式训练和梯度同步。[PyTorch DDP](https://docs.pytorch.org/docs/main/generated/torch.nn.parallel.DistributedDataParallel.html)

建议按题面重写为推理服务的负载测量、批处理、KV cache、prefill/decode、并行与延迟约束；训练优化另归训练题，避免两类问题混讲。

### Q3 · q0940：题目已改成 EndpointSlice，答案仍只讲 Endpoints

位置：[engineering.md:1559](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/engineering.md:1559)。

答案通篇 endpoint 资源列表、endpoint controller，没有回答题目中的 EndpointSlice。应说明控制器维护端点切片、数据平面消费 Service/EndpointSlice 信息，再转发流量，区分资源管理和实际转发。[Kubernetes EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)

### Q4 · q2483：把 Teleport 和未编译动态 DOM 混为一谈

位置：[frontend.md:11034](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/frontend.md:11034)。

答案称 Teleport 到 body 的弹窗没有 data-v 属性，因此 scoped 样式不生效。这一概括错误。根据 scoped 的编译机制与 Teleport 的 DOM 移动行为，不能推导出移动时作用域属性消失；实际需要区别“作用域属性”与“依赖原祖先关系的选择器”。`v-html`、手动创建 DOM、Teleport 应分开解释。[Vue scoped CSS](https://vuejs.org/api/sfc-css-features)、[Vue Teleport](https://vuejs.org/guide/built-ins/teleport.html)

### Q5 · q2409：“前端源码不能直接跑浏览器”过度绝对化

位置：[frontend.md:702](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/frontend.md:702)。

原生 HTML/CSS/JavaScript 和浏览器支持的 ESM 可以直接运行；TS、JSX、SFC 等通常需要转换。应把“目标浏览器兼容性、性能和工程化的需要”与“所有前端必须构建”区分开。本项目的原生前端也是直接反例。[MDN JavaScript modules](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Modules)

### Q6 · q0782：protobuf 的类型信息与流式边界表述不严谨

位置：[os-network.md:7854](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/os-network.md:7854)。

应区分“不带字段名及完整 schema 类型”与“tag 包含 wire type”，不能笼统说没有类型信息。流式处理还需区分读取单条消息与连续多条消息；后者必须由外层界定消息边界，protobuf wire format 不会自行提供整条消息的分界。[官方编码说明](https://protobuf.dev/programming-guides/encoding/)、[官方多消息流说明](https://protobuf.dev/programming-guides/techniques/)

### Q7 · q2834：HTTP/TLS 版本边界与安全保证混讲

位置：[os-network.md:9504](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/os-network.md:9504)。

将 HTTP/HTTPS 一概写成 TCP 协议栈，未限定 HTTP/1.1、HTTP/2，与 HTTP/3 使用 QUIC 不符。介绍 TLS 1.3 0-RTT 后又笼统承诺防重放，缺少早期数据的重放风险说明。应按版本区分，不要把普通握手后的数据保证无条件套到 0-RTT 上。[RFC 9114](https://www.rfc-editor.org/rfc/rfc9114.html)、[RFC 8446](https://www.rfc-editor.org/rfc/rfc8446.html)

## 4. 需要收敛的重复内容

标题字符 3-gram 相似度扫描得到 65 对候选（阈值 0.40），再对候选阅读核实。相似度只用于发现线索，不作为自动删题依据。以下五组确认有明显共用主干：

| 题号与位置 | 重复内容 | 建议边界 |
| --- | --- | --- |
| q0397 / q0398：[Redis 扩缩容](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/redis.md:839) | 渐进式 rehash 的绝大部分回答相同，仅新表大小不同 | 合并为扩缩容触发条件与过程；若保留两题，各自主讲触发条件，公共过程不再重复铺开 |
| q3683 / q3684：[定义](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/agent.md:12206)、[特点](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/agent.md:10312) | LCEL 串联、管道符、invoke/batch/stream、工厂流水线类比均重复 | 合并为定义/使用题；另一题只有改成独立的流式传播或错误处理问题才有保留价值 |
| q3288 / q2437：[rem 基础](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/frontend.md:12782)、[rem 与 vw/vh](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/frontend.md:5197) | 根字号、16px/10px 换算、移动端适配重复展开 | 统一单位基础；比较题只讲参照基准、缩放和选型差异 |
| q0761 / q2834：[HTTP/HTTPS](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/authored/os-network.jsonl:59)、[综合题](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/os-network.md:9504) | 安全性、端口、证书、握手重复 | q0761 保留基本区别；另一题聚焦指定 TLS 版本的握手和安全边界 |
| q0860 / q0861：[烧绳计时](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/puzzle.md:293) | 同一个 30+15 分钟过程，后一题再加 30 分钟 | 做成一道母题及追问；15 分钟题必须明确是否允许预先燃烧 30 分钟 |

不存在完全相同标题/答案，不等于不存在这些语义重复。建议按知识点边界收敛，而不是简单缩短答案后保留所有题目。

## 5. 仍有依赖缺失上下文的题面

- q2697：[“可以上下进行移动，这个过程你如何实现的？”](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/frontend.md:11699)：未说明移动什么，输入与限制是什么。
- q1965：[“前面提到的大多数方法都是预定义好的 pipeline……”](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/agent.md:8551)：依赖不存在的前文，问句本身没有明确任务。
- q1647：[“交互采用终端聊天……具体代码如下？”](/Users/didi/aiStudy/interview-memory/crawler/questions_v2/full_v2/agent.md:9036)：文章过渡句，不是自包含问题。
- q3684、q2061 的题面问题已在前文合并记录，不重复计数。

## 6. 通过的检查与验证边界

已通过：

- `.venv/bin/python -m pytest -q`：58 passed。
- `.venv/bin/python verify_flows.py`：31 通过，0 失败。
- 前台/后台 JavaScript `node --check`、后端及脚本 Python 编译检查。
- 题库导入 dry-run：2,586 道校验通过；依赖 `pip check` 无损坏项。
- 全量源题 ID、标题唯一；必要字段非空；去空白后的完全相同答案未检出。
- JSONL 与生成 Markdown 的题目 ID、顺序一致；当前清洗函数重跑幂等。
- 正式 SQLite `PRAGMA quick_check` 返回 ok；正式数据库本轮只读。
- 未发现长度超过 600 字符且完全没有换行的源答案。但有换行不代表层级合理，C9 就是反例。

新增复现均使用临时数据库、Node 内存执行或离线模拟响应，没有向正式题库插入测试题。

尚不能据此宣称通过的部分：

- 全部答案逐句语义正确、全部潜在语义重复已消除。
- 真正的嵌入模型质量评估：NumPy 已安装，但 Ollama 服务/模型尚不可用；离线逻辑测试不能替代真实模型实验。
- 真实 SMTP、外部 Agent/LLM、对象存储服务联调；相关测试中的模拟/降级分支不代表外部服务实际可用。
- 不同数据库/容器部署组合、完整安全审计与性能压测。
- 本轮未做所有页面、所有设备尺寸的浏览器逐项验收；渲染缺陷采用当前前端函数和真实题库输入验证。

## 7. 推荐处理顺序

1. 修复 C1 代码渲染、C9 标题拆分，补反例测试；防止后续整理内容再次被显示层破坏。
2. 修正 Q1—Q7，处理缺失上下文题面，按第四节收敛重复边界；统一从 authored 生成 full_v2。
3. 修复判题、导入、练习/复习状态及实验脚本的异常输入处理，补当前 58 项测试缺失的反例。
4. 完成备份和学习记录检查后，再把确认过的源题库同步到网页数据库。
5. 重跑测试，并用浏览器验收代码复制、未答复盘、新一轮抽题、遗忘状态、分类与题目总数；最后单独完成真实模型实验。

本报告是下一轮修复清单，不是修复完成证明。
