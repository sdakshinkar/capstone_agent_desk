"""LangGraph workflow for the supervisor + specialist team.

This file holds only the graph wiring and node orchestration. The supervisor
routing logic itself is kept in supervisor_agent.py, and the shared state schema
is kept in team_state.py.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from .quant_agent import run_quant_agent
from .researcher_agent import run_researcher
from .risk_diff_agent import run_risk_diff_agent
from .supervisor_agent import supervisor_decision
from .team_state import TeamState


def supervisor_node(state: TeamState) -> TeamState:
    return supervisor_decision(state)


def researcher_worker_node(state: TeamState) -> TeamState:
    state["narrative"] = run_researcher(state["task"])
    state["messages"].append(HumanMessage(content=state["narrative"], name="researcher_worker"))
    return state


def quant_worker_node(state: TeamState) -> TeamState:
    state["facts"] = run_quant_agent(state["task"])
    state["messages"].append(HumanMessage(content=state["facts"], name="quant_worker"))
    return state


def risk_worker_node(state: TeamState) -> TeamState:
    state["risk"] = run_risk_diff_agent(state["task"])
    state["messages"].append(HumanMessage(content=state["risk"], name="risk_worker"))
    return state


def aggregate_node(state: TeamState) -> TeamState:
    parts: list[str] = []
    if state.get("narrative"):
        parts.append("Narrative findings:\n" + state["narrative"])
    if state.get("facts"):
        parts.append("Quant findings:\n" + state["facts"])
    if state.get("risk"):
        parts.append("Risk comparison:\n" + state["risk"])
    state["final_answer"] = "\n\n".join(parts)
    return state


def build_team_workflow():
    workflow = StateGraph(TeamState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("researcher_worker", researcher_worker_node)
    workflow.add_node("quant_worker", quant_worker_node)
    workflow.add_node("risk_worker", risk_worker_node)
    workflow.add_node("aggregate", aggregate_node)

    workflow.set_entry_point("supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        lambda state: state.get("next", "FINISH"),
        {
            "researcher_worker": "researcher_worker",
            "quant_worker": "quant_worker",
            "risk_worker": "risk_worker",
            "FINISH": "aggregate",
        },
    )

    workflow.add_edge("researcher_worker", "supervisor")
    workflow.add_edge("quant_worker", "supervisor")
    workflow.add_edge("risk_worker", "supervisor")
    workflow.add_edge("aggregate", END)

    return workflow.compile()


def run_team_workflow(question: str) -> str:
    app = build_team_workflow()
    initial: TeamState = {
        "messages": [HumanMessage(content=question)],
        "next": "",
        "task": "",
        "narrative": "",
        "facts": "",
        "risk": "",
        "final_answer": "",
    }
    result = app.invoke(initial,{"recursion_limit": 30})
    return result["final_answer"]
