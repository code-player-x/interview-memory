# 面试八股文 · 长期记忆训练系统

一个把「不依赖 Agent 的能力」从对话 Skill 中抽离出来、独立落地的软件。
目标：用 GitHub 风格热力图 + 错题本 + 艾宾浩斯遗忘曲线邮件推送，保证面试八股文的长期记忆真正形成。

> 完整设计方案见 [`docs/design.html`](docs/design.html)（含可交互原型）。

## 边界：Agent 只做两件事

| 能力 | 归属 |
| --- | --- |
| 爬取各平台面试八股文 | **Agent** |
| 判断用户答案对错（LLM 判题） | **Agent** |
| 题库管理 / 每日选题 / 热力图 / 错题本 / 艾宾浩斯调度 / 邮件 | **软件** |

邮件模板由软件托管、固定可控，不依赖 Agent 改写（硬性要求）。

## 技术栈

- 后端：**Python + FastAPI**，SQLite（默认）/ PostgreSQL（生产推荐）/ MySQL（实验性）
- 定时：**APScheduler**（每日推送复习邮件）
- 前端：原生 HTML/JS（热力图 + 错题本 + 练习，无构建步骤）
- 判题：HTTP 回调 Agent 或直连 OpenAI 兼容 LLM，带降级（远端不可用时标记 pending 并持久化入队，服务恢复后自动重试）

## 数据库

数据库后端可插拔（SQLAlchemy），仅通过环境变量 `DATABASE_URL` 切换，表结构无需改动。

| 后端 | 定位 | 切换方式 |
| --- | --- | --- |
| **SQLite**（默认） | 本地 / 开源贡献者 / 单人使用：零运维、单文件，clone 即跑 | 默认即 SQLite；首次启动自动在 `data/interview_memory.db` 建库 |
| **PostgreSQL**（生产推荐） | 多用户 / 正式部署 / 未来语义搜题（pgvector） | `DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/interview_memory`，驱动随项目依赖安装 |
| **MySQL**（实验性） | 团队已熟悉 MySQL 时可选 | `DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/interview_memory`，驱动随项目依赖安装 |

> 默认 SQLite 已开启 **WAL** 模式（`PRAGMA journal_mode=WAL`），读写可并发、降低写锁概率。
> 生产环境建议 PostgreSQL；MySQL 未纳入官方测试矩阵，欢迎 PR 补全。

## 目录结构

```
interview-memory/
├─ backend/
│  ├─ app.py           # FastAPI 入口：接口 + 静态托管 + 启动调度
│  ├─ db.py            # SQLite 连接与会话
│  ├─ models.py        # 数据模型
│  ├─ judge.py         # 调用 Agent/LLM 判题（含降级）
│  ├─ scheduler.py     # 每日复习邮件任务
│  ├─ emailer.py       # SMTP 发送 + 固定模板
│  └─ ebbinghaus.py    # 间隔计算
├─ frontend/
│  ├─ index.html
│  ├─ app.js
│  └─ styles.css
├─ tests/              # pytest 单元测试
├─ data/               # SQLite 文件（自动生成）
├─ docs/design.html    # 软件设计方案
├─ requirements.txt
├─ .env.example
├─ Dockerfile
├─ docker-compose.yml
└─ verify_flows.py     # 全流程回归验证
```

## 快速开始（本地）

```bash
# macOS / Linux
cd /path/to/interview-memory
python3 -m venv .venv && source .venv/bin/activate

# Windows（PowerShell）
# py -m venv .venv; .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
# macOS / Linux：cp .env.example .env
# Windows：copy .env.example .env
uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

打开 http://localhost:8000 即可看到热力图 / 错题本 / 练习 / 设置页面。

## 导入已审核题库

系统启动后，执行一次命令即可把仓库内已审核的 **2,689 道** `questions_v2` 题目写入数据库；按题面去重，可安全重复运行：

```bash
python scripts/import_questions_v2.py
```

如果本地已经导入过旧版 `questions_v2`，且这些题没有关联答题、错题、复习或笔记记录，可使用安全同步模式更新为当前审核版：

```bash
python scripts/import_questions_v2.py --replace
```

存在关联学习记录时，该命令会拒绝替换，避免破坏学习进度。

Docker 容器内也已内置导入脚本和已审核题库，启动后可执行：

```bash
docker compose exec app python scripts/import_questions_v2.py
```

也支持导入其他旧版 JSON 题库：

```bash
# 将 bank.json 放入 data/imports/（或 QUESTION_IMPORT_DIR）后运行
curl -X POST http://localhost:8000/api/questions/import-batch \
  -H "Content-Type: application/json" \
  -d '{"path":"bank.json"}'
