#!/usr/bin/env python3
"""Curate authored question data and render the selected full_v2 corpus.

The script is intentionally deterministic and idempotent.  It removes known
scraped fragments/duplicates, applies reviewed factual corrections, strips the
repeated "关键机制补全" boilerplate, and then renders authored JSONL to Markdown.
"""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

from reviewed_full_v2 import FIELD_FIXES, MERGED_INTO, MOVE_TO, OVERRIDES
from reviewed_followup_fixes import OVERRIDES as FOLLOWUP_OVERRIDES
from reviewed_manual_fixes import (
    MANUAL_ANSWER_OVERRIDES,
    MANUAL_DROP_IDS,
    MANUAL_MOVE_TO,
    MANUAL_TITLE_REWRITES,
)
from reviewed_reclassification_v3 import (
    DROP_IDS as RECLASSIFICATION_DROP_IDS,
    FIELD_FIXES as RECLASSIFICATION_FIELD_FIXES,
    MERGED_INTO as RECLASSIFICATION_MERGED_INTO,
    MOVE_TO as RECLASSIFICATION_MOVE_TO,
    OVERRIDES as RECLASSIFICATION_OVERRIDES,
    TITLE_REWRITES as RECLASSIFICATION_TITLE_REWRITES,
)
from reviewed_extra_v2 import (
    EXTRA_DROP_IDS,
    EXTRA_FIELD_FIXES,
    EXTRA_FRAGMENT_RE,
    EXTRA_MERGED_INTO,
    EXTRA_MOVE_TO,
    EXTRA_OVERRIDES,
    EXTRA_RANGE_MOVES,
    EXTRA_TITLE_REWRITES,
)

ROOT = Path(__file__).resolve().parent
AUTHORED = ROOT / "authored"
OUTPUT = ROOT / "full_v2"

AI_DOMAINS = {
    "agent": "Agent 架构与工程",
    "ai-product": "AI 产品与应用",
    "evaluation": "评估与可观测",
    "llm-basics": "大模型与 AI 基础概念",
    "llm-posttraining": "大模型后训练（微调/对齐）",
    "llm-pretraining": "大模型预训练",
    "multimodal": "多模态",
    "prompt": "提示工程",
    "rag": "RAG 与向量检索",
    "safety": "安全与沙箱",
}

# The remote corpus added these domains after the AI-only second pass.  Keep
# them in the same deterministic pipeline, but retain separately reviewed
# rules and a separate raw-record archive so provenance remains clear.
EXTRA_DOMAINS = {
    "algorithm": "算法与数据结构",
    "behavioral": "行为与项目面试",
    "design-pattern": "设计模式",
    "distributed": "分布式系统",
    "engineering": "工程化与 DevOps",
    "frontend": "前端工程",
    "general": "通用技术与职业问题",
    "go": "Go",
    "java": "Java",
    "mq": "消息队列",
    "mongodb": "MongoDB",
    "mysql": "MySQL",
    "os-network": "操作系统与网络",
    "puzzle": "智力与开放题",
    "redis": "Redis",
    "system-design": "系统设计",
}

DOMAINS = AI_DOMAINS | EXTRA_DOMAINS
ALL_MERGED_INTO = MERGED_INTO | EXTRA_MERGED_INTO | RECLASSIFICATION_MERGED_INTO
# Manual review (2026-09-20) wins: these moves and rewrites were applied in the
# app database first and are replayed here so --replace cannot revert them.
ALL_MOVE_TO = MOVE_TO | EXTRA_MOVE_TO | MANUAL_MOVE_TO | RECLASSIFICATION_MOVE_TO
ALL_OVERRIDES = OVERRIDES | EXTRA_OVERRIDES | MANUAL_ANSWER_OVERRIDES | RECLASSIFICATION_OVERRIDES | FOLLOWUP_OVERRIDES
ALL_FIELD_FIXES = FIELD_FIXES | EXTRA_FIELD_FIXES | RECLASSIFICATION_FIELD_FIXES


def write_crlf(path: Path, content: str) -> None:
    """Preserve the corpus' existing CRLF convention to keep diffs reviewable."""
    path.write_bytes(content.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))

# These are semantic duplicates of a better-scoped question, questions placed
# in the wrong domain, or unverifiable/current-product prompts that should not
# be presented as durable interview knowledge.
DROP_IDS = {
    # Agent: duplicate definitions, generic repeats, or fragments.
    "q0048", "q0120", "q1205", "q1207", "q1287", "q1357", "q1372",
    "q1411", "q1517", "q1648", "q1675", "q2091", "q2104", "q2935",
    "q2958", "q2959", "q2969", "q3928", "q3929", "q4007", "q4008",
    "q4009", "q4011", "q1375", "q1381", "q2165", "q2180",
    "q1691", "q1996", "q2018", "q2142", "q2951", "q2955", "q2982",
    "q2984", "q3428", "q3528", "q3654", "q3681", "q1376", "q2181",
    "q3516", "q3520",
    "q1579", "q1607", "q1745", "q2870", "q2883", "q2763", "q2766",
    "q2796", "q3165", "q0069", "q1100", "q1710", "q2119", "q2859",
    "q3734", "q3959", "q2187", "q2223", "q2868", "q3476", "q0077",
    "q0122", "q1149", "q1214", "q1297", "q1319", "q1439", "q1459",
    "q1480", "q1597", "q1611", "q1706", "q1717", "q1744", "q2107",
    "q2110", "q2232", "q2850", "q2875", "q2888", "q2892", "q2899",
    "q2923", "q2945", "q3418", "q3561", "q3592", "q3593", "q3666",
    "q3677",
    # Agent memory duplicates and compound/article prompts.
    "q1399", "q1506", "q1578", "q1739", "q2124", "q2150", "q2204",
    "q2210", "q2855", "q2990", "q3442", "q3468", "q3469", "q3470",
    "q3651", "q3936", "q3939", "q3976",
    # Generic MCP/Function Calling repeats.
    "q1337", "q1358", "q1365", "q1366", "q1407", "q1585", "q1718",
    "q1719", "q1720", "q1721", "q1723", "q1762", "q1765", "q2137",
    "q2218", "q2954", "q3907", "q3951", "q3985",
    # Multi-Agent repeats.
    "q1217", "q1221", "q1383", "q1392", "q1427", "q2885", "q2989",
    "q3415", "q3986",
    # Planning/workflow repeats.
    "q0115", "q1409", "q1520", "q1544", "q1734", "q2126", "q2862",
    "q3427", "q3445", "q3587", "q3971", "q2083", "q2887", "q3685",
    # RAG: duplicate definition/process/optimization/evaluation questions.
    "q1363", "q1528", "q1529", "q1802", "q1828", "q1917", "q1918",
    "q1922", "q1924", "q1959", "q2078", "q3017", "q3043", "q3550",
    "q3551", "q3614", "q3835", "q3940", "q3979", "q3982",
    # LLM basics: repeated Transformer/attention/KV/quantization/RoPE prompts.
    "q2261", "q3058", "q3701", "q3709", "q3711", "q3715", "q3724",
    "q3728", "q3730", "q3736", "q3737", "q3769", "q3770", "q3772",
    "q3870", "q3905", "q1747", "q1757", "q2174", "q2235", "q3692",
    "q2145", "q2303", "q2985", "q1512", "q3754", "q3766", "q2005",
    "q3126", "q3697", "q3845", "q3048", "q2312", "q3786", "q3227",
    "q1552", "q2300", "q1354", "q1644", "q1712", "q2275", "q2291",
    "q3115", "q1457",
    # Post-training: repeated generic LoRA/QLoRA/SFT/DPO/RAG comparisons.
    "q1122", "q1260", "q1422", "q1560", "q1911", "q2140", "q2176",
    "q2271", "q2272", "q2331", "q2345", "q3725", "q3741", "q3743",
    "q3758", "q3808", "q3814", "q3824", "q3825", "q3830", "q3839",
    "q3858", "q3897", "q3912", "q1539", "q2429", "q2333", "q1157",
    "q1314", "q3726", "q1315", "q3740", "q3750", "q2206", "q2318",
    "q3096", "q3915", "q1099", "q1443", "q1522", "q1852", "q1856",
    "q1132", "q3727", "q3756", "q3829", "q3210", "q2241", "q2253",
    "q3911", "q1313", "q1174", "q1325", "q1326", "q1487", "q3833",
    "q1119", "q1324",
    # Pre-training: duplicates and post-training questions in the wrong domain.
    "q3723", "q3809", "q3815", "q3899", "q1323", "q1593", "q3059",
    "q1462",
    # Multimodal questions duplicated by their dedicated domains.
    "q3803", "q3832", "q1165", "q1167", "q1168", "q1170", "q1176",
    # Prompt duplicates and malformed fragments.
    "q1332", "q2325", "q2329", "q2334", "q1564", "q3492", "q1653",
    "q1659", "q3211", "q3490", "q1299", "q2309", "q3507", "q3606",
    # Evaluation duplicates and RAG-specific items covered by the RAG domain.
    "q1845", "q3868",
    # Safety frontend questions.
    "q1874", "q1886", "q1898", "q1923", "q2924", "q3641",
    # Ambiguous article fragments and duplicated RAG/evaluation examples.
    "q1994", "q2189", "q2298", "q1808", "q1952", "q1993", "q1995", "q2070",
    "q2208", "q3003", "q3020", "q3021", "q3040", "q3041", "q3625",
    "q1371", "q1910", "q3801", "q2636", "q2592", "q3642", "q2259", "q2264",
    # RAG definition, chunking, retrieval and optimization repeats.
    "q1596", "q3002", "q1785", "q1582", "q2108", "q2998", "q1984",
    "q2996", "q3859", "q3941", "q3978", "q4006", "q3036",
    "q1158", "q1799", "q1954", "q2025", "q3025", "q3086", "q3599",
    "q3605", "q3639", "q3680", "q3906",
    "q0009", "q0039", "q0110", "q1166", "q1173", "q1262", "q1419",
    "q1523", "q1525", "q1526", "q1527", "q1600", "q1919", "q1928",
    "q1998", "q2016", "q2017", "q2209", "q4014", "q1456",
    # Safety duplicates or items owned by the Agent observability domain.
    "q1253", "q1106",
}

