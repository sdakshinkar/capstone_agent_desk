"""Callback that records one eval run and enforces its budget.

Attached to the top-level invoke, it also sees every nested call (the worker agents run inside
graph nodes and inherit the callbacks through LangChain's context), so one Recorder captures:
    nodes       graph nodes in the order they ran (research_lead, supervisor, quant_worker, ...)
    tool_calls  name, arguments and output of every tool call
    llm_calls   number of chat model calls, input/output tokens, and cost when OpenRouter
                reports it (response metadata token_usage.cost)
and stops the run by raising BudgetExceeded *before* the next model or tool call once a limit
is passed. raise_error = True makes LangChain propagate that exception instead of logging it.
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

GRAPH_NODES = {
    "research_lead", "approve_plan", "supervisor", "researcher_worker", "quant_worker", "risk_worker",
    "writer", "critic",
}
MAX_OUTPUT_CHARS = 60_000  # tool outputs are kept for the evidence check, capped per call


class BudgetExceeded(RuntimeError):
    pass


class Recorder(BaseCallbackHandler):
    raise_error = True

    def __init__(
        self,
        max_tokens: int | None = None,
        max_llm_calls: int | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.max_tokens = max_tokens
        self.max_llm_calls = max_llm_calls
        self.timeout_s = timeout_s
        self.started = time.monotonic()
        self.nodes: list[str] = []
        self.tool_calls: list[dict[str, Any]] = []
        self._open_tools: dict[Any, dict[str, Any]] = {}
        self.llm_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd: float | None = None

    # ------------------------------------------------------------------ budget

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def _check_budget(self) -> None:
        if self.timeout_s is not None and self.elapsed > self.timeout_s:
            raise BudgetExceeded(f"timeout: {self.elapsed:.0f}s > {self.timeout_s:.0f}s")
        if self.max_tokens is not None and self.tokens > self.max_tokens:
            raise BudgetExceeded(f"token budget: {self.tokens} > {self.max_tokens}")
        if self.max_llm_calls is not None and self.llm_calls >= self.max_llm_calls:
            raise BudgetExceeded(f"llm call budget: {self.llm_calls} >= {self.max_llm_calls}")

    # ------------------------------------------------------------------ graph nodes

    def on_chain_start(self, serialized: Any, inputs: Any, **kwargs: Any) -> None:
        name = kwargs.get("name") or (serialized or {}).get("name")
        if name in GRAPH_NODES:
            self.nodes.append(name)

    # ------------------------------------------------------------------ tools

    def on_tool_start(self, serialized: Any, input_str: str, *, run_id: Any = None, **kwargs: Any) -> None:
        self._check_budget()
        name = kwargs.get("name") or (serialized or {}).get("name", "?")
        call = {"name": name, "args": kwargs.get("inputs") or input_str, "output": None}
        self._open_tools[run_id] = call
        self.tool_calls.append(call)

    def on_tool_end(self, output: Any, *, run_id: Any = None, **kwargs: Any) -> None:
        call = self._open_tools.pop(run_id, None)
        if call is not None:
            text = getattr(output, "content", output)
            call["output"] = str(text)[:MAX_OUTPUT_CHARS]

    def on_tool_error(self, error: BaseException, *, run_id: Any = None, **kwargs: Any) -> None:
        call = self._open_tools.pop(run_id, None)
        if call is not None:
            call["output"] = f"TOOL ERROR: {type(error).__name__}: {error}"

    # ------------------------------------------------------------------ model calls

    def on_chat_model_start(self, serialized: Any, messages: Any, **kwargs: Any) -> None:
        self._check_budget()
        self.llm_calls += 1

    def on_llm_start(self, serialized: Any, prompts: Any, **kwargs: Any) -> None:
        self._check_budget()
        self.llm_calls += 1

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        usage: dict[str, Any] = {}
        try:
            message = response.generations[0][0].message
            meta = getattr(message, "usage_metadata", None) or {}
            usage = {"input": meta.get("input_tokens", 0), "output": meta.get("output_tokens", 0)}
            token_usage = (getattr(message, "response_metadata", {}) or {}).get("token_usage") or {}
        except (AttributeError, IndexError):
            token_usage = {}
        if not usage:
            token_usage = (response.llm_output or {}).get("token_usage") or token_usage
            usage = {
                "input": token_usage.get("prompt_tokens", 0),
                "output": token_usage.get("completion_tokens", 0),
            }
        self.input_tokens += int(usage.get("input") or 0)
        self.output_tokens += int(usage.get("output") or 0)
        cost = token_usage.get("cost")
        if isinstance(cost, (int, float)):
            self.cost_usd = (self.cost_usd or 0.0) + float(cost)

    # ------------------------------------------------------------------ result

    def summary(self) -> dict[str, Any]:
        return {
            "nodes": self.nodes,
            "tool_calls": self.tool_calls,
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
        }
