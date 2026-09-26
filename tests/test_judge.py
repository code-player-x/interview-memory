"""外部 Agent 判题回调的回归测试。"""
import asyncio
import json

import httpx
import pytest

from backend import judge


class _SuccessResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"is_correct": True, "explanation": "Agent 判定正确", "error_reason": ""}


class _SuccessClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return _SuccessResponse()


class _FailingClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        raise httpx.ConnectError("offline")

    async def __aexit__(self, *args):
        return False


def test_agent_callback_is_preferred_and_parsed(monkeypatch):
    monkeypatch.setenv("AGENT_JUDGE_URL", "http://agent.example/judge")
    monkeypatch.setattr(httpx, "AsyncClient", _SuccessClient)
    result = asyncio.run(judge.judge("问题", "参考答案", "用户答案"))
    assert result == (True, "Agent 判定正确", "", "agent")


def test_agent_callback_failure_returns_pending(monkeypatch):
    monkeypatch.setenv("AGENT_JUDGE_URL", "http://agent.example/judge")
    monkeypatch.setattr(httpx, "AsyncClient", _FailingClient)
    result = asyncio.run(judge.judge("问题", "参考答案", "用户答案"))
    assert result[0] is None
    assert result[3] == "pending"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("false", False), (" TRUE ", True)],
)
def test_llm_string_boolean_is_parsed_without_python_truthiness(monkeypatch, value, expected):
    class LlmResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": (
                '{"is_correct": "' + value + '", "explanation": "ok", "error_reason": ""}'
            )}}]}

    class LlmClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return LlmResponse()

    monkeypatch.delenv("AGENT_JUDGE_URL", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setattr(httpx, "AsyncClient", LlmClient)
    result = asyncio.run(judge.judge("问题", "参考答案", "用户答案"))
    assert result == (expected, "ok", "", "llm")


@pytest.mark.parametrize("source", ["agent", "llm"])
@pytest.mark.parametrize("field,value", [("explanation", {}), ("error_reason", []), ("explanation", None)])
def test_malformed_service_text_returns_pending(monkeypatch, source, field, value):
    payload = {"is_correct": True, "explanation": "ok", "error_reason": "", field: value}

    class Response:
        def raise_for_status(self): pass
        def json(self):
            return payload if source == "agent" else {"choices": [{"message": {"content": json.dumps(payload)}}]}

    class Client(_SuccessClient):
        async def post(self, *args, **kwargs): return Response()

    monkeypatch.setenv("AGENT_JUDGE_URL", "http://agent.example" if source == "agent" else "")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_MODEL", "test")
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    assert asyncio.run(judge.judge("题", "参考", "回答")) == (None, "判题服务暂不可用", "judge_error", "pending")


@pytest.mark.parametrize("wrapper", ["{}", "```json\n{}\n```", "```json {} ```"])
def test_llm_json_fences_do_not_remove_json_word_from_explanation(monkeypatch, wrapper):
    content = wrapper.format(json.dumps({"is_correct": True, "explanation": "valid json answer", "error_reason": ""}))

    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": content}}]}

    class Client(_SuccessClient):
        async def post(self, *args, **kwargs): return Response()

    monkeypatch.setenv("AGENT_JUDGE_URL", "")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_MODEL", "test")
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    assert asyncio.run(judge.judge("题", "参考", "回答")) == (True, "valid json answer", "", "llm")
