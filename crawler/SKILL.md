---
name: agent-mianshi-harvester
description: >
  自动采集互联网上的「Agent 开发」面试经验（面经）与手撕题目（含登录墙站点），分类后先与飞书知识库做
  去重（本地语义镜像 + difflib 0.85 判重），未命中的题目由 LLM 引用权威来源生成答案并上传飞书，
  并支持每天 09:00 经 QQ 邮箱推送 5 道面试题用于日常学习。
  已固化「一键增量」：scripts/harvest.py 统一调度多源采集（小红书/掘金/V2EX/脉脉/牛客/知乎）+ 抽取去重。
  触发词：爬 agent 面经 / 抓取 agent 开发面试题 / 收集 agent 手撕题目 / 整理 agent 面试题库 /
  更新我的 agent 面经知识库 / 每天给我推面试题 / 我的 agent 面试题库还缺哪些 / 扩源采集 / 一键增量。
agent_created: true
version: 1.0.0
status: active
---

# Agent 面经收割机（v1.0）

把"网上面经 → 飞书知识库（去重+入库）→ 每天推题学习"串成一条可全自动重复跑的流水线。

## 用户画像（写死，触发即带入上下文）
- 当前：Go 后端开发，做国际化外卖业务。
- 目标：明年年初跳槽做 **Agent 开发**；自述 Agent 相关知识较少。
- 因此：分类保留「后端八股(Go)」**单独成类**（Agent 岗仍会深挖后端），答案优先引用权威来源、标注出处。

## 何时使用
- 用户想批量采集 Agent 开发相关的面经 / 手撕题目（含牛客深度帖、小红书等登录墙源）。
- 用户想维护一个**去重过**的 Agent 面试题库（飞书知识库）。
- 用户想每天收到 5 道面试题 + 答案做日常积累（QQ 邮箱，09:00；**仅技术类**：排除手撕算法/行为与HR）。

## 前置依赖（必须先启用/信任，否则流水线在飞书/邮箱步骤报错）
1. **lark-unified** skill（飞书/Lark 套件，含 Wiki/文档/表格）：负责飞书**读取（去重预筛）**与**写入（上传）**。
   - ✅ **已建好独立 Wiki 空间「Agent开发面试题库」**（space_id `7662025183418387409`），7 类分类节点 + 「每日推送归档」节点全部创建完成，节点 token 见下方「飞书知识库配置」。
   - ⚠️ 已核实：lark-unified 的 Wiki 搜索是**关键词/标题级，非语义检索**。本 skill 的语义去重因此**不依赖**它的搜索能力（见去重设计）。
2. **QQ 邮箱连接器**：每日推送通道。未启用则降级为 lark-unified 发飞书消息（仍可用，但用户已选 QQ 邮箱）。
3. 可选（含登录墙源时）：本机已登录的 Chrome + `chrome-remote-interface`，复用 zhipin-jd-scraper 的 CDP 方案（见 references/cdp.md）。

## 架构要点（务必理解）
- 本 skill 以 **SKILL.md 为编排大脑**：抓取、分类、答题、飞书读写、每日推送大多由**智能体直接调用工具**完成。
- `scripts/` 只承担**本地结构化辅助**：题库 JSON 管理（bank.py）、相似度计算（dedup.py / process_source.py 内联 difflib）、
  每日抽题+HTML 邮件（prepare_daily_email.py —— **5 题生产版，自动化实际调用**；daily.py 为早期 3 题变体）、
  一键增量调度（harvest.py）、通用后处理（process_source.py）、CDP 抓取核心（cdp_helper.py）。
- 飞书 I/O **必须通过 lark-unified 的工具**完成（脚本不能直接调飞书 API），所以"上传/检索飞书"是智能体动作，不是脚本。

