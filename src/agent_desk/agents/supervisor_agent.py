"""Supervisor decision logic for the L11-style team supervisor.

This file keeps only the reasoning/selection behavior. The workflow graph and
shared state schema live in workflow.py and team_state.py.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, SystemMessage

from ..llm.llm import get_tool_llm
from .team_state import Route, TeamState


def supervisor_decision(state: TeamState) -> TeamState:
    """Choose the next specialist worker and write the brief for it."""
    system = (
        "You are the supervisor. You coordinate these workers and never do their work yourself:\n"
        "- researcher_worker: reads filings and returns narrative findings\n"
        "- quant_worker: retrieves SEC fact values and computes numeric answers\n"
        "- risk_worker: compares year-over-year risk-factor text\n"
        "- FINISH: stop when the answer is complete or no worker can help\n\n"
        "A worker sees only the brief you write for it, not the full conversation. "
        "Reports stay in this conversation. One worker at a time. "
        "When the job is done, choose FINISH and put your final report in `message`."
    )

    router = get_tool_llm().with_structured_output(
        Route,
        method="json_schema",
        strict=True,
        include_raw=True,
    )

    out = router.invoke([SystemMessage(content=system), *state["messages"]])
    choice = out["parsed"] or {"next": "FINISH", "message": "STOPPED: invalid route"}

    if choice.get("next") not in {"researcher_worker", "quant_worker", "risk_worker", "FINISH"}:
        choice = {"next": "FINISH", "message": "STOPPED: invalid route returned by supervisor"}

    state["next"] = choice["next"]
    state["task"] = choice["message"]
    state["messages"] = [
        *state["messages"],
        AIMessage(content=f"[to {choice['next']}] {choice['message']}"),
    ]
    return state


def run_supervisor(question: str) -> str:
    """Convenience wrapper when the supervisor is called directly."""
    from langchain_core.messages import HumanMessage

    initial: TeamState = {
        "messages": [HumanMessage(content=question)],
        "next": "",
        "task": "",
        "narrative": "",
        "facts": "",
        "risk": "",
        "final_answer": "",
    }
    result = supervisor_decision(initial)
    return result["task"]
