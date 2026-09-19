# 贡献指南（CONTRIBUTING）

感谢你对「面试八股文 · 长期记忆训练系统」感兴趣！本文档说明如何在本仓库跑起来、如何提 Issue / PR，以及数据库与图片存储的约定。

> 完整设计方案见 [`docs/design.html`](docs/design.html)。项目整体说明请读 [`README.md`](README.md)。

---

## 行为准则（CoC）

请友善、尊重地交流。我们采用常见的开源社区共识：**就事论事、不人身攻击、对初学者友好**。辱骂、骚扰、歧视类言论一律零容忍。

---

## 如何报告问题 / 提需求

1. 先搜 [Issues](https://github.com/code-player-x/interview-memory/issues) 确认没人提过。
2. 新建 Issue，并尽量带上：
   - **复现步骤**（能稳定触发的最小操作）
   - **期望行为 vs 实际行为**
   - **环境**：操作系统、Python 版本、数据库后端（SQLite/PostgreSQL/MySQL）
   - **日志**：后端 `uvicorn` 报错、浏览器 Console 报错（脱敏后）
3. 功能建议请标注 `[Feature]`，并说明使用场景。

---

## 开发环境搭建

### 1. Fork & Clone

```bash
git clone git@github.com:code-player-x/interview-memory.git
cd interview-memory
```

### 2. 准备 Python 环境

需要 **Python 3.10+**。推荐用虚拟环境隔离：

```bash
# Windows
python -m venv .venv && .venv\Scripts\activate
# macOS / Linux
python3 -m venv .venv && source .venv/bin/activate

pip install -r requirements-dev.txt
```

> 若计划使用对象存储（见下文「图片存储」），额外安装：`pip install boto3`

### 3. 配置（可选）

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

`.env` 用于 SMTP 邮件、Agent 判题回调、或直接连 LLM 判题。**不填也能本地跑**（判题会进入 pending 降级队列）。注意 `.env` 已被 `.gitignore` 忽略，切勿提交密钥。

### 4. 启动后端

```bash
uvicorn backend.app:app --reload --port 8000
```

> ⚠️ **务必带 `--reload`**：后端热重载才能在改代码后立即生效；不带 `--reload` 的老进程会一直跑旧路由表，导致新接口 404。这是踩过的坑。

启动后前端由后端**静态托管**在 http://localhost:8000 ，直接打开即可看到热力图 / 错题本 / 练习 / 设置页。

若只想单独预览前端布局（不连 API），也可：

```bash
python -m http.server 8088 --directory frontend
# 打开 http://localhost:8088
```

### 5. 导入题库（可选）

首次运行建议先导入题库，否则页面是空的：

- **方式 A（已审核 questions_v2）**：导入仓库自带的精选题库，命令可重复执行：

  ```bash
  python scripts/import_questions_v2.py
  ```

- **方式 B（批量 JSON）**：把你的题目 JSON 通过接口导入

  ```bash
  curl -X POST http://localhost:8000/api/questions/import-batch \
    -H "Content-Type: application/json" \
    -d '{"path":"/绝对路径/你的题库.json"}'
  ```

- **方式 C（飞书 Markdown）**：解析飞书导出的题库 Markdown

  ```bash
  python scripts/import_feishu_wiki.py --md data/feishu_go_qa.md
  # 需要补全图片时加 --download-images；补已有题的 images 列加 --update
  ```

---

## 数据库后端

数据库后端通过 SQLAlchemy 可插拔，**仅改环境变量 `DATABASE_URL`**，表结构无需改动：

| 后端 | 定位 | 切换方式 |
| --- | --- | --- |
| **SQLite**（默认） | 本地 / 开源贡献者 / 单人：零运维、单文件，clone 即跑 | 默认即 SQLite |
| **PostgreSQL**（生产推荐） | 多用户 / 正式部署 / 未来语义搜题（pgvector） | `DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/interview_memory`，并 `pip install psycopg2` |
| **MySQL**（实验性） | 团队已熟悉 MySQL 时可选 | `DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/interview_memory`，并 `pip install pymysql` |

- 默认 SQLite 已开启 **WAL** 模式，读写可并发。
- PostgreSQL 是生产推荐；MySQL 未纳入官方测试矩阵，欢迎 PR 补全。

---

## 图片存储

解析图片支持两种存储后端，由 `STORAGE_BACKEND` 环境变量切换（默认 `local`）：

- **`local`**（默认）：图片存到 `data/images/`，数据库 `images` 列保存可访问路径 `/data/images/<file>`，clone 即跑、零运维。
- **`s3`**：图片上传到对象存储（AWS S3 / 阿里云 OSS / 腾讯云 COS / MinIO / Cloudflare R2 均兼容，boto3 实现），`images` 列保存绝对 URL。需额外配置 `S3_ENDPOINT / S3_REGION / S3_BUCKET / S3_ACCESS_KEY / S3_SECRET_KEY / S3_PUBLIC_URL`。

> **请勿把数据库文件、`.env`、上传图片、日志提交进仓库**——它们已被 `.gitignore` 屏蔽，提交 PR 前请 `git status` 确认工作区干净。

---

## 代码与提交规范

- **分支策略**：从 `master` 切功能分支（`feat/xxx`、`fix/xxx`），不要把未完成改动直接推 `master`。
- **提交信息**：`<type>: <一句话简述>`，type ∈ `feat` / `fix` / `refactor` / `docs` / `style` / `chore` / `test`。
  - 例：`fix(storage): S3 模式下 URL 拼接多一个斜杠`、`feat(judge): 支持直连 LLM 判题降级`。
- **小步提交**：一个逻辑点改完就提交一次，比"攒一大坨再提"更易 review、易回滚。
- **不要提交**：`data/`、`*.db`、`*.bak*`、`.env`、`uvicorn*.log`、前端 `*.bak*/` 等（已被 `.gitignore` 忽略）。
- **前端改动提示**：`frontend/` 是原生 HTML/JS、无构建步骤。样式/交互的**大改请先开 Issue 与维护者对齐**（避免 PR 返工）；小修小补直接提 PR 即可。

---

## 测试

核心模块有 `pytest` 单测（当前覆盖图片存储抽象层）：

```bash
pytest tests/ -q
python verify_flows.py
```

提交前请保证本地测试通过。新增功能建议同步补测试。

---

## PR 流程

1. Fork 本仓库，从 `master` 切出功能分支。
2. 本地开发与自测（含 `pytest`）。
3. 提交（遵循上面的 commit 规范），推送你的 fork。
4. 在 GitHub 开 PR 到本仓库 `master`，PR 描述写清楚：
   - 改了什么、为什么改
   - 是否涉及数据库 / 配置变更（如需，说明迁移方式）
   - 如何验证
5. 等待 Review；如需调整，按 Review 意见追加提交（不要 force-push 覆盖历史，除非维护者要求）。

---

再次感谢你的贡献 🎉