## 飞书知识库配置（已建好，上传时按此映射父节点）
- 空间名：**Agent开发面试题库** ｜ space_id：`7662025183418387409` ｜ 根父节点 token：`CAXbwAwlwiXsDjkmsATc1G1UnMc`
- 分类 → 父节点 node_token 映射（每条题目上传到对应分类节点下，新建 docx 子节点）：
  | 分类 | node_token | 链接 |
  |---|---|---|
  | 概念基础 | `Ppt4wthCZidFYNkxVrucMidfnQe` | https://my.feishu.cn/wiki/Ppt4wthCZidFYNkxVrucMidfnQe |
  | 架构设计 | `PpW5w4271iWXxAk7S5pc6DvFnse` | https://my.feishu.cn/wiki/PpW5w4271iWXxAk7S5pc6DvFnse |
  | 工程落地 | `UoDwwf2e8i7SNGkdi54cmjn0ngf` | https://my.feishu.cn/wiki/UoDwwf2e8i7SNGkdi54cmjn0ngf |
  | 手撕算法 | `MT5xwon14iWefkkYtBPcqyynnkQ` | https://my.feishu.cn/wiki/MT5xwon14iWefkkYtBPcqyynnkQ |
  | 项目深挖 | `IA4owjQtyizXM0kA74Xchif6nRb` | https://my.feishu.cn/wiki/IA4owjQtyizXM0kA74Xchif6nRb |
  | 后端八股（Go） | `KgREwgYrxi3cHUknvcMchwdSnSd` | https://my.feishu.cn/wiki/KgREwgYrxi3cHUknvcMchwdSnSd |
  | 行为与HR | `WIgNwsVUHiyg7ZkMBaacu6OFn8d` | https://my.feishu.cn/wiki/WIgNwsVUHiyg7ZkMBaacu6OFn8d |
  | 每日推送归档 | `DbO9wFcVhiintgkmJ2qcgbesnuV` | https://my.feishu.cn/wiki/DbO9wFcVhiintgkmJ2qcgbesnuV |
- 上传规则：用 `lark-cli wiki +node-create --parent-node-token <分类node_token> --title "<题面截断到40字>" --as user` 建子节点，再用 **lark-doc** 把「答案格式模板」正文写入该 docx。
- 同步：每次上传后必把 `wiki_node_token` / `wiki_url` 写回 `data/questions-bank.json`，保持本地镜像与飞书一致。
- 配置镜像文件：`data/wiki-config.json`（供 `bank.py` / `prepare_daily_email.py` / 智能体读取，避免 token 散落）。

## 两种模式

### 模式 A：增量采集 collect（全自动）

1. **定范围**：主题 = Agent 开发岗面经 + 手撕题目。来源见 references/sources.md（**公开源 + 登录墙源**都抓）。
2. **抓取**：
   - **一键增量（推荐）**：直接跑 `python scripts/harvest.py --source all`（或指定单源），它串行执行「采集 → 抽取去重 → 生成 shortlist/refined」。采集脚本清单见下方「多源一键增量」。
   - 登录墙 / 反爬源（小红书、脉脉、牛客）均走 **CDP 复用本机已登录 Chrome（端口 9222）**，全程只读 DOM、不存凭据；开放源（掘金）也走 CDP 复用 Chrome 出口——因为沙箱直连对部分站点（如 V2EX）超时、掘金搜索 API 被风控，经用户浏览器出口最稳。**微信公众号例外**：文章是公开页面，**免登录、免 CDP**，直接用标准库 HTTP 抓 `#js_content` 正文即可（见 `weixin_harvest.py`），再用文末「推荐阅读」链接做 BFS 滚雪球扩到该公众号全部面经。
   - **手撕识别规则**：含 LeetCode 题号 / 代码块 / "手撕" / "算法题"字样。
3. **归一化 + 分类**：解析为结构化条目（字段见 references/taxonomy.md），归入 7 类体系（见下）。
4. **去重（见"去重设计"）**：本地语义镜像比对 + lark-unified 关键词预筛 + LLM 判重。
   - 命中（相似度 ≥ 0.85） → 标记 `已有`，跳过；
   - [0.7, 0.85) → `待复核`（首批强制人工复核，之后按全自动直接判 `已有`）；
   - < 0.7 → 视为新题。
5. **生成答案**：对未命中题目，LLM **必须引用权威来源**（抓到的原文片段 + 官方文档/论文 + 补充），按「答案格式模板」输出简版/展开/加分点/雷区，并在末尾列出来源链接。
6. **格式化 + 上传飞书**：把条目先追加写进 `data/questions-bank.json`；再运行 `bash scripts/upload_feishu.sh`（它为尚未上传的题目生成 XML、按「飞书知识库配置」的对应分类父节点建子文档并写入答案正文，最后回写 `wiki_node_token/wiki_url`）。飞书 I/O 全部经 `lark-cli`（lark-unified）完成；Windows 下 python 子进程解析不到 Git Bash 版 lark-cli，故上传走 shell 脚本而非 python。
7. **本地镜像同步**：无论命中与否，都把条目追加进 `data/questions-bank.json`（与 frontend-interview-master 同构），`status` 标 `已有/新增/待复核`。**这是去重的权威本地副本**，飞书仅是展示/同步端。
8. **产出报告**：本次采集 N 题、新增 M 题、已有 K 题、待复核 P 题、分类分布，present_files 给用户（全自动模式下直接落库后给汇总，不阻塞）。