FRAGMENT_PATTERNS = [
    r"^\s*(本文|这篇文章|下一篇|前面|上面|此前|后来|以上\s*\d*|摘要[:：]|关键洞察[:：]|为什么重要[:：])",
    r"^\s*(一个直观的例子|翻译成大白话|常识/知识类|Part\s*\d|第\s*\d+\s*篇|下图|表\s*\d+)",
    r"^\s*(├──|workflows/|PM Agent|unsetunset|\$\s*npm)",
    r"(一张图看懂|手把手|万字干货|看完这|欢迎在评论区|本文将|本文从|本文全面|文章推荐|入门第一篇)",
    r"^(比如|例如|而对于|众所周知|想象一下场景|你可以这样类比|一句话总结[:：]|最后\s*A2A|整个过程|这就是|它们不是|步骤\s*\d+[:：])",
    r"(技术深度\s*⭐|术语混乱|可能是MCP|老王(来了|明显|抿|拧|咳|合上|接着|翻了|眼睛|第一问|最后一题|话锋)|师兄接着说)",
    r"(前端为什么选择\s*React|用过react吗|vue和react|React\s*(虚拟DOM|Fiber|Hooks)|redux|computed|服务端渲染)",
    r"(Canvas 更适用|align-items|align-self|Vue Router|attribute和property|Object\.defineProperty)",
    r"^\s*(这一节|但这里|记忆也是|结合面试表现|GitHub\s*一度|重构后的|现在很多人|我之前|我一开始|但我|我为|今天正好)",
    r"^\s*(这是一个|从《|这些不是|至少讲清|description[:：]|再者|接下来|本章|本书|让我们|我们的目标|我们会|我们通过)",
    r"^\s*(在此之前|那么我们|所以|不管|回到开头|好，背景|有同学会问|最近金三银四|原理\s+|加分点[:：]|适用场景\s+)",
    r"^\s*(成本与迭代|该技术通常|增强可解释性|ICL用|系统提示词定义|客服场景Prompt设计|把这几个块)",
    r"^\s*(偏好数据集|这种方法不仅|这个方案|然后把这些|召回算法问题|它与传统RAG|对比维度|逐行写出|进阶可通过)",
    r"^\s*(个人助手\s+|简单的文案|一个 Agent 执行任务时|get_tools_for_agent|Skill 模型知道|几千万并发沙箱)",
    r"^\s*(它|它们|这个|这些|这几个|这两个|前者|后者)\b",
    r"^\s*[“”\"「』]|^[🌟🔥📌🔑👀❓]+",
    r"(超\d+小时体系化AI课程|完整过一遍|从原理到线上落地|爆火开源|成果，通过AI Agent|从底层原理到如何从0)",
]
FRAGMENT_RE = [re.compile(pattern, re.IGNORECASE) for pattern in FRAGMENT_PATTERNS]

QUESTION_SIGNAL_RE = re.compile(
    r"什么|如何|怎么|为什么|哪些|是否|能否|区别|对比|介绍|解释|说明|设计|实现|"
    r"原理|作用|机制|流程|策略|方法|优缺点|权衡|选择|影响|问题|挑战|排查|优化|"
    r"评估|管理|处理|解决|保证|避免|控制|搭建|构建|调用|训练|推理|哪里|谁|多少|"
    r"何时|为何|讲讲|说说|谈谈|吗|呢",
    re.IGNORECASE,
)

TITLE_REWRITES = {
    "q2008": "在线 AI 产品的典型架构是什么？如何兼顾延迟、成本、稳定性与可观测性？",
    "q2190": "AI 编程普及后，前端与后端的核心差异还体现在哪里？",
    "q2287": "如何从产品经理视角构建一个可落地的 AI 产品？",
    "q2636": "ChatGPT 的基本原理是什么？它与普通 GPT 基座模型有什么区别？",
    "q3127": "为什么流式输出对 AI 产品体验很重要？工程上如何实现和治理？",
    "q3547": "如何讲述一个真实的 AI 落地项目，并说明难点、取舍与量化收益？",
    "q3548": "AI 编程场景下，如何管理有限的上下文窗口？",
    "q3617": "如何判断一个 AI 项目是科研原型还是真实生产落地？",
    "q3706": "AI 项目从模型 Demo 走向产品化，需要补齐哪些能力？",
    "q2013": "如何把 AI Demo 升级为生产级系统？",
    "q2071": "为什么幻觉是严肃 ToB 场景的核心风险？如何分层治理？",
    "q2099": "一套可持续迭代的 LLM Eval 体系应该如何搭建？",
    "q2263": "如何系统性降低大模型幻觉？",
    "q2282": "做 AI 系统架构选型时，应该比较哪些维度？",
    "q2298": "LLM 为什么会产生幻觉或不可靠输出？",
    "q2301": "理解 LLM 工作原理，如何帮助我们评估并缓解它的局限？",
    "q2858": "如何判断 Agent 给出的答案是否正确？",
    "q3499": "一个 RAG/Agent 项目应该如何设计 Eval？",
    "q3531": "分阶段开发多个 AI 模块时，如何分别验证并评估效果？",
    "q3631": "生成端如何评估答案忠实度与相关性？",
    "q3919": "如何公平比较不同架构、不同参数规模的基础模型？",
    "q3980": "内部评测集需要多少条数据？如何估算样本量？",
    "q2319": "如何扩展并优化大模型的上下文长度？",
    "q1784": "RAG 和长上下文有什么区别？应该如何选型？",
    "q1441": "工具描述应该如何设计，才能让 LLM 正确选择和调用工具？",
    "q3048": "零点量化（zero-point quantization）如何实现？",
    "q3049": "如何把模型量化为 GGUF？实施时要注意什么？",
    "q3053": "Transformers 中的推测解码如何实现？适用条件是什么？",
    "q3864": "PTQ 与 QAT 的原理和适用场景有什么区别？",
    "q3866": "如何根据硬件与质量要求选择量化方案？",
    "q2241": "经典 RLHF 通常包含哪些训练阶段？",
    "q2253": "RLHF 的强化学习阶段如何利用人类反馈？",
    "q2321": "DPO 与 SFT 在数据和训练目标上有什么区别？",
    "q3827": "PPO、DPO、GRPO 的核心原理、成本和适用场景有什么区别？",
    "q3828": "为什么完成 SFT 后仍可能需要偏好对齐或强化学习？",
    "q3829": "为什么仅靠 SFT 难以学习‘更好’的回答？",
    "q3917": "视觉语言模型如何通过图文对比学习进行预训练？",
    "q2908": "开放词汇目标检测与闭集目标检测有什么区别？",
    "q2160": "音频生成模型应该如何分类、评测和选型？",
    "q3335": "语音请求的数据量如何估算？哪些因素决定传输与存储成本？",
    "q1371": "RAG 是什么？它的核心链路有哪些？",
    "q1456": "RAG 最初解决了 LLM 的哪些核心问题？",
    "q1368": "常用 Embedding 模型应该如何对比与选型？",
    "q1646": "Context Engineering 与 Prompt Engineering 有什么区别？",
    "q3218": "Instruction Tuning 与 Prompt Learning 有什么区别？",
    "q3332": "OAuth 相比直接传递凭证有哪些安全优势？",
    "q3534": "现有 Skill 无法解决问题时如何兜底？模型输出如何安全对接工具代码？",
    "q2161": "LangChain 的核心架构由哪些模块组成？",
    "q2162": "为什么选择 LangGraph4j，而不是 Python 版 LangGraph？",
    "q2219": "Function Calling 为什么仍然属于 token 概率预测？",
    "q2981": "Skill 在 Sub-agent 中如何加载与执行？",
    "q2995": "Multi-Agent 系统中的执行 Agent 能否使用 Plan 模式？",
    "q2248": "为什么大模型会出现小模型没有的涌现能力？",
    "q2155": "提示词文件应该放在哪里？是否允许用户自定义？",
    "q1810": "文档达到百万级后，RAG 的存储与检索应该如何设计？",
    "q1811": "高维向量会如何影响检索延迟？应该怎样权衡维度与效果？",
    "q1830": "RAG 重排模型应该如何选型？",
    "q1837": "视频和音频内容应该如何检索？如何控制语音转文字成本？",
    "q1934": "什么是 Naive RAG？它的基本流程和局限是什么？",
    "q2847": "不同厂商的大模型 API 能否统一接入？需要处理哪些兼容性差异？",
    "q3222": "Llama 2 不同规模分别使用 MHA 还是 GQA？如何实现分组查询注意力？",
    "q3731": "vLLM 的 PagedAttention 如何减少传统 KV Cache 管理的显存碎片？",
    "q3331": "OAuth 授权码流程如何避免前端直接接触敏感凭证？",
    "q1391": "用户问题很短或语义不完整时，Agent 应如何消歧与补全？",
    "q1478": "如何系统性降低 Agent 的工具调用错误率？",
    "q2260": "如何用 Agent 设计一个可靠的游戏策划工具？",
    "q2896": "Agent 与传统 RPA 的核心区别是什么？二者如何组合？",
    "q3678": "LlamaIndex 主要解决什么问题？它与 LangChain 应该如何选型？",
    "q2044": "在百万级向量检索中，什么时候适合选择 HNSW？如何与其他索引比较？",
    "q2254": "Prompt Tuning 与 Prompt Engineering、全量微调有什么区别？",
    "q3489": "自动化评测体系的题库和标准答案应如何构建？如何支持动态更新？",
    "q1611": "直接调用大模型接口有哪些局限？Agent 在此基础上增加了什么能力？",
    "q2231": "为什么需要 Skill？它弥补了 LLM 的哪些原生能力边界？",
    "q3011": "如何用 ReAct Loop 实现多跳检索？怎样利用上一跳结果构造下一跳查询？",
    "q1613": "多个 Agent 并行运行时会发生哪些冲突？如何处理超时和局部失败？",
    "q2112": "把 AI Agent 部署到生产环境时，需要考虑哪些架构与治理问题？",
    "q2113": "如何控制 Agent 的调用成本？单次对话异常消耗大量 token 时如何处置？",
    "q2947": "子 Agent 应该共享全部工具吗？工具权限与动态授权应如何设计？",
    "q1573": "代码检索应该如何组合文本搜索、符号索引与语义检索？",
    "q1591": "Temperature、Top-k、Top-p 分别如何影响采样？参数应该怎样调优？",
    "q1595": "项目中应该如何比较并选择大模型？",
    "q2004": "模型文件与推理引擎分别是什么？为什么需要解耦？",
    "q3109": "模型权重或运行时显存放不下时，有哪些压缩、分片与卸载方案？",
    "q3129": "服务端如何把 LLM 的增量生成结果流式推送给客户端？",
    "q1159": "LLaVA 的视觉—语言对齐与指令微调分别训练哪些模块？MLP Projector 与 Q-Former 如何取舍？",
    "q1193": "Agent 执行多步副作用操作时，如何控制部分成功并实现回滚或补偿？",
    "q2029": "互联网网页 RAG 与本地文档 RAG 有哪些共同点和工程差异？",
    "q2074": "RAG 会被 Agent 取代吗？二者在系统中的关系是什么？",
    "q2105": "Agent 工具调用死循环应该如何检测和恢复？",
    "q3994": "移除大模型后，AI 平台还能保留哪些确定性能力？",
    "q3893": "DPO 的数学目标如何从带 KL 约束的 RLHF 目标推导出来？",
}

