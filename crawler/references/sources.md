# 采集源清单（references/sources.md）

## 公开源（WebSearch + WebFetch，无需登录）
- 牛客公开帖：`https://www.nowcoder.com`（搜索 "Agent 开发 面经"）
- 掘金：`https://juejin.cn`（如《最稳、最落地、适合 5 年 Python 后端转 AI Agent 的路线》）
- CSDN：`https://blog.csdn.net`（如《Agent 开发面试通关攻略》）
- 腾讯云开发者社区：`https://cloud.tencent.com/developer`（如《字节 AI Agent 二面(飞连)面试题与参考解答》）
- CodeFather：`https://www.codefather.cn`
- OfferShow / 小红书网页版公开帖
- 通用 WebSearch 关键词组：
  - "Agent 开发 面经" / "AI Agent 面试 手撕" / "LangGraph 面试题"
  - "RAG 面试" / "Function Calling 面试题" / "Agent 架构设计 面试题"
  - "Go 后端 转 Agent" / "Agent 岗 后端八股"

## 登录墙源（需 CDP 复用已登录 Chrome，见 cdp.md）
- 牛客深度帖 / 私信分享帖
- 小红书 App 网页版深度经验帖
- 脉脉 / 微信朋友圈转载
- 知乎问答 / 专栏文章（强登录墙 + 强反爬，须先在 Chrome 登录 zhihu.com；采集脚本 `zhihu_harvest.py` 收"问题"与"文章"两类卡片，问题页合并多个回答正文）

## 抓取纪律
- 串行 + 随机 sleep，遇登录墙/验证码即跳过，不破解、不硬刚。
- 每条保留原始 `url` 作为可校验锚点与答案来源。
