"""Supervisor decision logic for the L11-style team supervisor.

This file keeps only the reasoning/selection behavior. The workflow graph and
shared state schema live in workflow.py and team_state.py.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..llm.llm import get_tool_llm
from .team_state import TeamState

WORKERS = {"researcher_worker", "quant_worker", "risk_worker"}
VALID_ROUTES = WORKERS | {"REPLAN", "FINISH"}


class Route(TypedDict):
    next: Literal["researcher_worker", "quant_worker", "risk_worker", "REPLAN", "FINISH"]
    message: str

# example:
#    1. Get FY2025 annual report
# -> 2. Get operating income
#    3. Verify the figure
def _plan_text(state: TeamState) -> str:
    plan = state.get("plan") or {}
    outline = plan.get("outline", [])
    if not outline:
        return "No plan is available."
    step = min(state.get("plan_step", 0), len(outline) - 1)
    lines = [f"{'->' if i == step else '  '} {i + 1}. {s}" for i, s in enumerate(outline)]
    return f"Goal: {plan.get('goal', '')}\nPlan steps (current step marked ->):\n" + "\n".join(lines)


def supervisor_decision(state: TeamState) -> dict:
    """Choose the next worker (or REPLAN / FINISH) and write the brief for it."""
    replan_count = state.get("replan_count", 0)
    replans_left = state.get("max_replans", 2) - replan_count
    system = (
        "You are the supervisor. You coordinate these workers and never do their work yourself:\n"
        "- researcher_worker: searches 10-K filing text (Item 1A risk factors, Item 7 MD&A, etc.) "
        "for a company and fiscal year and returns narrative passages with citations.\n"
        "- quant_worker: looks up reported numbers (revenue, operating income, ...) for a company "
        "and fiscal year from SEC Company Facts and computes ratios. It cannot return dates or text.\n"
        "- risk_worker: compares Item 1A risk factors year over year.\n"
        "- REPLAN: ask the research lead for a new plan. Choose it when a worker reports an error "
        "(WORKER FAILED), an empty result, 'no passages' or 'could not find', or when the plan "
        "cannot be answered with the workers' tools. Put the reason in `message`. "
        f"Replans left: {replans_left}.\n"
        "- FINISH: stop when the answer is complete or cannot be completed; put your final "
        "report in `message`.\n\n"
        f"{_plan_text(state)}\n\n"
        "Write the brief for the current plan step (marked ->) only, as one concrete question the "
        "chosen worker's tools can answer, with the company, fiscal year and metric spelled out. "
        "Do not work on later steps yet. If the current step cannot be answered by any worker as "
        "written, rephrase it into a question one can answer; if that is impossible, choose "
        "REPLAN. A worker sees only the brief you write for it, not the conversation. "
        "Never ask for something a worker has already reported. One worker at a time."
    )

    router = get_tool_llm().with_structured_output(
        Route,
        method="json_schema",
        strict=True,
        include_raw=True,
    )

    messages = state["messages"]
    try:
        out = router.invoke([SystemMessage(content=system), *messages])
        choice = out["parsed"] or {}
    except Exception as exc:
        choice = {"error": type(exc).__name__}

    next_step = choice.get("next")
    message = choice.get("message", "")
    if next_step not in VALID_ROUTES:
        next_step, message = "FINISH", f"STOPPED: supervisor returned no usable route {choice}"
    if next_step == "REPLAN" and replans_left <= 0:
        next_step = "FINISH"
        message = f"Could not complete the request after {replan_count} replans. Last problem: {message}"

    update: dict = {
        "next": next_step,
        "messages": [AIMessage(content=f"[to {next_step}] {message}", name="supervisor")],
    }
    if next_step == "REPLAN":
        update["replan_reason"] = message
    else:
        update["task"] = message
        last = messages[-1] if messages else None
        # Moving on after a successful worker report means the current plan step is done.
        if (
            next_step in WORKERS
            and getattr(last, "name", None) in WORKERS
            and not str(last.content).startswith("WORKER FAILED")
        ):
            update["plan_step"] = state.get("plan_step", 0) + 1
    return update


def run_supervisor(question: str) -> str:
    """Convenience wrapper when the supervisor is called directly."""
    initial: TeamState = {
        "question": question,
        "messages": [HumanMessage(content=question)],
        "next": "",
        "task": "",
        "plan": {},
        "plan_step": 0,
        "replan_count": 0,
        "max_replans": 2,
        "replan_reason": "",
        "narrative": "",
        "facts": "",
        "risk": "",
        "final_answer": "",
    }
    return supervisor_decision(initial)["task"]
