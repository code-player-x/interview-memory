"""判题模块：仅此模块依赖外部 Agent / LLM。

策略（保证不抛异常，避免 /api/answer 直接 500）：
1. 若配置了 AGENT_JUDGE_URL → 调用外部 Agent 判题（source='agent'）；
2. 否则若配置了 LLM_* → 调用 OpenAI 兼容接口判题（source='llm'）；
3. 两者均未配置时，降级为启发式判题（source='heuristic'）；
4. 已配置的远端判题服务不可用时 → 返回 pending，供后续重试，不误判为对/错。

绝不在此代填 API Key；缺失配置时静默走 heuristic。
"""
import os
import re
from typing import Optional, Tuple

_STOPWORDS = set("的 了 是 在 和 与 及 或 一个 一种 可以 我们 你 我 他 它 这 那 有 没有 不 也 都 就 而 对 为 等 以 于 到 把 被 让 使".split())


def _parse_is_correct(value) -> bool:
    """只接受真正的布尔值或常见的 JSON 字符串布尔值。

    Python 的 ``bool(\"false\")`` 为 True，直接套用会把部分 OpenAI 兼容服务
    返回的字符串 ``\"false\"`` 误判为正确。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise ValueError("is_correct must be a boolean")


def _extract_keywords(text: str) -> set:
    """从文本中提取有意义的关键词（去标点、去停用词、保留 ≥2 字中文或英文词）。"""
    if not text:
        return set()
    # 英文/数字词
    toks = re.findall(r"[a-zA-Z0-9_+\.#]{2,}", text)
    # 中文按 2~4 字切分（简单 N-gram，覆盖常见术语）
    cn = re.findall(r"[一-鿿]{2,4}", text)
    words = set(toks) | set(cn)
    return {w for w in words if w not in _STOPWORDS}


def _parse_result(data, source: str):
    """Validate untrusted service output before it reaches response/DB models."""
    if not isinstance(data, dict):
        raise ValueError("judge result must be an object")
    value = _parse_is_correct(data.get("is_correct"))
    explanation = data.get("explanation", "")
    error_reason = data.get("error_reason", "")
    if not isinstance(explanation, str) or not isinstance(error_reason, str):
        raise ValueError("judge explanation and error_reason must be strings")
    return value, explanation, error_reason, source


def _heuristic_judge(reference_answer: str, user_answer: str) -> Tuple[Optional[bool], str, str, str]:
    """启发式：参考答案关键词在用户答案中的覆盖率决定正误。"""
    ref_kw = _extract_keywords(reference_answer)
    if not ref_kw:
        # 参考答案无可提取关键词 → 无法客观判定，按「部分正确」标记需人工/LLM 复核
        return None, "参考答案无可判定关键词，建议人工复核或配置 LLM 判题", "", "heuristic"
    ans_kw = _extract_keywords(user_answer)
    covered = ref_kw & ans_kw
    ratio = len(covered) / len(ref_kw)
    if ratio >= 0.6:
        return True, f"命中关键词 {len(covered)}/{len(ref_kw)}（覆盖率 {ratio:.0%}），判为正确", "", "heuristic"
    if ratio >= 0.25:
        return False, f"仅命中关键词 {len(covered)}/{len(ref_kw)}（覆盖率 {ratio:.0%}），判为错误", "关键词覆盖不足", "heuristic"
    return False, f"几乎未命中参考答案关键词（覆盖率 {ratio:.0%}）", "未覆盖核心要点", "heuristic"


async def _llm_judge(question_text: str, reference_answer: str, user_answer: str):
    """可选 LLM 判题；未配置时返回 None，已配置但不可用时返回 pending。"""
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
    if not (api_key and base_url and model):
        return None
    try:
        import httpx  # 动态导入，避免无依赖时 import 失败
    except ImportError:
        return None, "判题服务暂不可用", "judge_error", "pending"
    prompt = (
        "你是技术面试判题助手。判断用户答案是否正确覆盖了参考答案的要点。\n"
        f"【题目】{question_text}\n"
        f"【参考答案】{reference_answer}\n"
        f"【用户答案】{user_answer}\n"
        "仅输出 JSON：{\"is_correct\": true/false, \"explanation\": \"...\", \"error_reason\": \"...\"}"
    )
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        import json
        # Strip only a wrapping fence, not the word "json" inside the answer.
        content = re.sub(r"\A```(?:json)?\s*([\s\S]*?)\s*```\Z", r"\1", content.strip(), flags=re.I)
        return _parse_result(json.loads(content), "llm")
    except Exception:
        return None, "判题服务暂不可用", "judge_error", "pending"


async def _agent_judge(question_text: str, reference_answer: str, user_answer: str):
    """调用外部 Agent HTTP 回调；未配置时返回 None。"""
    url = os.getenv("AGENT_JUDGE_URL", "").strip()
    if not url:
        return None
    try:
        import httpx
    except ImportError:
        return None, "判题服务暂不可用", "judge_error", "pending"

    headers = {"Content-Type": "application/json"}
    token = os.getenv("AGENT_JUDGE_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                url,
                headers=headers,
                json={
                    "question_text": question_text,
                    "reference_answer": reference_answer,
                    "user_answer": user_answer,
                },
            )
            response.raise_for_status()
            data = response.json()
        return _parse_result(data, "agent")
    except Exception:
        return None, "判题服务暂不可用", "judge_error", "pending"


async def judge(
    question_text: str, reference_answer: str, user_answer: str
) -> Tuple[Optional[bool], str, str, str]:
    """判题入口。返回 (is_correct, explanation, error_reason, source)。

    - is_correct: True/False/None（None 表示无法判定）
    - source: 'llm' | 'heuristic' | 'pending' | 'none'
    """
    ua = (user_answer or "").strip()
    if not ua:
        return None, "未作答", "", "none"
    try:
        agent_res = await _agent_judge(question_text, reference_answer, ua)
        if agent_res is not None:
            return agent_res
        llm_res = await _llm_judge(question_text, reference_answer, ua)
        if llm_res is not None:
            return llm_res
    except Exception:
        return None, "判题服务暂不可用", "judge_error", "pending"
    try:
        return _heuristic_judge(reference_answer, ua)
    except Exception as e:  # 兜底：绝不向上抛，避免接口 500
        return None, f"判题异常：{type(e).__name__}", "judge_error", "pending"