### 模式 A·多源一键增量（harvest.py）

所有采集脚本统一约定：`data/tmp/<source>/posts.jsonl`（append/resume 断点续传）+ `progress.json`（状态机 RUNNING / WAIT_VERIFY / NEED_VERIFY / DONE）。`harvest.py` 串行调度，复用同一 Chrome 标签，避免并行抢同一标签。

```bash
# 全源采集 + 后处理
python scripts/harvest.py --source all
# 单源
python scripts/harvest.py --source xiaohongshu   # 需已登录小红书
python scripts/harvest.py --source juejin        # 开放源，无需登录
python scripts/harvest.py --source v2ex          # 开放源；本机网络不可达时改用 WebFetch 兜底
python scripts/harvest.py --source maimai        # 需先在 Chrome 登录脉脉
python scripts/harvest.py --source nowcoder      # 需已登录牛客
python scripts/harvest.py --source zhihu         # 需先在 Chrome 登录知乎
# 只跑后处理（抽取+去重，产出 shortlist/refined 供挑题手写答案）
python scripts/harvest.py --source juejin --stage process
```

| 源 | 类型 | 采集脚本 | 关键坑（已踩过，复用即避） |
|---|---|---|---|
| 小红书 | 登录墙 | `xiaohongshu_harvest.py` | ① 详情页必须带 `xsec_token`（直接 `explore/{id}` 返回"页面不见了"空壳）；② 滑块验证页阻塞 JS 上下文致 `Runtime.evaluate` 超时 → 须把超时**保守判为验证**并自动轮询等用户滑掉 |
| 掘金 | 开放 | `juejin_harvest.py` | ① 搜索结果异步加载，须等 `a[href^='/post/']` 出现再收；② 正文容器 `.markdown-body`；③ 沙箱直连搜索 API 被风控，走 CDP |
| V2EX | 开放 | `v2ex_harvest.py` | **本机网络对 v2ex.com 直连超时**；WebFetch 可达但 V2EX 搜索功能失效（任意词返回无关节点）。换 V2EX 可达网络可用 CDP 脚本；否则 WebFetch 兜底（搜索不靠谱，需手动找 /go/jobs 帖子） |
| 脉脉 | 登录墙 | `maimai_harvest.py` | 强登录墙+风控，须先在 Chrome 登录脉脉；撞墙原地等登录/滑验证（最长 120s）后写 NEED_VERIFY |
| 牛客 | 登录墙 | `nowcoder_harvest.py` | 站内搜索 API（`gw-c.nowcoder.com/api/sparta/pc/search`，POST）取 `momentData.content` 片段 |
| 知乎 | 登录墙 | `zhihu_harvest.py` | ① 强登录墙+强反爬，须先在 Chrome 登录 zhihu.com，否则详情页只回"登录后查看"残缺正文被跳过；② 搜索/详情重 JS 渲染，撞"安全验证"页同小红书/V2EX 处理（`detect_block` 命中 `请先登录/扫码登录` 等关键词 → 原地轮询等滑掉，最长 300s）；③ 问题页会合并多个回答 `RichText` 取最长正文，文章页取主 `RichText` |
| 微信(面经哥等) | 公开(免登录) | `weixin_harvest.py` | **纯 HTTP 免 CDP**（公开页）；正文在 `#js_content`；噪声低（多为结构化问题清单），但仍需精选 |