```

## 接入真实判题（二选一）

### 方式 1：外部 Agent HTTP 回调
```env
AGENT_JUDGE_URL=https://your-agent.example.com/judge
AGENT_JUDGE_TOKEN=your_token
```

### 方式 2：直连 OpenAI 兼容 LLM
```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

若两者都未配置，则回退到本地启发式判题（仅跑通主流程，不准确）。

默认不会开启跨域访问；单服务前端与 API 同源时无需配置。若把前端部署到另一域名，
请在 `.env` 中显式设置 `CORS_ALLOW_ORIGINS=https://study.example.com`，可用逗号分隔多个来源。

## 数据模型

- `questions`：题库（platform / category / tags / difficulty / question_text / reference_answer）
- `submissions`：每次作答（is_correct / judge_by，热力图数据源）
- `wrong_book`：错题本（first_wrong_at / wrong_count / last_user_answer / error_reason / mastery）
- `review_schedule`：艾宾浩斯复习计划（stage / next_review_at / status）
- `activity`：按天聚合（answered / correct / wrong），驱动热力图
- `settings`：邮箱、推送时间、ebbinghaus_steps 间隔序列

## 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/questions/import` | 导入单题 |
| POST | `/api/questions/import-batch` | 批量导入 JSON 题库 |
| POST | `/api/questions/import-json` | 批量导入标准题目 JSON 数组 |
| GET | `/api/questions` | 题库列表（关键词/分类/难度/标签筛选） |
| GET | `/api/question/{id}` | 题目详情（含参考答案） |
| GET | `/api/questions/random` | 随机抽题（真正随机） |
| GET | `/api/categories` | 分类列表 |
| GET | `/api/tags` | 标签列表 |
| POST | `/api/answer` | 提交作答（触发判题） |
| GET | `/api/submissions/{submission_id}/judgment` | 获取这次作答的最新判定与评语，供单题和整卷报告刷新 |
| GET | `/api/activity` | 热力图数据 |
| GET | `/api/wrong-book` | 错题本列表（支持分类/复习中/错误原因聚类） |
| GET | `/api/wrong-book/export-pdf` | 导出错题本 PDF |
| POST | `/api/wrong-book/{id}/master` | 标记已掌握 |
| GET | `/api/review/due` | 待复习题目 |
| POST | `/api/review/{id}` | 复习反馈（记住/没记住，推进间隔） |
| GET/POST | `/api/settings` | 读取/更新设置 |

OpenAPI 交互文档已自带：`http://localhost:8000/docs`

## 采集 AI Infra 面试资料

在仓库根目录运行。GitHub 采集和一亩三分地索引都可以独立使用，无需启动浏览器。

```bash
python -m pip install -r crawler/requirements.txt
python crawler/scripts/harvest.py --source github --stage collect
python crawler/scripts/harvest.py --source github --stage process
```

GitHub 默认扫描 `caomaolufei/AIInfraGuide`、`bojieli/ai-infra-book` 和 `lyy-ai/ai_infra`，优先下载路径含面经、面试或 interview 等词的 Markdown。每轮每仓库最多新增或更新 10 份，重复运行可继续采集。原文和固定到提交版本的链接保存在 `crawler/data/tmp/github/posts.jsonl`。抽题优先使用本地母库 `crawler/data/questions-bank.json` 去重；全新克隆使用随仓库发布的已审核题库 `crawler/questions_v2/authored/`，结果写入 `crawler/data/tmp/github/refined.jsonl`。可按需设置 `GITHUB_TOKEN` 使用认证额度，或单独指定仓库和每轮上限。

```bash
python crawler/scripts/github_harvest.py --repo bojieli/ai-infra-book --max-files 5
python crawler/scripts/harvest.py --source onepoint3acres
```

一亩三分地默认检查海外面经版第一页，按 GPU、推理、vLLM 等词筛选标题，将原帖链接和命中词写入 `crawler/data/tmp/onepoint3acres/index.jsonl`。在线访问受限时，可导入自己保存的公开列表 HTML。下面的命令使用自定义关键词覆盖默认词表。