ALL_TITLE_REWRITES = (
    TITLE_REWRITES
    | EXTRA_TITLE_REWRITES
    | MANUAL_TITLE_REWRITES
    | RECLASSIFICATION_TITLE_REWRITES
)


def load_feishu_answers() -> dict:
    """飞书知识库答案覆盖表（由 scripts/build_feishu_overrides.py 生成）。

    手写整理的《计算机知识库》答案最贴近真实面试口径，优先于 AI 生成的默认答案；
    已经过人工勘误的 ANSWER_REWRITES 仍然优先，避免把已修正的事实错误倒回去。
    """
    path = ROOT / "feishu_answers.json"
    if not path.exists():
        return {}
    records = json.loads(path.read_text(encoding="utf-8"))
    return {qid: rec for qid, rec in records.items() if str(rec.get("answer", "")).strip()}


FEISHU_ANSWERS = load_feishu_answers()


def feishu_source(qid: str) -> str:
    return str(FEISHU_ANSWERS.get(qid, {}).get("source", ""))


def apply_feishu_answer(item: dict, record: dict) -> None:
    item["answer"] = record["answer"]
    item["answer_source"] = record["source"]
    if record.get("chapter"):
        item["chapter"] = record["chapter"]

META_REWRITES = {
    "q1161": {
        "kaodian": "考察 CLIP 对称 InfoNCE、可学习温度，以及 SigLIP 逐对 sigmoid loss 的区别与工程含义。",
        "framework": "1) 图文双塔与批内正负样本；2) 对称 InfoNCE；3) logit scale 与温度的方向；4) SigLIP 的逐对 sigmoid loss 和可学习 bias；5) batch 与跨设备归一化的取舍。",
    },
    "q1168": {
        "kaodian": "考察 MoE 推理中总参数存储、激活参数计算、专家并行通信和小 batch 利用率之间的区别。",
        "framework": "1) 服务副本需要可访问全部专家，但可跨卡分片、缓存或卸载；2) 激活参数主要决定单 token 计算量；3) all-to-all 与路由不均；4) 小 batch 下算术强度低；5) 专家并行、grouped GEMM、量化与卸载的权衡。",
    },
    "q2160": {
        "kaodian": "考察是否能按音频任务拆分模型类别，并用可复现的业务评测代替不带版本的‘最好’结论。",
        "framework": "1) 拆分 ASR、TTS、声音克隆、音乐和音效；2) 明确语言、延迟、成本、部署与授权约束；3) 用真实样本做主客观评测；4) 记录模型版本与测试日期；5) 核对版权、同意机制与 SLA。",
    },
    "q1064": {
        "kaodian": "考察 QLoRA 的 4-bit 冻结基座、LoRA 适配器、NF4、双重量化和分页优化器，以及显存结论的适用条件。",
        "framework": "1) 4-bit 存储与计算精度的区别；2) 冻结基座、只训练 LoRA；3) NF4、double quantization、paged optimizers；4) 显存还受序列长度、batch、rank 和实现影响；5) 量化后必须做任务与通用能力回归。",
    },
    "q1441": {
        "kaodian": "考察工具描述、上下文、候选工具集和运行时校验如何共同影响工具选择，而不是把描述当作唯一依据。",
        "framework": "1) name/description/schema 写清能力与边界；2) 系统指令、历史和候选集同样影响选择；3) 相似工具的互斥描述；4) schema、业务和权限校验；5) 用工具选择与参数正确率回归验证。",
    },
    "q1784": {
        "kaodian": "考察 RAG 与长上下文的机制、成本、适用任务和组合方式，并能区分 FlashAttention 的 IO 优化与理论计算复杂度。",
        "framework": "1) 长上下文直接装入材料，RAG 按需检索；2) 精确注意力仍是 O(n²) 计算；3) FlashAttention 优化 IO 和显存，不是线性注意力；4) 比较成本、延迟、更新与溯源；5) 生产中常组合。",
    },
    "q3547": {
        "kaodian": "考察能否基于真实经历讲清业务背景、技术取舍、验证方法和可追溯指标，避免把示例案例冒充个人成果。",
        "framework": "1) 真实背景与约束；2) 两三个核心难点；3) 方案与被放弃方案；4) 评测集、指标和上线验证；5) 只报告有口径的真实数据；6) 复盘与剩余风险。",
    },
    "q3617": {
        "kaodian": "考察能否用用户、真实数据、SLA、评测闭环和业务结果区分科研原型与生产落地。",
        "framework": "1) 是否进入真实业务流程；2) 是否接入真实数据和权限；3) 是否具备 SLA、监控、成本和容量治理；4) 是否有灰度、兜底和 badcase 闭环；5) 原型阶段如实说明已验证假设与待补能力。",
    },
    "q1176": {
        "kaodian": "考察 Mamba 中输入相关的 B、C、Δ，固定的连续时间 A，以及 selective scan 如何兼顾内容选择与线性复杂度。",
        "framework": "1) 传统 SSM 的参数不随 token 内容变化；2) Mamba 让 B、C、Δ 由输入生成，A 通常仍是学习到的固定参数；3) 大 Δ 更快衰减历史，小 Δ 更保留历史；4) 选择性系统不能直接用固定卷积核；5) 用并行 scan 实现高效训练。",
    },
    "q3888": {
        "kaodian": "考察 Mamba 的选择性 SSM 与普通 RNN 的共同点和差异，尤其是哪些参数输入相关以及并行 scan 的意义。",
        "framework": "1) 两者都有固定大小的递归状态；2) Mamba 的 B、C、Δ 输入相关，连续时间 A 通常固定；3) 离散转移因 Δ 而随 token 变化；4) 大 Δ 更快遗忘历史，小 Δ 更保留历史；5) 结构化线性递推支持硬件友好的并行 scan。",
        "追问": "为什么输入相关的选择性 SSM 不能直接写成固定卷积核？selective scan 如何并行化递推？",
    },
    "q2847": {
        "kaodian": "考察是否能区分统一适配层与厂商原生协议，避免把所有模型 API 说成完全兼容 OpenAI。",
        "framework": "1) 多数服务使用 HTTP/JSON，但字段和语义不完全一致；2) 用 provider adapter 统一内部接口；3) 处理消息、工具调用、流式事件和错误码差异；4) 做能力探测与版本测试；5) 保留厂商特性的扩展字段。",
    },
    "q2991": {
        "kaodian": "考察上下文压缩的触发依据、预算组成和信息保真策略，不能把固定百分比或某个产品窗口当成通用结论。",
        "framework": "1) 按模型真实 tokenizer 计算总预算；2) 为输出、工具结果和 RAG 预留空间；3) 用滑窗、摘要、结构化状态和外部检索组合；4) 触发阈值由历史长度分布与任务回归确定；5) 保护系统指令和关键约束。",
    },
    "q3222": {
        "kaodian": "考察 Llama 2 各规模的注意力配置，以及 MHA、GQA 的张量形状和 KV 共享方式。",
        "framework": "1) 全系列都是 decoder-only 因果自注意力；2) 7B/13B 使用 MHA，70B 使用 GQA；3) GQA 保留多个 Q 头、减少 KV 头；4) 用 repeat/broadcast 把 KV 对齐到 Q 头；5) 说明 KV Cache 与质量权衡。",
    },
    "q3731": {
        "kaodian": "考察 PagedAttention 的块式 KV Cache、逻辑到物理映射和按需分配，以及它只能减少而非彻底消除碎片。",
        "framework": "1) 连续预分配造成内部与外部浪费；2) KV 切成固定 token block；3) block table 映射逻辑序列到非连续物理块；4) 按需分配、回收和共享前缀；5) 仍有尾块、元数据和调度开销。",
    },
    "q3678": {
        "kaodian": "考察 LlamaIndex 与 LangChain 的能力重心、重叠范围和按项目约束选型的方法，避免绝对化地指定框架。",
        "framework": "1) LlamaIndex 偏数据接入、索引与检索；2) LangChain 偏模型、工具与工作流编排；3) 两者能力有重叠且可组合；4) 按现有代码、团队经验、可观测性和扩展需求选型；5) 先做最小验证，避免框架锁定。",
    },
    "q2044": {
        "kaodian": "考察 HNSW、IVF、量化索引和精确检索的机制与选型条件，避免把某种索引说成普遍最优。",
        "framework": "1) 先明确规模、维度、召回、延迟、内存、更新和过滤需求；2) HNSW 的分层近邻图；3) 高召回低延迟与高内存、慢构建的权衡；4) 对比 Flat、IVF/IVF-PQ 和磁盘型索引；5) 用真实数据压测参数。",
    },
    "q1159": {
        "kaodian": "考察 LLaVA 分阶段训练中冻结策略的变化，以及 MLP Projector 和 Q-Former 在信息保留、压缩与计算成本上的取舍。",
        "framework": "1) 区分预训练对齐阶段与视觉指令微调阶段；2) 第一阶段通常冻结视觉编码器和 LLM、训练 projector；3) 原始 LLaVA 第二阶段通常更新 projector 与 LLM、保持视觉编码器冻结；4) MLP 保留更多视觉 token 且结构简单；5) Q-Former 用可学习 query 压缩视觉信息。",
    },
    "q1591": {
        "kaodian": "考察 temperature、top-k、top-p 的数学作用和联合调参方法，避免把经验参数写成跨模型通用的最佳值。",
        "framework": "1) temperature 缩放 logits；2) top-k 固定候选数量；3) top-p 按累计概率动态截断；4) 参数交互与实现差异；5) 用任务评测和固定随机种子调优。",
    },
    "q1595": {
        "kaodian": "考察能否从业务质量、延迟、成本、能力、合规和运维约束出发做可复现的模型选型，而不是背诵易过时的产品排名。",
        "framework": "1) 明确任务与硬约束；2) 建立真实业务评测集；3) 测质量、延迟、吞吐、成本与稳定性；4) 核对工具调用、多模态、上下文和私有化能力；5) 固定版本、灰度发布并保留回退。",
    },
    "q1573": {
        "kaodian": "考察代码检索中精确文本、符号关系和语义意图三类需求，以及组合检索而非二选一的工程方案。",
        "framework": "1) grep/rg 适合已知字符串与正则；2) LSP/AST/代码图适合定义、引用和调用关系；3) embedding 适合自然语言描述的概念检索；4) 用结构化结果约束 LLM；5) 按查询类型路由并评测召回。",
    },
}