> **⚠️ 微信"枚举某号全部文章"的实测限制（2026-07-16，重要）**
> - 微信公众号**无公开文章列表接口**；且实测面经哥**不放「推荐阅读」卡片、不建专辑**，所以 `weixin_harvest.py` 的 BFS 滚雪球**失效**（文末只有微信官方《名誉保护投诉指引》链接，已过滤）。
> - 改试**搜狗微信搜索**（`weixin.sogou.com`，脚本 `sogou_weixin_search.py`）按关键词搜面经哥文章——能搜到结果，但搜狗对 `link?url=` 跳转访问做了 **antispider 风控**：纯 HTTP 与 CDP 真实 Chrome（全新 profile）打开 `weixin.sogou.com/link?url=...` 转链都会被 302 到 `weixin.sogou.com/antispider/` 验证页，**自动还原真实链接失败**；脚本仅作"列标题+转链清单"用。
> - **可靠路径（推荐，用户已确认）**：用户在「自己的常用浏览器」（搜狗不拦）打开面经哥文章 → **直接复制地址栏链接丢给我**即可。实测发现：浏览器地址栏里的链接通常是 `mp.weixin.qq.com/s?src=11&timestamp=...&signature=...` 形式的**搜狗中转链接**——只要该 signature **新鲜（刚从浏览器复制）**，纯 HTTP 就能直接抓到完整正文（`weixin_harvest.py` 已兼容该形态，见下方）；若已过期则抓不到，需重新在浏览器打开复制。极少数情况地址栏会变成永久链接 `mp.weixin.qq.com/s/<ID>`，两种都支持。多条链接可一次给（每行一个）。
> - **去重已加固**：`weixin_harvest.py` 对微信文章按「公众号+标题」去重（跨 URL 形态一致），同一篇无论用中转链接还是永久链接、或不同中转 signature，都只落盘一次（2026-07-16 实测：用户给的中转链接解析为已入库的 73 题面经，被正确 SKIP）。

**共享核心**：`scripts/cdp_helper.py` 提供 `Browser` 类（connect / send / eval_js / navigate / wait_for_selector / detect_block / wait_verify_clear）与 `run_source(adapter, ...)` 通用驱动。新增源只需实现一个 adapter（`search_url` / `first_card_selector` / `card_js` / `note_url` / `note_js` / `content_selectors`），无需重写 CDP 逻辑——这是"扩展到更多源"的标准做法。

### 模式 A·掘金采集 SOP（已跑通，照抄即可）

掘金是**开放源但搜索 API 被风控**，必须经用户 Chrome 出口跑 CDP。下面 7 步是 2026-07-15 实测跑通的完整链路（77 篇 → 精选 23 道入库），照顺序执行即可复现。

**Step 1 — 探测端口 / 环境**
```bash
curl -s http://127.0.0.1:9222/json/version || echo NO_CHROME_9222   # 端口是否已开
ls "C:/Users/UserName/.workbuddy/binaries/python/envs/default/Scripts/python.exe"  # venv
"C:/Users/UserName/.workbuddy/binaries/python/envs/default/Scripts/python.exe" -c "import websocket"  # websocket-client
```
Chrome 路径固定：`C:/Users/UserName/AppData/Local/Google/Chrome/Application/chrome.exe`。

**Step 2 — 启动带远程调试的专用 Chrome**（⚠️ 三个坑见 references/cdp.md / MEMORY.md）
```bash
# 若 9222 已被旧实例占用，先杀整棵进程树（同 profile 复用会加入旧会话，端口不会重绑）
pkill -f "remote-debugging-port=9222"   # 或 taskkill.exe /PID <pid> /T /F
# 必须带 --remote-allow-origins=*，否则 Chrome 150+ 握手 403；用独立调试 profile 避免锁冲突
"C:/Users/UserName/AppData/Local/Google/Chrome/Application/chrome.exe" \
  --remote-debugging-port=9222 --remote-allow-origins=* \
  --user-data-dir="C:/Users/UserName/.workbuddy/chrome-debug-profile" \
  --no-first-run --no-default-browser-check --window-position=200,200 &
```

**Step 3 — 让用户在弹出的窗口里登录掘金**。开放源理论上免登录，但登录后 cookie 生效更稳、少触发风控。等用户确认已登录再继续。

**Step 4 — 复探登录态 + 搜索可用性**（可选，用 `scripts/_probe_juejin_login.py` 或直接跑采集）。确认 `avatar:True` 且搜索能返回 `a[href^='/post/']` 卡片即可。

**Step 5 — 正式采集**（venv python，后台跑，7 关键词 × 每词 15 篇）
```bash
cd agent-mianshi-harvester && \
"C:/Users/UserName/.workbuddy/binaries/python/envs/default/Scripts/python.exe" scripts/juejin_harvest.py
# 监控：读进度文件（勿依赖 stderr）
cat data/tmp/juejin/progress.json          # 状态 RUNNING/DONE
wc -l < data/tmp/juejin/posts.jsonl        # 已落盘帖子数
```

**Step 6 — 后处理**（managed python，纯标准库，无需 venv）
```bash
"C:/Users/UserName/.workbuddy/binaries/python/versions/3.13.12/python.exe" \
  scripts/process_source.py --source juejin     # 产出 candidates/shortlist/refined
```

