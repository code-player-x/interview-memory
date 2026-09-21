# 练习库去重 + 母库同步 验证报告

- 日期：2026-09-18
- 目标库：`G:/interview-memory/data/interview_memory.db`
- 母库：`G:/interview-memory/crawler/data/questions-bank.json`（3820 题，已完成 0.88 去重）
- 嵌入模型：Ollama **bge-m3**（1024 维），阈值 **0.88**，并查集连通分量聚类

## 结果

| 项目 | 数值 |
|---|---|
| 同步前题数 | 1578 |
| 内部去重删除 | 114 |
| 冗余删除 | 0 |
| 母库命中（复用原 id 富化） | 1283 |
| 练习独有保留 | 181 |
| 母库独有插入 | 2537 |
| **最终题数** | **4001** |

## 学习进度（零丢失）

| 表 | 行数 | 孤儿外键 |
|---|---|---|
| review_schedule | 17 | 0 |
| submissions | 31 | 0 |
| wrong_book | 17 | 0 |

- 进度外键重定向 114 条（被合并题 → 保留题）
- 原 17 个有进度的题全部仍在最终库中

## 发现并修复的问题：富化阶段答案降级

**现象**：富化用母库数据整体覆写匹配行；当母库答案比练习库原有答案简略时造成内容丢失。

- 影响：**411 行被降级，丢失 144,008 字**
- 最严重：`sync.RWMutex读写锁底层是怎么实现的` 3484 → 403 字（-88%）；`interface的底层原理了解吗` 2232 → 232 字

**修复（两步）**：

1. `scripts/repair_answer_downgrade.py` 按 id 恢复「原答案更长」的行 → 411 行全恢复，挽回全部 144,008 字
2. 根治：在 `dedup_sync_practice.py` 步骤 3 加入 `no_downgrade()` —— **enrich but never downgrade**
   （`reference_answer` 取母库与练习库原答案中更长者；分类/标签/难度/来源仍用母库覆盖。
   该保护只作用于 UPDATE 富化行，INSERT 新行不适用）

## 最终校验

| 校验项 | 结果 |
|---|---|
| 题数 | 4001 |
| 唯一 id | 4001（最大 id 4115） |
| 进度孤儿外键 | 0（三表全 0） |
| 答案降级行 | **0** |
| 富化变长行 | 547（净增 118,423 字） |
| 空答案 | 9（同步前既有，非本次引入） |

## 备份（可还原）

| 备份 | 内容 |
|---|---|
| `interview_memory.db.bak_20260918_225246` | 同步前原始 1578 题 |
| `interview_memory.db.bak_repair_20260918_230331` | 修复前（4001 题，含降级） |

还原方式：`cp <备份> G:/interview-memory/data/interview_memory.db`

## 脚本

| 脚本 | 用途 |
|---|---|
| `scripts/dedup_sync_practice.py` | 练习库去重 + 母库同步（`--apply` / `--thresh`；**无 `--model` 参数**） |
| `scripts/repair_answer_downgrade.py` | 答案降级补救（`--backup <同步前备份> [--apply]`） |
| `scripts/dedup_bank_088.py` | 母库去重（`--fresh` / `--model` / `--thresh` / `--apply`） |
| `scripts/test_embed_discriminative.py` | 嵌入模型短中文区分度快测（换模型先验证） |
