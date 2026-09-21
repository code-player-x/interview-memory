# 分类体系与字段样例（references/taxonomy.md）

## 7 大分类
1. 概念基础：Agent / LangGraph / Function Calling / RAG / 幻觉 / 记忆机制 / 上下文工程
2. 架构设计：可扩展 Agent 系统、多轮记忆、工具编排、反思/规划模块
3. 工程落地：并发 / 服务化（Go 或 FastAPI）/ Docker / 监控 / 限流重试 / 可观测性
4. 手撕算法：LeetCode 代码题（只记题面+思路；力扣题必附链接，仅题号也可）
5. 项目深挖：结合简历的项目追问（架构/难点/量化效果）
6. 后端八股（Go）：Go 并发/调度、GC、channel、分布式、MySQL、Redis、网络 —— **独立成类**
7. 行为与 HR：自我介绍、职业规划、为什么转 Agent、薪资/期望

## 题库条目字段（questions-bank.json 中每条）
```json
{
  "id": "q0001",
  "category": "概念基础",
  "type": "essay",            // essay | code
  "content": "什么是 AI Agent？和普通 LLM 应用区别？",
  "source": "字节 AI Agent 二面(飞连)",
  "difficulty": "★★☆",
  "tags": ["Agent", "LLM"],
  "status": "新增",            // 新增 | 已有 | 待复核
  "answer": {
    "简版": "...",
    "展开": "...",
    "加分点": "...",
    "雷区": "..."
  },
  "leetcode_url": "",          // 手撕题：https://leetcode.cn/problems/<slug>/ 或空
  "sources": ["https://..."],  // 权威来源链接
  "norm": "...",               // 由 bank.normalize 自动生成，用于精确去重
  "created_at": "2026-07-13"
}
```

## 手撕题特殊规则
- `type: "code"`，`leetcode_url` 必填（力扣链接；若原文只给题号如"LeetCode 678"，填
  `https://leetcode.cn/problems/<slug>/` 的占位或仅记题号文本均可）。
- 答案块不强制附可运行代码（用户决定：只记题面+思路）；如需代码再补 `answer.code`。