ANSWER_REWRITES = {
    "q1590": """大模型解码可分为确定性搜索与随机采样，选择依据是任务是否需要唯一、稳定的答案，以及是否需要多样性。\n\n1. 贪心解码：每步选概率最大的 token，速度快、结果稳定，但可能陷入局部最优或重复。适合抽取、分类式生成和强调可复现的场景。\n\n2. Beam Search：每步保留若干条累计得分最高的序列，适合机器翻译、语音识别等候选序列可比较的任务；代价是计算、显存随 beam 数增加，开放式对话中还可能产生安全但平庸的文本。\n\n3. 随机采样：按概率抽样，通常配合 temperature、top-k、top-p。温度越低分布越尖锐，top-k 限制固定候选数，top-p 保留累计概率达到阈值的最小候选集合。适合创意写作和需要多个候选答案的场景。\n\n这些策略可以组合。例如 Hugging Face Transformers 中 `do_sample=True` 且 `num_beams>1` 是 beam sampling，并不要求 `num_beams=1`。实际选型要用任务指标评估，同时设置最大长度、停止词和重复惩罚，不能把“低温”误当成事实正确性的保证。""",
    "q1161": """CLIP 用图像编码器和文本编码器把配对图文映射到同一归一化向量空间。一个 batch 中，匹配图文是正样本，其余组合是批内负样本；训练分别做“图找文”和“文找图”的交叉熵，再对两个方向取平均，这就是对称 InfoNCE。\n\n相似度 logits 通常写成 `exp(logit_scale) * cosine_similarity`，等价于余弦相似度除以温度 τ。尺度越大（温度越小），softmax 分布越尖锐。实现中限制的是指数化后的 logit scale 上限，而不是把温度本身简单裁剪到同一区间。\n\nSigLIP 不再对整行或整列做 softmax，而是把每个图文对独立看成正负二分类，使用 sigmoid loss，并加入可学习 bias 缓解负样本数量远多于正样本的问题。这样不需要跨设备收集全局 softmax 归一化项，在较小 batch 下也能有效训练、扩展更方便；但它并不意味着 batch 大小完全无关，也不能据此断言单机必须或天然能使用 32k 以上 batch。""",
    "q1168": """MoE 推理的核心矛盾是“每个 token 只激活少量专家，但服务仍要能访问全部专家权重”。在不做卸载或专家缓存时，一个副本的设备集通常需要容纳全部专家，因此容量规划主要看总参数；这不等于每张 GPU 都要复制所有专家，也不等于所有权重必须永远常驻显存。工程上可以用专家并行分片、CPU/NVMe offload、按热度缓存和量化，在容量与延迟之间取舍。\n\n第二个瓶颈是通信。专家并行会先按路由结果把 token all-to-all 分发到不同设备，专家计算后再聚合。自回归 decode 时每步 token 少、batch 小，单个专家拿到的 token 更少，矩阵乘法难以吃满 GPU，固定通信延迟就会占主导。路由不均还可能造成热点专家拖慢整批请求。\n\n常见优化包括：让专家并行尽量位于高带宽互联域内；用 grouped GEMM 合并小矩阵；做通信与计算重叠；提高连续批处理规模；限制或均衡专家容量；再结合量化、专家缓存或卸载。回答时应区分“总参数影响整个服务副本的存储需求”和“激活参数决定单 token 的主要计算量”。""",
    "q1784": """长上下文与 RAG 都能让模型利用更多信息，但路径不同：长上下文把材料直接放入一次请求，RAG 把材料放在外部知识库中，按问题检索少量片段再注入上下文。\n\n标准的精确自注意力时间复杂度仍是 O(n²)。FlashAttention 通过分块和 online softmax 减少 HBM 读写及中间注意力矩阵的显存占用，通常显著加速并把额外显存降到近线性，但没有把精确注意力的理论计算量变成 O(n)。真正改变渐进复杂度的是滑动窗口、稀疏注意力、线性注意力等结构，它们会改变可见范围或采用近似。\n\n长上下文适合材料规模可控、需要跨段整体推理的任务，但输入成本、首 token 延迟和 KV Cache 会随长度增加，还存在 Lost in the Middle。RAG 适合知识量大、更新频繁、需要引用溯源的场景，代价是检索、切块和重排质量决定上限。生产中常组合使用：RAG 先缩小候选材料，再让长上下文模型做跨片段推理。""",
    "q1441": """工具描述会显著影响模型是否选对工具和参数，但它不是唯一依据。模型还会受到用户请求、系统指令、对话历史、当前可见工具集合、few-shot 示例和运行时反馈影响。\n\n设计工具契约时，应让 name、description 和 JSON Schema 一起回答四件事：工具做什么；何时调用；何时不要调用；参数与返回值有哪些约束。功能相近的工具要写清互斥边界，并尽量只向模型暴露当前任务相关的候选集。\n\n可靠性不能只靠描述。运行时还要做 schema 校验、业务校验和权限校验；信息不足时允许模型澄清；执行失败时回传结构化错误并限制重试；高风险动作要求确认或审批。评估时用真实请求建立工具选择与参数正确率回归集，才能判断描述修改是否有效。""",
    "q3530": """处理 Agent State 并发修改，先把状态按语义拆分，再选择乐观锁、串行化或可合并数据结构，不能把 event sourcing 的 append-only 误解为天然没有冲突。\n\n存储层可给状态加 version/revision，用 CAS 或 `UPDATE ... WHERE version=?` 做乐观并发控制；冲突低时重读、合并、重试，冲突高且合并代价大时再考虑队列串行化或短期悲观锁。工具副作用必须使用幂等键，避免重试造成重复下单、发消息或写库。\n\n事件溯源把变更记录成追加事件，能保留审计历史并支持重放，但多个写入者仍可能基于同一旧版本产生语义冲突，事件的全序、聚合版本和业务不变量仍需显式控制。CRDT 只适合满足相应合并代数的数据类型；“最后写入获胜”也会丢失业务信息。\n\n多 Agent 场景最好让子 Agent 写私有结果，再由确定性的 reducer 按字段合并。能自动裁决的用规则，语义矛盾保留双方证据交给仲裁或人工，不要静默覆盖。""",
    "q3534": """现有 Skill 无法解决问题时，Agent 应先判断是缺信息、缺能力、执行失败还是越权：缺信息就澄清；缺能力就选择已授权的替代工具或明确说明限制；短暂失败可有限次重试；高风险或超权限任务转人工，不能编造已完成。\n\n模型与后续代码应通过明确契约连接。优先使用 tool calling 或支持 JSON Schema 的 structured output，让模型产生工具名与参数；服务端仍要做类型、枚举、业务和权限校验。普通 JSON mode 通常只提高“输出是合法 JSON”的概率或保证语法合法，并不等于字段一定符合业务 schema，更不保证值在语义上正确。\n\n解析或校验失败时，把机器可读的错误回灌给模型，设置重试上限；常见格式问题可以确定性修复，但 ID、金额、权限等业务字段不能由模型猜。核心原则是生成、校验、执行三层分离。""",
    "q3557": """CLI 是面向人和脚本的命令行接口；MCP 是面向 AI 应用的客户端—服务器协议，用统一方式发现和调用 tools、读取 resources、使用 prompts。两者不是替代关系：成熟 CLI 完全可以被 MCP Server 包装复用。\n\nMCP 消息基于 JSON-RPC 2.0。当前远程传输应优先描述为 Streamable HTTP，本地集成常用 stdio；早期独立的 HTTP+SSE 双端点传输属于兼容性/历史方案，不应笼统地说成当前标准只有“HTTP/SSE”。\n\nCLI 主要靠命令名、参数、退出码和文本流；MCP 还提供能力协商、工具 schema、结构化错误与生命周期管理。无论用哪一种，鉴权、参数校验、超时、权限和副作用控制都必须由宿主与执行侧强制实现。""",
    "q2160": """比较市面模型时，不应给出一个不带版本和日期的“最好”结论。先按任务拆分：音频至少分为语音识别、语音合成、语音克隆、音乐生成和音效生成，它们的模型、指标和合规风险都不同。\n\n选型可分三步。第一，定义硬约束：语言和方言、是否流式、端到端延迟、可接受成本、并发量、部署区域、数据是否能出域、商用授权。第二，用真实业务样本比较：TTS 看主观 MOS、可懂度/WER、说话人相似度、首包延迟与实时率；音乐或音效还要看可控性、长程一致性、FAD/CLAP 等辅助指标。第三，做盲测和小流量 A/B，并记录候选模型的具体版本、测试日期和参数。\n\n闭源产品更新很快，公开榜单只能用于初筛；最终结论应写成“在某日期、某数据集、某预算与延迟约束下，候选 A 的综合结果最好”，而不是长期宣称某产品第一。企业落地还必须核对训练数据与生成内容的授权、声音克隆同意机制、水印、审计和供应商 SLA。""",
    "q1064": """QLoRA 的核心是：把冻结的预训练权重以 4-bit 形式存储，前向时反量化到计算精度，同时只训练 LoRA 低秩适配器，因此主要节省基座权重和优化器相关显存。\n\n经典 QLoRA 有三项关键技术：NF4 针对近似正态分布的权重设计量化码；double quantization 再量化量化常数；paged optimizers 利用统一内存缓解长序列或大 batch 带来的显存峰值。4-bit 是存储格式，不代表矩阵乘法始终以 4-bit 完成，也不代表精度必然无损。\n\nQLoRA 论文展示的是在一张 48GB GPU 上微调 65B 模型；能否在单卡训练某个规模，取决于显存、序列长度、batch、LoRA rank、梯度检查点和实现。面试中不要把它概括成“任意 7B 到 70B 都能在普通单卡训练”。最终质量必须在目标任务和通用能力回归集上验证。""",
    "q3547": """这是一道项目经历题，不能把虚构案例和指标当成自己的真实经历。回答时选一个确实参与过的项目，用“背景—约束—方案—验证—结果—复盘”展开。\n\n1. 背景：说明用户、原流程和业务目标，避免只说“做了一个 Agent”。\n2. 难点：只选两三个最关键的问题，例如长尾数据、检索召回、工具误调、延迟成本或合规。\n3. 方案与取舍：讲清为什么采用 RAG、微调、规则、模型级联或人工兜底，并给出被放弃方案及原因。\n4. 验证：说明评测集如何构建，使用什么离线指标、线上护栏与 A/B 方法。\n5. 结果：只引用真实可追溯的数据，标明统计口径、时间窗口、样本量和基线；没有线上数据就诚实说是原型或离线实验。\n6. 复盘：说明哪项假设被证伪、哪里仍有风险、下一步怎么做。\n\n一个合格答案的重点不是数字越大越好，而是指标能解释：例如成本下降是因为模型路由还是缓存，准确率提升是否有置信区间，人工效率是否把审核成本算进去。任何示例数字都应明确标为示意，不能冒充个人项目成果。""",
    "q3617": """判断项目是否真实落地，要看是否进入真实用户与业务流程，而不是看是否用了热门模型。回答应基于自己的项目事实，不要先假设“项目 1 已规模化上线”。\n\n可以从五个证据判断：第一，有明确用户、使用频次和要解决的原流程；第二，接入真实数据与权限体系，而非只跑公开样例；第三，有 SLA、监控、告警、成本和容量规划；第四，有离线评测、灰度、人工兜底和 badcase 闭环；第五，有可核验的业务结果及统计口径。\n\n如果目前只是科研或 Demo，也可以如实回答：说明已经验证了哪些假设、尚缺哪些生产条件，以及从原型走向上线需要补齐的数据治理、鉴权、幂等、降级、审计和运维工作。面试官更关注边界意识和推进计划，而不是把原型包装成上线项目。""",
    "q1176": """传统线性时不变 SSM 对不同 token 使用同一组状态更新参数，擅长高效压缩序列，却难以根据内容决定“保留什么、忽略什么”。Mamba 的关键改进是选择性：B、C 和离散化步长 Δ 由当前输入生成；连续时间状态矩阵 A 通常仍是学习到的固定参数。由于离散转移 `exp(ΔA)` 会随 Δ 变化，实际状态更新仍然是输入相关的时变系统。\n\nΔ 可以理解为当前 token 对时间尺度的控制。较大的 Δ 会让旧状态更快衰减、更多吸收当前输入；较小的 Δ 更接近保留旧状态、弱化当前输入。B 决定怎样把当前输入写入状态，C 决定怎样从状态读出，因此模型能按内容选择记忆和输出。\n\n这种输入相关性也意味着它不能像线性时不变 SSM 那样直接化成一个固定卷积核。Mamba 使用硬件感知的 selective scan，在训练时对结构化线性递推做并行扫描，推理时保持固定大小状态递归更新。序列计算量随长度近线性增长，但固定状态仍是有损压缩，精确复制和随机访问能力通常不如显式全注意力。""",
    "q3888": """Mamba 和 RNN 都维护固定大小的隐状态，并在推理时递归更新；因此不能简单说 Mamba 与 RNN“本质完全不同”。关键差异在状态更新的结构和并行实现。\n\n经典 RNN 用非线性单步递推，例如 `h_t=tanh(W_h h_{t-1}+W_x x_t)`，时间维依赖强，常规训练难以并行。Mamba 使用结构化线性状态空间递推，连续时间 A 通常是固定的学习参数，而 B、C、Δ 由输入生成。Δ 参与离散化后，离散状态转移随 token 改变：大 Δ 更快衰减历史并吸收当前输入，小 Δ 更保留历史；B 控制写入，C 控制读出。\n\nMamba 的 selective scan 利用这种结构做并行前缀扫描，并通过 kernel fusion 减少 HBM 往返，因此训练可以高效并行、推理保持常数大小状态。它没有随序列增长的 KV Cache，但固定状态会压缩历史，不等价于 Transformer 对所有历史 token 的显式随机访问。回答时不要说 A、B、C、Δ 全都由输入生成，也不要把 Δ 说成固定时间步。""",
    "q2847": """不同厂商通常都提供 HTTP/JSON API，但不能假设它们完全兼容 OpenAI 协议。消息角色、系统提示、图像与音频输入、tool calling、structured output、流式事件、token 统计、错误码和限流语义都可能不同；即使提供 OpenAI-compatible 端点，也常只覆盖协议子集。\n\n工程上应在业务代码和厂商 SDK 之间加一层 provider adapter，内部统一请求、响应、流式事件和错误模型，再为各厂商做显式转换。启动或发布前跑能力探测与契约测试，例如是否支持并行工具调用、JSON Schema、取消请求和 prompt caching。\n\n统一层不能抹掉所有差异：厂商独有能力通过扩展字段暴露，调用方按 capability 选择模型；版本升级要固定模型标识并做回归。这样才能做到可切换，而不是简单更换 base_url、api_key 和 model 就认为行为一致。""",
    "q2991": """上下文压缩不是达到固定轮数或固定百分比就机械触发，而是按 token 预算和任务风险决定。预算要包含 system、历史、当前输入、工具 schema、RAG 片段和预期输出，并使用目标模型的真实 tokenizer 计算。\n\n常见组合是：最近对话保留原文；较旧内容做滚动摘要；用户偏好、已确认事实、计划和工具结果写成结构化状态；更远历史外部化后按需检索。系统指令、当前目标和不可丢失约束应单独保护，摘要要保留来源或可回查句柄，避免错误被永久固化。\n\n触发阈值应由线上长度分布、模型最大窗口、最大输出和工具返回上限反推，并通过长对话回归集验证。所谓 70%—85% 只能是起始经验，不是通用规则；模型窗口和产品配置也会变化，不应把某个型号的当前数字写成长期结论。""",
    "q3222": """Llama 2 全系列都是 decoder-only 的因果自注意力，但注意力头配置并不完全相同：公开的 7B 和 13B 使用标准 MHA，70B 使用 GQA 来减少 KV Cache 和内存带宽。因此不能笼统说“Llama 2 都使用 GQA”。\n\nMHA 中 Q、K、V 都有 H 个头；GQA 保留 H 个 Query 头，但只有 G 个 Key/Value 头，其中 `1 < G < H`。每组 `H/G` 个 Query 头共享一组 K/V。实现时先把 Q reshape 为 `[B,H,T,D]`，K/V 为 `[B,G,T,D]`，再按组 broadcast 或 `repeat_interleave` 到 Query 头维度后计算因果注意力。\n\n当 G=H 时是 MHA，G=1 时是 MQA。KV Cache 大小大致按 `G/H` 缩减，代价是一定的表示共享；组数需要用质量、吞吐与显存回归共同确定。""",
    "q3731": """PagedAttention 借鉴虚拟内存分页，把每条序列的 KV Cache 切成固定 token 数的 block。逻辑序列通过 block table 指向可分散在显存中的物理块，因此请求不需要预留一段按最大长度计算的连续显存，生成时按需申请，结束后逐块回收。\n\n它主要减少两类浪费：按最大生成长度预留造成的内部浪费，以及连续块反复申请释放造成的外部碎片；还便于 beam 或共享前缀通过引用计数复用 block。这样能显著提高可用于 batching 的 KV 容量。\n\n但“消除碎片”或“显存利用率接近 100%”都说得过头。最后一个未填满的 block 仍有尾部浪费，block table、引用计数、调度和 kernel 访问也有开销。block 太大浪费更多，太小则元数据与寻址成本更高，实际需要按模型和工作负载调优。""",
    "q3678": """LlamaIndex 的能力重心是把外部数据接入大模型应用：加载和解析数据、切分为节点、构建向量或其他索引、检索、重排，再把证据交给模型生成。LangChain 的能力重心更偏模型调用、工具封装、链与 Agent/工作流编排。两者都在扩展，边界并不绝对，也可以组合使用。\n\n选型不能简化成“做 RAG 就一定用 LlamaIndex”。如果核心难点是多源文档解析、索引和复杂检索，LlamaIndex 的抽象通常更直接；如果核心难点是多工具流程、状态机和模型编排，LangChain/LangGraph 或自研编排可能更合适。简单 RAG 也可能只需要原生 SDK、向量库客户端和少量业务代码。\n\n最终要比较现有技术栈、团队经验、异步与流式支持、可观测性、版本稳定性、二次开发成本和供应商锁定风险。先用真实数据做最小验证，再决定是否引入框架，而不是根据框架宣传下结论。""",
    "q2044": """HNSW 用分层可导航近邻图做近似最近邻搜索：上层稀疏图负责快速接近目标区域，底层稠密图负责精细搜索。它常能在内存充足时取得较高召回和较低查询延迟，也支持增量插入，因此是百万级向量检索的常见候选，但不是普遍意义上的“最佳方案”。\n\n它的主要代价是图边带来的较高内存占用、索引构建成本，以及删除和大规模更新的维护复杂度。`M` 影响图连接数和内存，`efConstruction` 影响构建质量与耗时，`efSearch` 影响查询召回与延迟；这些参数没有脱离数据集的固定最优值。\n\n选型要比较约束：数据量较小或要求精确结果时可用 Flat；内存紧张、数据规模更大时可考虑 IVF-PQ 等压缩索引；数据远超内存时可评估磁盘型 ANN；强过滤、高更新率还要单独测试索引与过滤器的协同效果。最终应在真实向量分布和过滤条件下测 Recall@k、p95/p99 延迟、内存、构建时间与更新成本，再决定是否选择 HNSW。""",
    "q1159": """LLaVA 不能概括成“始终冻结 LLM、只训练 Projector”。以原始 LLaVA 的两阶段训练为例：第一阶段做视觉—语言特征对齐，通常冻结视觉编码器和 LLM，只训练线性 projector；第二阶段做视觉指令微调，通常仍冻结视觉编码器，但更新 projector 和 LLM。具体冻结策略会随版本和训练方案变化，回答时应明确所指阶段。\n\nMLP projector 直接把视觉编码器的 patch 特征映射到 LLM embedding 空间，结构简单、训练和推理开销低，也保留较多视觉 token。它的代价是长高分辨率输入会产生较多 token，把筛选和融合压力交给 LLM。Q-Former 用少量可学习 query 通过交叉注意力从视觉特征中抽取固定数量表示，能够压缩 token、隔离模态，但增加模块复杂度和计算，也可能因固定 query 数形成信息瓶颈。\n\n因此两者没有脱离任务的绝对优劣。需要细粒度 OCR、定位或高分辨率理解时，要关注压缩是否丢细节；更关注延迟、实现简单和大规模数据训练时，MLP 可能更合适。最终应同时比较任务质量、视觉 token 数、首 token 延迟、吞吐和显存。""",
    "q1591": """Temperature 在 softmax 前缩放 logits：大于 1 时分布更平，小于 1 时更尖；top-k 只保留概率最高的 k 个候选；top-p 保留累计概率达到阈值的最小候选集合。随后对保留集合重新归一化并采样。不同推理框架的过滤顺序、默认值和 temperature=0 的处理可能不同，应以具体 API 为准。\n\n不存在跨模型、跨任务通用的“最佳设置”。抽取、代码补全或格式严格的任务通常从确定性解码或较低随机性开始；创意生成可逐步提高多样性。低温只会让分布更集中，不会保证事实正确；同时大幅修改多个参数也会让归因困难。\n\n调优时先固定模型版本、prompt、停止条件、随机种子策略和评测集，每次只改变一个主要参数，比较任务质量、格式通过率、多样性与稳定性。生产环境还要记录实际参数，因为供应商默认值和实现可能随接口而异。""",
    "q1595": """模型选型应从业务约束出发，而不是先列品牌或引用一张会过时的排行榜。先明确任务类型、语言、上下文长度、工具或多模态需求、数据是否允许出域、目标延迟、并发量和预算，再筛出满足硬约束的候选模型。\n\n用真实业务样本建立版本化评测集，至少比较任务成功率或 rubric 得分、事实与安全错误、结构化输出和工具调用正确率、TTFT、端到端 p95/p99 延迟、吞吐、单次成功请求成本和限流稳定性。闭源 API 要固定可用的模型版本并验证升级行为；自部署模型还要把 GPU、容量冗余和运维人力计入总成本。\n\n最终结论应写成“在某个版本、日期、数据集和约束下选择候选 A”，并保留灰度、回归与回退机制。简单任务可路由到较小模型，复杂任务升级到更强模型，但路由收益必须用端到端成功率和总成本验证。面试回答只讲自己真实测过的候选和数据，不虚构项目选择。""",
    "q1573": """代码检索不是 grep 与 RAG 二选一，而是先判断查询类型。已知标识符、错误码、配置键或正则模式时，`rg`/grep 的字面搜索快、确定、可复现；查定义、引用、类型关系和调用链时，LSP、AST 索引或代码图比纯文本更准确；用户只描述业务意图、不知道命名时，embedding 或混合检索有助于召回语义相近的候选。\n\n语义检索的结果是近似候选，不能直接当成事实。可靠链路通常是：语义召回缩小范围，再用文本搜索、符号解析和实际文件内容验证，最后让 LLM 解释；回答中的路径、符号和行号应来自工具结果，而不是模型生成。代码变更后还要增量更新索引，并按仓库、权限和版本过滤。\n\n评测时按查询类型分别统计 Recall@k、定义/引用命中率、索引新鲜度和端到端定位成功率。小仓库或精确查询可能完全不需要向量库；大型异构仓库的自然语言检索才更可能从语义索引中获益。""",
    "q2004": """模型文件保存权重及其配置，常见格式包括 safetensors、GGUF 等；tokenizer、架构代码和生成配置有时同包提供，有时需要单独文件。它描述“参数和结构是什么”，本身不会完成请求调度和高效执行。\n\n推理引擎负责加载和放置权重、执行算子、管理 KV Cache、批处理与调度，并实现量化 kernel、张量并行、采样和流式输出等能力。服务层还会在引擎之外增加鉴权、限流、路由和监控，因此推理引擎也不等同于完整的 API 服务。\n\n二者解耦后，同一权重可以在兼容的不同硬件和引擎上运行，但“格式可读取”不代表所有算子、量化方式和模型架构都受支持。转换格式、量化、kernel 和采样实现也可能造成性能或数值差异，换引擎后仍需做输出质量、吞吐、延迟和显存回归。""",
    "q3109": """先区分显存花在哪里：推理主要包括模型权重、KV Cache、临时工作区和批处理开销；训练还包括梯度、激活和优化器状态。不同瓶颈对应不同方案，不能只说“量化”。\n\n减少权重体积可用低比特量化、结构化剪枝、稀疏化、低秩分解或知识蒸馏。量化最常用，但能否加速取决于硬件与 kernel，实际显存还包含量化元数据和运行时开销；剪枝或稀疏只有得到算子支持才会转化为速度收益。另一类方案是不改变模型：用张量/流水线并行分片到多设备，或把部分权重、KV、优化器状态卸载到 CPU/NVMe，代价是通信或数据搬运延迟。\n\n如果长上下文导致 KV Cache 成为瓶颈，应缩短上下文、降低并发、采用 GQA/MQA、KV 量化、分页管理或前缀复用，而不是只压缩权重。最终按目标硬件测峰值显存、质量、吞吐和 p95 延迟；不要用“参数量乘位宽”得到的理论下限冒充可部署显存。""",
    "q1193": """跨数据库、文件系统和第三方 API 的多步操作通常无法获得一个真正的全局 ACID 事务，因此目标应是缩小原子边界、避免重复副作用，并让失败状态可恢复、可审计。\n\n同一数据库内优先使用本地事务；支持 prepare/commit 的少数资源可以考虑两阶段提交，但要承担阻塞、协调器故障和可用性成本。更常见的是 Saga：把流程拆成幂等步骤，记录状态与幂等键；后续步骤失败时，按相反顺序执行显式补偿。补偿并不等于物理回滚，例如已发送邮件无法收回，只能发送更正或转人工。\n\ndry-run、沙箱和变更预览可以在提交前发现风险，但不能证明真实执行一定成功，因为权限、并发状态和外部系统可能变化。高风险动作应把待执行参数生成不可篡改的摘要供用户确认，提交时再校验版本与前置条件；无法自动补偿的步骤设置人工审批和对账任务。""",
    "q2029": """两者都遵循“获取外部证据，再让模型基于证据回答”的思想，但网页 RAG 不只是把 PDF 换成 URL。网页场景首先要决定是实时搜索并读取少量页面，还是持续抓取、清洗后建立自有索引；前者不一定需要预先切块和向量化，后者才更接近典型离线文档 RAG。\n\n网页额外面对动态内容、JavaScript 渲染、重复页面、正文抽取、抓取许可与限流、内容时效、来源可信度和恶意提示注入。系统应保存 URL、抓取时间、内容版本与引用片段，做域名或来源质量控制，并把网页文本当作不可信数据而不是指令。\n\n本地文档通常有更明确的授权、权限和版本边界，但也要处理 PDF 版面、OCR、表格和 ACL。两种方案都需要用真实问题评估证据召回、引用正确性和最终回答忠实度，不能因为来源是互联网就默认更新、更全面或更可信。""",
}


