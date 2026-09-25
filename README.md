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
- 判题：HTTP 回调 Agent 或直连 OpenAI 兼容 LLM，带降级（Agent 不可用时进入 pending 重试队列）

## 数据库

数据库后端可插拔（SQLAlchemy），仅通过环境变量 `DATABASE_URL` 切换，表结构无需改动。

| 后端 | 定位 | 切换方式 |
| --- | --- | --- |
| **SQLite**（默认） | 本地 / 开源贡献者 / 单人使用：零运维、单文件，clone 即跑 | 默认即 SQLite；首次启动自动在 `data/interview_memory.db` 建库 |
| **PostgreSQL**（生产推荐） | 多用户 / 正式部署 / 未来语义搜题（pgvector） | `DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/interview_memory`，并 `pip install psycopg2` |
| **MySQL**（实验性） | 团队已熟悉 MySQL 时可选 | `DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/interview_memory`，并 `pip install pymysql` |

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

系统启动后，执行一次命令即可把仓库内已审核的 **2,586 道** `questions_v2` 题目写入数据库；脚本会先校验分类文件、题目数量与唯一性，再按题面去重，可安全重复运行：

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
curl -X POST http://localhost:8000/api/questions/import-batch \
  -H "Content-Type: application/json" \
  -d '{"path":"C:\\Users\\UserName\\WorkBuddy\\Claw\\题库\\agent_interview_bank.json"}'
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
| GET | `/api/activity` | 热力图数据 |
| GET | `/api/wrong-book` | 错题本列表（支持分类/复习中/错误原因聚类） |
| GET | `/api/wrong-book/export-pdf` | 导出错题本 PDF |
| POST | `/api/wrong-book/{id}/master` | 标记已掌握 |
| GET | `/api/review/due` | 待复习题目 |
| POST | `/api/review/{id}` | 复习反馈（记住/没记住，推进间隔） |
| GET/POST | `/api/settings` | 读取/更新设置 |

OpenAPI 交互文档已自带：`http://localhost:8000/docs`

## 测试

```bash
pip install -r requirements-dev.txt
pytest tests/ -q            # 单元测试
python verify_flows.py      # 全流程回归验证
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