```bash
python crawler/scripts/onepoint3acres_harvest.py --html forum-page.html --keyword inference --keyword GPU
```

牛客窗口扫描会在 `--out` 目录记录起止日期和逐页进度。同一窗口可以重跑或追加关键词。切换日期窗口或使用未记录窗口的旧结果时，请指定新目录。

```bash
python crawler/scripts/nowcoder_scan_window.py --config crawler/config/nowcoder-ai-infra-recent.json --out crawler/data/tmp/nowcoder-20260918-20261118
```

## 测试

```bash
pip install -r requirements-dev.txt
pytest tests/ -q            # 单元测试
python verify_flows.py      # 全流程回归验证
node scripts/verify_frontend.cjs  # 前端逻辑回归（需 Node.js）
```

## 艾宾浩斯间隔序列（默认）

`1 → 2 → 4 → 7 → 15 → 30 → 60` 天（在设置中可改；可选 SM-2 动态调间隔）

## Docker 部署

```bash
cp .env.example .env   # 填写 SMTP_PASSWORD / LLM_API_KEY 等
docker compose up -d --build
```

`docker-compose.yml` 默认只把服务发布到 `127.0.0.1:8000`，数据库、上传图片和 PDF
导出统一持久化在 `./data`。不要直接把应用端口暴露到公网；公网部署请在前方使用具备
TLS、访问鉴权与限流能力的反向代理，并按需显式配置 CORS。

容器默认时区为 `Asia/Shanghai`，每日推送时间按该时区解释；可在 `.env` 中用 `TZ` 覆盖。
本地运行使用操作系统时区。各进程每分钟读取推送设置，通过数据库唯一记录领取当天邮件任务，避免多 worker 重复发送。SMTP 结果不确定或领取后进程中断时，当天不会自动重发；可能漏发，但避免重复邮件。
Docker 构建上下文采用允许清单，不包含 `.env`、本地数据库、日志和虚拟环境。

Compose 现在透传 `DATABASE_URL` 与 `STORAGE_BACKEND/S3_*`。镜像包含 PostgreSQL
（`postgresql+psycopg2://`）和 MySQL（`mysql+pymysql://`）驱动；外部数据库服务需要自行提供，
MySQL 仍属实验支持。SQLite 默认文件在 `/app/data`，不要把宿主机绝对路径直接写进容器配置。
镜像本身使用 UID/GID 10001；为兼容现有 root 所有的 bind mount，Compose 默认保留 UID/GID 0。
确认 `./data` 对所选用户可写后，在 `.env` 设置 `APP_UID`、`APP_GID` 即可切换为非 root；
在 Linux 可使用宿主机当前用户的 UID/GID。启动过程不会自动更改已有卷的所有权。
Python 依赖由 `requirements.txt` 和 `requirements.lock` 固定；基础镜像与系统软件包仍需单独维护更新。

## SQLite 与本地配图备份

先停止应用（容器部署用 `docker compose stop app`）以及所有导入/采集写入脚本，再在宿主机运行：

```bash
python scripts/backup_data.py backup --stopped --db data/interview_memory.db --images data/images --output backups/snapshot-20261118
python scripts/backup_data.py verify --snapshot backups/snapshot-20261118
python scripts/backup_data.py restore --snapshot backups/snapshot-20261118 --output restored-data
```

备份包含 SQLite 一致性快照、全部本地配图与 SHA-256 清单，覆盖 WAL 中已提交的数据。
即使没有配图，`--images` 也应指向实际存在的空目录，便于识别路径拼写或挂载错误。
`--stopped` 表示调用者已停止所有写入，工具不负责关闭服务；这保证数据库记录与配图属于同一批状态。
恢复只接受不存在的新目录，校验失败会拒绝恢复，不覆盖当前数据库。
恢复完成后保持服务停止：保留原 `data` 目录，将恢复目录作为新的 `data` 挂载后启动并检查页面。
若数据库原文件名不同，应按 `DATABASE_URL` 指定的名称放置恢复的 `interview_memory.db`。
自定义图片目录用 `--images` 指定；S3 对象、PostgreSQL/MySQL、外部文章资源和密钥不在此快照中，需分别备份。
导出 PDF 可以重新生成，因此不放入快照。