def should_drop(item: dict, domain: str) -> bool:
    # MANUAL_DROP_IDS：人工复核确认「答案自述无法作答 / 与面试无关」的无效题，
    # 原记录仍会写入归档，可回查恢复。
    if (
        item["id"] in DROP_IDS
        or item["id"] in EXTRA_DROP_IDS
        or item["id"] in MANUAL_DROP_IDS
        or item["id"] in RECLASSIFICATION_DROP_IDS
    ):
        return True
    title = item.get("title", "")
    patterns = FRAGMENT_RE if domain in AI_DOMAINS else EXTRA_FRAGMENT_RE
    if any(pattern.search(title) for pattern in patterns):
        return True
    if "?" not in title and "？" not in title and not QUESTION_SIGNAL_RE.search(title):
        return True
    return False


def normalize_title(title: str) -> str:
    title = re.sub(
        r"^\s*(?:问题\s*\d*|面试题\s*\d*|Q\d+|【Q\d+】|核心问题)\s*[:：．、]?\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"^[．。\s]+", "", title).replace("⭐", "").strip()
    title = re.sub(r"^(?:追问|补充)\s*[:：]\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*[√×]\s*(?:（[^）]*）|\([^)]*\))?", "", title)
    title = title.replace("。？", "？").replace("。?", "?")
    title = re.sub(r"[？?]+$", "？", title)
    if not title.endswith(("？", "?")) and QUESTION_SIGNAL_RE.search(title):
        title = title.rstrip("。；;，,") + "？"
    return title


def strip_boilerplate(answer: str) -> str:
    paragraphs = re.split(r"\n\s*\n", answer.strip())
    paragraphs = [p for p in paragraphs if not p.lstrip().startswith("关键机制补全：")]
    return "\n\n".join(paragraphs).strip()


def collapse_accidental_leading_repeat(answer: str) -> str:
    """Remove an exact, immediately repeated long opening sentence.

    A legacy scraper sometimes concatenated the answer lead twice (for example
    ``"Docker 是…。Docker 是…。"``).  This is deliberately narrower than
    general text de-duplication: it only removes adjacent, textually identical
    opening sentences of a meaningful length, so a deliberate summary followed
    by a differently worded explanation is preserved.
    """
    sentence_pair = re.compile(
        r"^(?P<prefix>\s*)"
        r"(?P<first>(?:[-*+]\s*)?[^。！？!?]{16,}[。！？!?])"
        r"\s*"
        r"(?P<second>(?:[-*+]\s*)?[^。！？!?]+[。！？!?])",
        flags=re.DOTALL,
    )

    def canonical(sentence: str) -> str:
        sentence = re.sub(r"^\s*(?:[-*+]\s*)?", "", sentence)
        return re.sub(r"\s+", " ", sentence).strip().rstrip("。！？!?").strip()

    while True:
        match = sentence_pair.match(answer)
        if not match or canonical(match.group("first")) != canonical(match.group("second")):
            return answer
        answer = (
            match.group("prefix")
            + match.group("first")
            + answer[match.end("second"):]
        )


def clean_editorial_fields(item: dict) -> dict:
    """Remove copied coaching appendices, not substantive answer paragraphs.

    The full original row is archived before any second-pass edits. Malformed
    follow-ups are omitted rather than turning a truncated statement into a
    purported question. Reviewed replacements provide their own follow-ups.
    """
    answer = strip_boilerplate(item.get("answer", ""))
    # Imported Cooper references are inert <cite> tags, not usable links in
    # Markdown. Preserve the human-readable title without leaking raw HTML.
    answer = re.sub(
        r'<cite\b([^>]*)>\s*</cite>',
        lambda match: unescape(re.search(r'title="([^"]*)"', match.group(1)).group(1))
        if re.search(r'title="([^"]*)"', match.group(1)) else "",
        answer,
        flags=re.IGNORECASE,
    )
    answer = re.sub(r"(?m)^超卖推荐学习：【[^\n]+", "**超卖场景补充**", answer)
    recommendation = re.search(r"(?m)^\s*(?:\*\*)?推荐学习(?:\*\*)?\s*[:：]?", answer)
    if recommendation:
        supplement = answer[recommendation.end():].strip().lstrip("*\n ")
        if len(supplement) > 250 or re.search(r"(?m)^\s*(?:>|```|\*\*补充)|https?://", supplement):
            answer = answer[:recommendation.start()].rstrip() + "\n\n**补充说明**\n\n" + supplement
        else:
            answer = answer[:recommendation.start()].rstrip()
    # Keep every question as the only outline node.  Source material sometimes
    # contains third- to sixth-level headings inside an answer; turn those
    # section labels into standalone bold lines without touching code fences.
    normalized_lines = []
    in_fence = False
    for line in answer.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        heading = None if in_fence else re.fullmatch(r"\s*#{3,6}\s+(.+?)\s*", line)
        if heading:
            label = heading.group(1).strip()
            if not (label.startswith("**") and label.endswith("**")):
                label = f"**{label}**"
            line = label
        normalized_lines.append(line)
    answer = "\n".join(normalized_lines)
    coaching = re.search(r"(?:【)?(?:加分点|常见雷区)(?:】|[:：]|是)", answer)
    if coaching:
        answer = answer[:coaching.start()].rstrip()
    answer = collapse_accidental_leading_repeat(answer)
    item["answer"] = answer
    focus = item.get("kaodian", "")
    generic = re.fullmatch(
        r"考察[^：。]{1,30}：能否讲清「(.+?)」的原理、取舍与落地细节。.*",
        focus,
        flags=re.DOTALL,
    )
    if generic:
        item["kaodian"] = generic.group(1).rstrip("？?。") + "。"
    followup = item.pop("追问", "") or item.get("followup", "")
    followup = re.sub(r"^(?:常见)?追问[:：]\s*", "", followup).strip()
    if any(marker in followup for marker in (
        "这些你能展开说清楚吗", "另外面试官常设这些坑", "面试官常顺着问", "…",
    )):
        followup = ""
    item["followup"] = followup
    # Remove standalone coaching placeholders from otherwise useful outlines.
    item["framework"] = re.sub(
        r"(?:；\s*)?\d+[)）]\s*(?:(?:常见)?雷区|加分点)[。.]?\s*$", "",
        item.get("framework", ""),
    ).rstrip()
    item["framework"] = re.sub(r"[和与]加分点", "", item["framework"])
    return item


def curate_item(item: dict) -> dict:
    item = dict(item)
    qid = item["id"]
    if qid in ALL_TITLE_REWRITES:
        item["title"] = ALL_TITLE_REWRITES[qid]
    item["title"] = normalize_title(item["title"])
    if qid in META_REWRITES:
        item.update(META_REWRITES[qid])
    if qid in ANSWER_REWRITES:
        item["answer"] = ANSWER_REWRITES[qid]
    elif feishu_source(qid).startswith("cs:"):
        # 手写整理的答案优先于既有的人工更正：它是作者本人的真实答题口径。
        apply_feishu_answer(item, FEISHU_ANSWERS[qid])
    else:
        item["answer"] = strip_boilerplate(item.get("answer", ""))
    if qid in ALL_OVERRIDES:
        item.update(ALL_OVERRIDES[qid])
        # A legacy Chinese key must not shadow a reviewed follow-up.
        item.pop("追问", None)
    item.update(ALL_FIELD_FIXES.get(qid, {}))
    # Agent 库是 AI 加工版：只填补没有被人工勘误、更正或字段修复覆盖过的题目。
    if (
        feishu_source(qid).startswith("agent:")
        and qid not in ANSWER_REWRITES
        and qid not in ALL_OVERRIDES
        and qid not in ALL_FIELD_FIXES
    ):
        apply_feishu_answer(item, FEISHU_ANSWERS[qid])
    return clean_editorial_fields(item)


def destination_for(domain: str, item: dict) -> str:
    """Return an explicitly reviewed destination for a retained item."""
    qid = item["id"]
    if qid in ALL_MOVE_TO:
        return ALL_MOVE_TO[qid]
    for lower, upper, destination in EXTRA_RANGE_MOVES.get(domain, ()):
        if lower <= qid <= upper:
            return destination
    return domain


def curate_domains() -> dict[str, list[dict]]:
    # Read every domain before writing any: a moved record must not be lost or
    # loaded twice just because its destination sorts before its source.
    original = {}
    for name in DOMAINS:
        source_path = AUTHORED / f"{name}.jsonl"
        original[name] = (
            [
                json.loads(line)
                for line in source_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if source_path.exists()
            else []
        )
    results = {name: [] for name in DOMAINS}
    moved = []
    archive_paths = {
        "ai": ROOT / "review_archive" / "second_pass_originals.jsonl",
        "extra": ROOT / "review_archive" / "third_pass_extra_originals.jsonl",
    }
    archived = {}
    for key, archive_path in archive_paths.items():
        if archive_path.exists():
            archived[key] = {row["item"]["id"]: row for row in map(json.loads, archive_path.read_text(encoding="utf-8").splitlines())}
        else:
            archived[key] = {}
    # A third-pass item can move into an AI domain.  Its original record still
    # belongs to the third-pass archive; do not create a second, already-
    # curated pseudo-original in the older AI archive on a subsequent run.
    for qid in set(archived["ai"]) & set(archived["extra"]):
        del archived["ai"][qid]
    for name, items in original.items():
        for raw_item in items:
            # A manually reviewed title rewrite stands on its own: apply it before
            # the fragment check, otherwise the original scraped phrasing (for
            # example "原理：…") would drop the question right after it moves into
            # an AI domain, whose fragment rules are stricter than the extra ones.
            # The archive keeps the untouched source record.
            item = dict(raw_item)
            if item["id"] in ALL_TITLE_REWRITES:
                item["title"] = ALL_TITLE_REWRITES[item["id"]]
            qid = item["id"]
            archive_key = "extra" if qid in archived["extra"] or name not in AI_DOMAINS else "ai"
            removed = qid in ALL_MERGED_INTO or should_drop(item, name)
            updated = None if removed else curate_item(item)
            destination = destination_for(name, item)
            if removed or updated != item or destination != name:
                archive_row = archived[archive_key].setdefault(qid, {
                    "domain": name, "item": raw_item,
                    "merged_into": ALL_MERGED_INTO.get(qid),
                    "destination": None if removed else destination,
                })
                # The first-seen row is the immutable source record, while
                # disposition follows the current deterministic review rules.
                archive_row["merged_into"] = ALL_MERGED_INTO.get(qid)
                archive_row["destination"] = None if removed else destination
            if removed:
                continue
            if destination == name:
                results[name].append(updated)
            else:
                moved.append((destination, updated))
    for destination, item in moved:
        results[destination].append(item)
    ids = [item["id"] for items in results.values() for item in items]
    assert len(ids) == len(set(ids)), "Duplicate ID after domain migration"
    assert set(ALL_MERGED_INTO.values()) <= set(ids), "A merge target is missing"
    for name, items in results.items():
        assert all(item["answer"].strip() for item in items), f"Empty answer in {name}"
    # Preserve first-seen originals while keeping their final disposition up
    # to date if a later review merges or moves an already archived question.
    final_destination = {
        item["id"]: domain
        for domain, items in results.items()
        for item in items
    }
    for archive_key, archive_rows in archived.items():
        for qid, row in archive_rows.items():
            if qid in ALL_MERGED_INTO:
                row["merged_into"] = ALL_MERGED_INTO[qid]
                row["destination"] = None
            else:
                # A record may have been removed on a later idempotent pass
                # after title normalization exposed an incomplete fragment.
                # Always archive its final corpus disposition, not a stale
                # intermediate destination.
                row["destination"] = final_destination.get(qid)
        archive_path = archive_paths[archive_key]
        archive_path.parent.mkdir(exist_ok=True)
        write_crlf(archive_path, "".join(json.dumps(archive_rows[qid], ensure_ascii=False) + "\n" for qid in sorted(archive_rows)))
    for name, items in results.items():
        write_crlf(AUTHORED / f"{name}.jsonl", "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items))
    return results


def render_domain(name: str, label: str, items: list[dict]) -> None:
    lines = [
        f"# {label}",
        "",
        f"> 题目数量：**{len(items)}** ｜ 渲染时间：自动 ｜ 源：authored/{name}.jsonl",
        "",
        "---",
        "",
    ]
    for index, item in enumerate(items, 1):
        freq = max(1, min(5, int(item.get("freq", 3))))
        followup = item.get("followup", "")
        lines.extend(
            [
                f"## {index}. {item['title']}",
                "",
                f"> 原题 ID：`{item['id']}`",
                "",
                f"**高频程度**：{'★' * freq}",
                "",
                f"**考察点**：{item.get('kaodian', '—')}",
                "",
                "**回答框架**：",
                "",
                item.get("framework", "—"),
                "",
                "**参考回答**：",
                "",
                item.get("answer", "—"),
                "",
            ]
        )
        if followup:
            lines.extend([f"**常见追问**：{followup}", ""])
        if item.get("sources"):
            links = "；".join(f"[{source['title']}]({source['url']})" for source in item["sources"])
            lines.extend([f"**核验资料**：{links}", ""])
        lines.extend(["---", ""])
    write_crlf(OUTPUT / f"{name}.md", "\n".join(lines))


def render_index(results: dict[str, list[dict]]) -> None:
    # Curate only the reviewed AI domains, but retain other independently
    # maintained domains in the shared index after cross-device merges.
    entries = {name: (DOMAINS[name], len(items)) for name, items in results.items()}
    for path in sorted(OUTPUT.glob("*.md")):
        if path.stem == "INDEX" or path.stem in entries:
            continue
        content = path.read_text(encoding="utf-8")
        title = re.search(r"^# (.+)$", content, re.MULTILINE)
        declared = re.search(r"^> 题目数量：\*\*(\d+)\*\*", content, re.MULTILINE)
        if not title or not declared:
            continue
        count = len(re.findall(r"^## \d+\. ", content, re.MULTILINE))
        assert count == int(declared.group(1)), f"Question count mismatch: {path}"
        entries[path.stem] = (title.group(1), count)
    total = sum(count for _, count in entries.values())
    lines = [
        "# 全量题库（精选标准 · 按领域）",
        "",
        f"> 总题数：{total}（源 {total}）｜ 渲染：questions_v2/full_v2/",
        "",
        "| 文件名 | 领域 | 题目数量 |",
        "| --- | --- | ---: |",
    ]
    for name, (label, count) in sorted(entries.items()):
        lines.append(f"| [{name}.md](./{name}.md) | {label} | {count} |")
    lines.append(f"| **合计** | | **{total}** |")
    lines.append("")
    write_crlf(OUTPUT / "INDEX.md", "\n".join(lines))


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = curate_domains()
    for name, label in DOMAINS.items():
        items = results[name]
        render_domain(name, label, items)
        print(f"{name}: kept={len(items)}")
    render_index(results)
    print(f"curated full_v2 total: {sum(map(len, results.values()))}")


if __name__ == "__main__":
    main()
