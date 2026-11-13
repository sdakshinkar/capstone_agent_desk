"""The three systems compared in experiment E1, behind one interface.

    run_system(name, question, callbacks) -> {"answer", "contexts", "replans", "worker_reports"}

c0_single_prompt  fixed retrieval + one LLM call            (agents/single_prompt_baseline.py)
c1_single_agent   one ReAct agent with all five tools       (agents/single_agent.py)
c2_team           research lead + supervisor + 3 workers    (agents/workflow.py, unchanged)

Each call is wrapped in a RunnableLambda so the callbacks reach every nested model and tool
call, including the worker agents that the team graph starts inside its nodes.
"""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda

SYSTEMS_WITH_TOOLS = {"c1_single_agent", "c2_team"}
# Only the team's quant worker has the run_python calculator (agents/quant_agent.py).
SYSTEMS_WITH_SANDBOX = {"c2_team"}
WORKERS = {"researcher_worker", "quant_worker", "risk_worker"}


def _c0(question: str) -> dict[str, Any]:
    from agent_desk.agents.single_prompt_baseline import run_single_prompt

    answer, passages = run_single_prompt(question)
    return {"answer": answer, "contexts": [p["text"] for p in passages], "replans": 0, "worker_reports": []}


def _c1(question: str) -> dict[str, Any]:
    from agent_desk.agents.single_agent import run_single_agent

    return {"answer": run_single_agent(question), "contexts": [], "replans": 0, "worker_reports": []}


def _c2(question: str) -> dict[str, Any]:
    from agent_desk.agents.workflow import build_team_workflow

    initial = {
        "question": question,
        "messages": [HumanMessage(content=question)],
        "next": "",
        "task": "",
        "plan": {},
        "plan_step": 0,
        "replan_count": 0,
        "max_replans": 2,
        "replan_reason": "",
        "narrative": [],
        "facts": [],
        "risk": [],
        "final_answer": "",
    }
    state = build_team_workflow().invoke(initial, {"recursion_limit": 30})
    reports = [str(m.content) for m in state["messages"] if getattr(m, "name", None) in WORKERS]
    return {
        "answer": state["final_answer"],
        "contexts": [],
        "replans": state.get("replan_count", 0),
        "worker_reports": reports,
        "plan": state.get("plan", {}),
    }


SYSTEMS: dict[str, Callable[[str], dict[str, Any]]] = {
    "c0_single_prompt": _c0,
    "c1_single_agent": _c1,
    "c2_team": _c2,
}


def run_system(name: str, question: str, callbacks: list | None = None) -> dict[str, Any]:
    if name not in SYSTEMS:
        raise ValueError(f"Unknown system {name!r}; choose from {sorted(SYSTEMS)}")
    return RunnableLambda(SYSTEMS[name], name=f"eval:{name}").invoke(
        question, {"callbacks": callbacks or []}
    )
