"""The three systems compared in experiment E1, behind one interface.

    run_system(name, question, callbacks) -> {"answer", "contexts", "replans", "worker_reports"}

c0_single_prompt  fixed retrieval + one LLM call            (agents/single_prompt_baseline.py)
c1_single_agent   one ReAct agent with all six tools        (agents/single_agent.py)
c2_team           research lead + supervisor + 3 workers + writer + compliance critic
                                                            (agents/workflow.py, unchanged)

Each call is wrapped in a RunnableLambda so the callbacks reach every nested model and tool
call, including the worker agents that the team graph starts inside its nodes.
"""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.runnables import RunnableLambda

SYSTEMS_WITH_TOOLS = {"c1_single_agent", "c2_team"}
# Systems with the run_python calculator: the team's quant worker and, since 2026-11-13, C1.
SYSTEMS_WITH_SANDBOX = {"c1_single_agent", "c2_team"}
WORKERS = {"researcher_worker", "quant_worker", "risk_worker"}


def _no_register() -> None:
    """C0 and C1 have no critic: run their tools without an evidence register (no F/D/P ids)."""
    from agent_desk.evidence import use_register

    use_register(None)


def _c0(question: str) -> dict[str, Any]:
    from agent_desk.agents.single_prompt_baseline import run_single_prompt

    _no_register()

    answer, passages = run_single_prompt(question)
    return {"answer": answer, "contexts": [p["text"] for p in passages], "replans": 0, "worker_reports": []}


def _c1(question: str) -> dict[str, Any]:
    from agent_desk.agents.single_agent import run_single_agent

    _no_register()

    return {"answer": run_single_agent(question), "contexts": [], "replans": 0, "worker_reports": []}


# Same graph step limit as workflow.run_team_workflow (the critic's revision rounds need room).
C2_RECURSION_LIMIT = 50


def _c2(question: str) -> dict[str, Any]:
    from agent_desk.agents.workflow import build_team_workflow, initial_state
    from agent_desk.evidence import Register, use_register

    # Run exactly as workflow.run_team_workflow does: a fresh evidence register, so the tools issue
    # F/D/P ids and the compliance critic runs (without a register the critic skips itself). The
    # graph is invoked here rather than through run_team_workflow to keep the final state.
    register = Register()
    use_register(register)
    state = build_team_workflow().invoke(initial_state(question), {"recursion_limit": C2_RECURSION_LIMIT})
    reports = [str(m.content) for m in state["messages"] if getattr(m, "name", None) in WORKERS]
    issues = state.get("critic_issues") or []
    return {
        "answer": state["final_answer"],
        "contexts": [],
        "replans": state.get("replan_count", 0),
        "worker_reports": reports,
        "plan": state.get("plan", {}),
        "critic": {
            "passed": state.get("critic_passed"),  # None: the critic did not run
            "revisions": state.get("revision", 0),
            "issues": [{"type": i.get("type"), "detail": str(i.get("detail", ""))[:200]} for i in issues],
        },
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