**Step 7 — ⚠️ 严格过滤 + 人工精选后入库（掘金必做，不可全量灌！）**
- 掘金噪声量级比牛客/小红书高 **1~2 个数量级**（77 篇 → refined 1803 条，大量标题/前端题/散文被误判成题）。**严禁**把 refined 直接 `bank.add_entry`，否则污染题库。
- 正确做法：先用严格过滤脚本（如 `scripts/_curate_pool.py`：按 Go 后端→Agent 方向 + 表述干净度筛）把 1803 → 几十条干净候选池，再**人工/LLM 精选 20~30 道**，手写四段式答案，逐条 `bank.add_entry` 入库。
- 入库后校验：与已有题跑 `difflib` 0.85 相似度，0 重复才算干净；最后 `bank.load()` 重读再写 `meta.total`（`add_entry` 内部每次 load+save，切勿用旧 data 对象覆盖）。
- 可选：`bash scripts/upload_feishu.sh` 把新题按分类建飞书节点并回写 `wiki_node_token/wiki_url`。

### 模式 B：每日推送 daily（自动化触发，全自动）
- 由**自动化（recurring, 每天 09:00）**触发，prompt 指向本 skill 的 daily 模式。
- 调 `scripts/prepare_daily_email.py` 从 `data/questions-bank.json` 抽 5 题：分类均衡、优先最新爬到的、避开已发送（`email_sent.json` 去重循环）。
- ⚠️ **推送分类偏好（用户明确指定，不可改）**：每日推送**只发技术类**题目，永久排除 `手撕算法` 与 `行为与HR`，两处均已写死 —— `daily.py` 与 `prepare_daily_email.py` 的 `EXCLUDE_CATS = {"手撕算法","行为与HR"}`（**用户 2026-07-15 明确要求「手撕算法不要发」**）。即只推送：概念基础 / 架构设计 / 工程落地 / 后端八股（Go） / 项目深挖。
- 用生成的 **HTML 邮件正文**（内联样式、卡片式、分类彩色徽章、链接可点）经 **QQ 邮箱连接器** `SendMessage` 以 `body_format=HTML` 推送；多数邮箱客户端不渲染 Markdown，故只用 HTML 不用 Markdown。未启用则降级飞书消息（lark-unified）。
- 去重循环存储：自动化实际调用的 `prepare_daily_email.py` 把已推 id 追加进 `data/tmp/email_sent.json`（发完一轮自动重置循环）；早期 `daily.py` 变体才会写入 bank 的 `meta.last_pushed`（现已不用于自动投递）。

## 分类体系（7 类，"后端八股(Go)"独立成类）
1. **概念基础**：Agent / LangGraph / Function Calling / RAG / 幻觉 / 记忆机制 / 上下文工程
2. **架构设计**：可扩展 Agent 系统、多轮记忆、工具编排、反思/规划模块
3. **工程落地**：并发 / 服务化（Go 或 FastAPI）/ Docker / 监控 / 限流重试 / 可观测性
4. **手撕算法**：LeetCode 代码题（**只记题面 + 思路；若是力扣题必须附力扣链接，仅题号也可**）
5. **项目深挖**：结合简历的项目追问（架构/难点/量化效果）
6. **后端八股（Go）**：Go 并发/调度、GC、channel、分布式、MySQL、Redis、网络 —— **独立成类**
7. **行为与 HR**：自我介绍、职业规划、为什么转 Agent、薪资/期望

## 去重设计（关键：不依赖 lark-unified 语义搜）
因为 lark-unified 仅关键词检索，本 skill 采用**本地语义镜像**方案：
- `data/questions-bank.json` 是飞书知识库的**权威本地镜像**（每次上传都同步写本地）。
- 新题进来先 `normalize(text)`：
  - 与 bank 中任一 `normalize(content)` **完全一致** → `已有`。
  - 否则算相似度：优先 embedding 余弦（若环境有 sentence-transformers），否则用 `difflib.SequenceMatcher` 比值作为代理。
  - ≥ 0.85 → `已有`；[0.7, 0.85) → `待复核`；< 0.7 → 新题。
- 交叉校验：调 lark-unified 对飞书做**关键词**搜索取候选文档，智能体用 LLM 判断新题是否与候选语义等价，等价则降级为 `已有`。
- **首批**（bank 为空或首个运行）所有 [0.7,0.85) 与边界项强制 `待复核` 交人工确认；之后按阈值全自动。

