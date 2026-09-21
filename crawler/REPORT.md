# 端到端验证报告（2026-07-13）

Agent 面经收割机 skill v1.0 已跑通完整链路：

**采集（WebSearch 真实题源）→ 分类（7 类）→ 去重（本地镜像，空库首跑全为「新增」）→ 答题（引用权威来源）→ 上传飞书（按类挂载）→ 写本地镜像 → 每日抽题验证。**

采集源：牛客 / CSDN / 掘金 / Go 官方文档。共 10 题，覆盖全部 7 类，均已上传到飞书知识库「Agent开发面试题库」。

## 已上传题目（按分类）

### 概念基础
- [介绍一下 Agent 的核心组件，以及它和普通 LLM 应用的核心区别是什么？](https://my.feishu.cn/wiki/ZVw3wb6OfiXj0GknBkNcpOnEn2d) ｜ ★★☆ ｜ 新增
- [Function Calling 和 MCP 的区别是什么？](https://my.feishu.cn/wiki/IbhCwNuWjiCRJOkgyTycY4HEnBd) ｜ ★★☆ ｜ 新增
- [RAG 的整体流程是什么？RAG 能彻底消除幻觉吗？如何降低幻觉？](https://my.feishu.cn/wiki/Hvv0wLl0oi3SPAklWWpcZSqvncb) ｜ ★★☆ ｜ 新增

### 架构设计
- [如何设计 Agent 的分层记忆系统？短期 / 工作 / 长期记忆分别怎么考虑？](https://my.feishu.cn/wiki/BEJww59foiqhU3kZ73Hctc1onYg) ｜ ★★★ ｜ 新增

### 工程落地
- [Agent 工具调用失败如何处理？如何提升工具可靠性？](https://my.feishu.cn/wiki/Dkj2wTG6AiHnOHkOrtFc3XnYnQg) ｜ ★★★ ｜ 新增

### 手撕算法
- [最小覆盖子串（LeetCode 76, Hard）如何用滑动窗口实现？](https://my.feishu.cn/wiki/RX2pwE1hsipFEHk8ThecpRchn0e) ｜ ★★★ ｜ 新增（附力扣链接）
- [零钱兑换（LeetCode 322）怎么解？](https://my.feishu.cn/wiki/QHLswAwIkiiwFkkQblgcT1fnnmh) ｜ ★★☆ ｜ 新增（附力扣链接）

### 后端八股（Go）
- [说一下 Go 的 Goroutine 调度模型（GMP），以及 Channel 的底层实现与阻塞/非阻塞？](https://my.feishu.cn/wiki/JRhMwZ3egiIzokkRlHQcDhfknAe) ｜ ★★★ ｜ 新增

### 行为与 HR
- [你现在是 Go 后端，为什么想转做 Agent 开发？你的职业规划？](https://my.feishu.cn/wiki/TWhAwKtlGiNLgrkzvLycokHpn3R) ｜ ★★☆ ｜ 新增

### 项目深挖
- [如何设计并评估一个 Agent/RAG 系统的线上效果？](https://my.feishu.cn/wiki/Lferw5In8ixBGZkmzl7chAy0nsd) ｜ ★★★ ｜ 新增

## 流水线产物
- `data/questions-bank.json`：题库本地镜像（10 题，全带 wiki_node_token / wiki_url）
- `data/wiki-config.json`：飞书空间 / 分类节点 token 映射
- `scripts/upload_feishu.sh`：上传入口（在 Bash 工具中运行）
- `scripts/daily.py`：每日抽 3 题（已验证：跨类、避近 7 天、优先新增）
- 自动化「Agent面经每日3题推送」：每天 08:30 经 QQ 邮箱推送（已注册）

## 已知环境坑（已规避）
- Windows 下 python 子进程解析不到 Git Bash 版 lark-cli（报 HCS 服务不可用）→ 上传改走 `bash scripts/upload_feishu.sh`。
- 生成 plan.tsv 为 CRLF，循环里需 `sed 's/\r$//'` 去 `\r`，否则 `cat` 取不到 XML 导致空正文（首跑已踩中并修复重灌）。

## 后续可扩展
- 登录墙源（牛客深度帖 / 小红书）走 `scripts/collect_login.py`（CDP），本次验证用公开源。
- 「项目深挖」类目前为用户简历驱动，待你提供简历后可批量生成针对性题。
- 去重阈值 0.85 + 首批人工复核：当前为全新增（空库），后续增量运行如需严格去重可接入 embedding。
