"""Glue between the guardrails and the app: switch, question check, tool hooks, answer check.

The app (ui/app.py) and the terminal runner (main.py) call these helpers; the guardrails themselves
live in __init__ (text rules) and tool_guards (tool hooks).

Switch: the environment variable AGENT_DESK_DEFENCES.
  "on"   guardrails run.  The app and main.py set this as their default.
  "off"  no guardrails (what the evaluation harness and tests see unless they ask for them).
Library code never turns it on by itself, so importing agent_desk changes no behaviour.
"""

from __future__ import annotations

import contextlib
import os
from collections import Counter
from typing import Any, Callable, ContextManager

from . import check_input, check_output
from .tool_guards import install

ENV_VAR = "AGENT_DESK_DEFENCES"


def enable_by_default() -> None:
    """Called once by the app and the terminal runner: guardrails on unless the user set the switch."""
    os.environ.setdefault(ENV_VAR, "on")


def enabled() -> bool:
    return os.environ.get(ENV_VAR, "off").strip().lower() == "on"


def screen_question(question: str) -> str | None:
    """None if the question may run; otherwise the reason it was stopped (shown to the user)."""
    if not enabled():
        return None
    verdict = check_input(question)
    return None if verdict.get("allowed", True) else str(verdict.get("reason", "blocked by the input guard"))


def screen_answer(answer: str, question: str) -> tuple[str, str | None]:
    """(text to show, reason). A reason means the output guard withheld the answer."""
    if not enabled() or not answer:
        return answer, None
    verdict = check_output(answer, question)
    if not verdict.get("allowed", True):
        reason = str(verdict.get("reason", "blocked by the output guard"))
        return f"This answer was withheld by the output guard: {reason}.", reason
    cleaned = verdict.get("answer")
    return (answer if cleaned is None else cleaned), None


def protect(question: str, counts: Counter | None = None) -> ContextManager[Any]:
    """Tool hooks (call budget, private terms, code check, result filter, EDGAR hash) around one graph run.

    Use around every graph.invoke for the same question, with the same `counts`, so the call budget
    covers the whole request.
    """
    return install(question, counts=counts) if enabled() else contextlib.nullcontext()


def run_guarded(question: str, run: Callable[[str], str]) -> str:
    """Whole-request helper for scripts: check the question, run it under the hooks, check the answer."""
    reason = screen_question(question)
    if reason:
        return f"Question not run: {reason}."
    with protect(question):
        answer = run(question)
    return screen_answer(answer, question)[0]