## 答案格式模板（必须引权威来源）
```
# [分类] 题面
- 来源：xxx（一面/二面）
- 难度：★★☆
- 标签：LangGraph, 记忆
## 题面
...
## 参考答案
### 简版（30s 口播）
...（引用：[来源名](链接)）
### 展开（追问时铺开）
...（引用：...）
### 加分点
...
### 雷区/易错
...
## 来源
- [牛客原帖](url) / [官方文档](url) / ...
## 关联题目：id-xxx
```
手撕题额外块：
```
## 力扣链接
- https://leetcode.cn/problems/<slug>/  （或仅题号：LeetCode 678）
```

## 文件结构
- `SKILL.md` — 本文件
- `scripts/harvest.py` — **一键增量调度器**：`--source all|xiaohongshu|juejin|v2ex|maimai|nowcoder|zhihu [--stage collect|process|all]`
- `scripts/cdp_helper.py` — **共享 CDP 核心**：`Browser` 类 + `run_source(adapter)` 通用驱动（含验证自动等待、断点续传）
- `scripts/juejin_harvest.py` / `v2ex_harvest.py` / `maimai_harvest.py` / `zhihu_harvest.py` — 四新源采集器（均 import cdp_helper，各实现一个 adapter；知乎为强登录墙源，需先登录 zhihu.com）
- `scripts/xiaohongshu_harvest.py` — 小红书采集器（参考实现，xsec_token + 验证等待）
- `scripts/nowcoder_harvest.py` — 牛客采集器（站内搜索 API）
- `scripts/process_source.py` — 通用后处理：对任意源 posts.jsonl 抽取候选 + 与题库去重 → `candidates/shortlist/refined`
- `scripts/bank.py` — 题库 JSON 读写 / 增条目 / 状态标记
- `scripts/daily.py` — 早期 3 题抽题变体（写 bank.meta.last_pushed，现已不被自动投递使用，保留参考）
- `scripts/prepare_daily_email.py` — **每日 5 题 HTML 邮件生成（自动化实际调用）**：抽题+排版，分类排除走 `EXCLUDE_CATS`，去重走 `email_sent.json`
- `scripts/juejin_harvest.py` — 掘金采集器（开放源但搜索被风控，走 CDP；实操 SOP 见「模式 A·掘金采集 SOP」）
- `scripts/weixin_harvest.py` — 微信公众号采集器（面经哥等；**纯 HTTP 免登录免 CDP**，提取正文 + 文末推荐链接 BFS 滚雪球扩源，落盘 `data/tmp/weixin/posts.jsonl`）
- `scripts/sogou_weixin_search.py` — 搜狗微信搜索枚举（按关键词搜面经哥文章）；**⚠️ 受 antispider 限制，自动还原真实链接常失败**，仅作"列标题+转链清单"用途；可靠批量采集请用户直接复制浏览器地址栏链接（中转 `s?src=11&signature=` 或永久 `s/<ID>` 均可）交给 weixin_harvest.py（见上方微信源限制说明）
- `scripts/_curate_pool.py` / `_probe_juejin_login.py` — 掘金精选池过滤 / 登录态探测（辅助脚本）
- `scripts/collect_login.py` — 早期 CDP 骨架（已被 cdp_helper 取代，保留参考）
- `scripts/gen_upload_plan.py` / `upload_feishu.sh` / `apply_results.py` / `parse_node.py` — 飞书上传链路
- `data/questions-bank.json` — 题库（本地语义镜像，去重权威副本）
- `data/wiki-config.json` — 飞书空间/分类节点 token 映射
- `references/taxonomy.md` — 分类体系与字段样例
- `references/sources.md` — 采集源清单（公开 + 登录墙）
- `references/cdp.md` — 登录墙抓取方案（CDP 复用已登录 Chrome）

## 关键风险
- 飞书 Wiki 搜索非语义 → 已用本地镜像规避；但 bank 与飞书需保持同步（上传必写本地）。
- **登录墙源串行 + 随机 sleep + 验证自动等待**：滑块验证页会阻塞 JS 上下文，使 `Runtime.evaluate` 超时——必须把"超时"保守判为验证页并原地轮询等用户滑掉，否则会误判"无验证"而空转遍历所有 query 却 0 产出（小红书踩过的坑）。
- **V2EX 在本机网络不可达**（Chrome/沙箱均超时），其站内搜索功能也失效；该源仅作便携脚本保留，换网络环境或 WebFetch 兜底才可用。
- 牛客/小红书/脉脉反爬严格，登录墙源串行，遇风控即跳过/等待，不硬刚。
- LLM 答案虽引来源，仍标注"AI 整理，建议核对"，避免记错八股。
- QQ 邮箱连接器未启用时，daily 模式自动降级飞书消息，不中断。
