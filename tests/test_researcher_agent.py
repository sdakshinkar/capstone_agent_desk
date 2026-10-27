from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent_desk import llm, researcher_agent


class ToolFakeChat(GenericFakeChatModel):
    """Fake chat model that accepts bind_tools and ignores the schemas."""

    def bind_tools(self, tools: Any, **kwargs: Any):
        return self


def test_get_llm_requires_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        llm.get_llm(llm.TOOL_MODEL)


def test_models_configured(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    assert llm.get_tool_llm().model_name == "meta-llama/llama-3.3-70b-instruct"
    assert llm.get_fast_llm().model_name == "meta-llama/llama-3.1-8b-instruct"


def test_researcher_runs_tool_loop():
    tool_call = AIMessage(
        content="",
        tool_calls=[{"name": "list_edgar_companies", "args": {}, "id": "call_1"}],
    )
    final = AIMessage(content="Apple, Microsoft and Alphabet are available.")
    fake = ToolFakeChat(messages=iter([tool_call, final]))

    agent = researcher_agent.build_researcher(fake)
    result = agent.invoke({"messages": [("user", "Which companies do you cover?")]})

    kinds = [m.type for m in result["messages"]]
    assert "tool" in kinds
    assert "AAPL" in result["messages"][kinds.index("tool")].content
    assert result["messages"][-1].content == final.content
