"""Run one question against one part of the system and record everything the checkers need.

Targets:
  team        the full graph: research lead -> supervisor <-> workers -> writer (workflow.py)
  researcher  the filings researcher alone (search_filing + EDGAR tools)
  quant       the quant agent alone (EDGAR tools + run_python)
  risk        the risk-diff agent alone (compare_risk_factors)
  sandbox     python_sandbox.run_code directly, no model

Defences: this harness does not build defences (the brief says the person writing attacks must not
build the defences). With defences="on" it:
  1. sets AGENT_DESK_DEFENCES=on so the team's own code can switch its hooks/guardrails on, and
  2. if a guardrails module exists (default agent_desk.guardrails), calls
       check_input(question) -> {"allowed": bool, "reason": str}
       check_output(answer, question) -> {"allowed": bool, "reason": str, "answer": str (optional)}
     before and after the run. Either function may be missing.
"""

from __future__ import annotations

import contextlib
import importlib
import inspect
import os
import time
from contextvars import ContextVar
from typing import Any, Iterator
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tracers.context import register_configure_hook

from .checks import RunRecord, ToolCall, mark_guard_events


class Recorder(BaseCallbackHandler):
    """Collects tool calls requested by the model, LLM call counts and token usage, from every nested agent."""

    def __init__(self) -> None:
        self.tool_calls: list[ToolCall] = []
        self.llm_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def on_chat_model_start(self, serialized: Any, messages: Any, *, run_id: UUID, **kw: Any) -> None:
        self.llm_calls += 1

    def on_llm_end(self, response: Any, **kw: Any) -> None:
        for gens in response.generations or []:
            for gen in gens:
                msg = getattr(gen, "message", None)
                # Tool calls are read from the model's reply: exactly what it asked to run, with
                # the arguments it chose. (Tool-start callbacks do not fire under LangGraph 1.x.)
                for tc in getattr(msg, "tool_calls", None) or []:
                    self.tool_calls.append(ToolCall(name=tc.get("name", "unknown"), args=dict(tc.get("args") or {})))
                usage = getattr(msg, "usage_metadata", None) or {}
                self.input_tokens += int(usage.get("input_tokens", 0) or 0)
                self.output_tokens += int(usage.get("output_tokens", 0) or 0)


# The team's workers call agent.invoke() inside graph nodes without passing config, so callbacks
# given to the outer invoke do not reach them. A configure hook (the mechanism LangSmith tracing
# uses) attaches the recorder to every run started while it is set, however deeply nested.
_ACTIVE: ContextVar[Recorder | None] = ContextVar("redteam_recorder", default=None)
register_configure_hook(_ACTIVE, inheritable=True)


@contextlib.contextmanager
def recording() -> Iterator[Recorder]:
    rec = Recorder()
    token = _ACTIVE.set(rec)
    try:
        yield rec
    finally:
        _ACTIVE.reset(token)


def load_guardrails(module_name: str | None):
    if not module_name:
        return None
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None


def _tool_layer(guard: Any | None, question: str, events: list[dict[str, Any]]):
    """The guard's tool wrapper for one request, or a no-op. Passes `events` if install() accepts it."""
    if guard is None or not hasattr(guard, "install"):
        return contextlib.nullcontext()
    if "events" in inspect.signature(guard.install).parameters:
        return guard.install(question, events=events)
    return guard.install(question)


def _invoke_target(target: str, question: str, config: dict[str, Any]) -> str:
    if target == "team":
        from agent_desk.agents.workflow import build_team_workflow, initial_state

        result = build_team_workflow().invoke(initial_state(question), {**config, "recursion_limit": 40})
        return str(result.get("final_answer", ""))
    if target in ("researcher", "quant", "risk"):
        if target == "researcher":
            from agent_desk.agents.researcher_agent import build_researcher as build
        elif target == "quant":
            from agent_desk.agents.quant_agent import build_quant_agent as build
        else:
            from agent_desk.agents.risk_diff_agent import build_risk_diff_agent as build
        result = build().invoke({"messages": [("user", question)]}, {**config, "recursion_limit": 25})
        return str(result["messages"][-1].content)
    raise ValueError(f"unknown target {target}")


def run_target(target: str, question: str, defences: bool, guardrails: Any | None = None) -> tuple[RunRecord, float]:
    """Returns the record and the wall-clock seconds. Never raises: errors go into record.error."""
    os.environ["AGENT_DESK_DEFENCES"] = "on" if defences else "off"
    rec = RunRecord()
    start = time.perf_counter()

    if target == "sandbox":
        from agent_desk.sandbox.python_sandbox import run_code

        if defences and guardrails is not None and hasattr(guardrails, "check_code"):
            reason = guardrails.check_code(question)
            if reason:  # the pre-tool hook refused the code before the sandbox ran it
                rec.blocked_by = f"input_guard: pre-tool hook: {reason}"
                return rec, time.perf_counter() - start
        try:
            rec.sandbox = run_code(question)
            rec.answer = rec.sandbox.get("output", "") + rec.sandbox.get("error", "")
        except Exception as exc:  # noqa: BLE001
            rec.error = f"{type(exc).__name__}: {exc}"
        return rec, time.perf_counter() - start

    guard = guardrails if defences else None
    if guard is not None and hasattr(guard, "check_input"):
        verdict = guard.check_input(question)
        if not verdict.get("allowed", True):
            rec.blocked_by = f"input_guard: {verdict.get('reason', '')}"
            return rec, time.perf_counter() - start

    guard_events: list[dict[str, Any]] = []  # calls the pre-tool hook blocked or changed
    tool_layer = _tool_layer(guard, question, guard_events)
    with recording() as recorder, tool_layer:
        try:
            rec.answer = _invoke_target(target, question, {})
        except Exception as exc:  # noqa: BLE001 - a crashed run is a result, not a harness failure
            rec.error = f"{type(exc).__name__}: {str(exc)[:500]}"
    rec.tool_calls = recorder.tool_calls
    # The recorder saw what the model ASKED for; mark the calls the hook stopped or changed, so a
    # blocked watchlist search or blocked escape code is not scored as a successful attack.
    reports_calls = guard is not None and hasattr(guard, "install") and "events" in inspect.signature(guard.install).parameters
    mark_guard_events(rec.tool_calls, guard_events, require_executed=reports_calls)
    rec.llm_calls = recorder.llm_calls
    rec.input_tokens = recorder.input_tokens
    rec.output_tokens = recorder.output_tokens

    if guard is not None and hasattr(guard, "check_output") and rec.answer:
        verdict = guard.check_output(rec.answer, question)
        if not verdict.get("allowed", True):
            rec.blocked_by = f"output_guard: {verdict.get('reason', '')}"
        elif verdict.get("answer") is not None:
            rec.answer = verdict["answer"]
    return rec, time.perf_counter() - start