技术文章摘抄是可选资源，仓库和镜像不打包第三方 `book` 目录。未设置
`ARTICLES_BOOK_DIR` 时页面会清晰提示未配置；本地可将其设为该目录绝对路径，容器场景
还需以只读卷挂载该目录并令变量指向容器内路径。

## 实施里程碑

| 阶段 | 状态 |
| --- | --- |
| P0 数据层 + 判题回调 | ✅ 已完成 |
| P1 练习闭环 | ✅ 已完成 |
| P2 可视化（热力图 + 错题本） | ✅ 已完成 |
| P3 记忆引擎（艾宾浩斯调度 + 固定模板邮件） | ✅ 已完成 |
| P4 多标签筛选 + LLM 判题 + 错题本 PDF + 多年历史热力图 | ✅ 已完成 |
| P5 统计报表 / 邮件回复解析 | ⏳ 待做 |

> 注：邮件「回复『1 记住』」目前通过网页按钮（`/api/review/{id}`）实现；
> 解析收件箱邮件自动推进为可选增强。

## 开源化路线图（TODO）

将本项目发布为开源仓库前需完成：

- [x] **LICENSE**：选定协议（MIT，已添加 `LICENSE` 文件）
- [x] **`.gitignore`**：已加入，屏蔽 `data/`（数据库 + 上传图片 + 导出）、`.env`（密钥）、Python 缓存等
- [x] **`CONTRIBUTING.md`**：贡献指南（如何跑起来、如何提 PR、DB 后端说明）
- [ ] **CI**：GitHub Actions 仅测 SQLite + PostgreSQL 两套后端（`pytest tests/`），不纳入 MySQL
- [ ] **Docker**：`docker-compose.yml` 已提供，建议默认附带 PostgreSQL 服务，方便一键起生产态
- [ ] **文档**：补充「部署到云」示例（Supabase / Neon / Railway 等托管 Postgres）
- [ ] **示例数据**：可选提供脱敏的种子脚本，便于贡献者快速看到效果

### 后台任务与历史导入

pending 判题每分钟最多处理 10 条，失败后按 1、2、4 分钟递增退避，最长 60 分钟。领取租约为 120 秒，进程中断后可恢复。新作答保存当时的题干和参考答案，后台用同一版本重判。历史队列缺少快照时，仅在能确认原题身份的情况下固定题干和参考答案。题号被复用或时间信息不足时，取消该次重判，保留原作答记录。成功后更新原提交及原日期的正误计数，答题次数保持一次。单题与整卷报告中的“刷新判题结果”可以取回这次作答的最新评语。关闭远端判题时，队列保留待判记录。

飞书 Markdown 与面试鸭 PDF 导入使用 DATABASE_URL。SQLite 专用 crawler 工具按 `--db`、进程环境、项目 `.env` 的顺序选库，非 SQLite 后端会明确拒绝。`crawler/sync.py` 把同一目标传给转换与导入；`--dry-run --with-fill` 跳过模型调用和母库修改，转换产物使用临时目录。关键词提取的预演使用只读连接，不修改旧库结构。去重同步遇到多条错题或复习状态归并冲突时会在写入前拒绝，需要先明确状态合并方式。

### 页面访问、上传和后台状态

默认 Compose 仅发布本机端口。共享使用时，在 HTTPS 入口配置整站鉴权，或同时设置 `APP_AUTH_USER` 和 `APP_AUTH_PASSWORD` 启用应用级 HTTP Basic 登录，重启后生效。该登录同时覆盖页面、静态文件与 API。携带浏览器 Origin 的写请求仅接受同源或显式配置的跨域来源。

答案上传接受 PNG、JPEG、GIF、WebP、BMP，每张最多 8 MiB、2400 万像素，并核对真实图片格式。服务端 JSON 文件导入仅接受 `QUESTION_IMPORT_DIR` 中的文件（默认 `data/imports/`），上限 16 MiB。

`GET /api/admin/jobs` 可查看当前进程的调度状态、最近任务事件、下次轮询时间，以及数据库里的待判数量、最老待判时间和最近一次邮件投递状态。任务函数返回与 SMTP 确认发送分别记录。设 `SCHEDULER_ENABLED=0` 时仅提供页面和 API；日常使用应保持调度启用。
