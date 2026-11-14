"""LangGraph orchestration for research lead + specialist workers."""

from __future__ import annotations

import json
from typing import TypedDict

from langgraph.graph import END, StateGraph

try:
    from langsmith import traceable
except ImportError:  # pragma: no cover - optional in local dev
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

from .quant_agent import run_quant_agent
from .research_lead_agent import run_research_lead
from .researcher_agent import run_researcher
from .risk_diff_agent import run_risk_diff_agent


class WorkflowState(TypedDict):
    question: str
    plan: dict
    route: str
    narrative: str
    facts: str
    risk: str
    final_answer: str


@traceable(run_type="chain", name="research_lead")
def research_lead_node(state: WorkflowState) -> WorkflowState:
    brief = run_research_lead(state["question"])
    try:
        plan = json.loads(brief)
    except json.JSONDecodeError:
        plan = {
            "goal": "Answer the user question by gathering evidence",
            "sub_questions": [
                "What is the company and year?",
                "What facts or narrative sections are needed?",
                "What changed compared with the prior year?",
            ],
            "outline": [
                "Identify company and year",
                "Gather filings or facts",
                "Compare the relevant evidence",
                "Answer and explain",
            ],
            "route": "both",
        }
    state["plan"] = plan
    state["route"] = plan.get("route", "both")
    return state


# Reserved for later: this node is intentionally not connected yet.
# Re-enable it when we want a human approval step between research lead and routing.
@traceable(run_type="chain", name="analyst_interrupt")
def analyst_interrupt_node(state: WorkflowState) -> WorkflowState:
    print("Research lead plan:")
    print(json.dumps(state["plan"], indent=2))
    try:
        edited = input("Press Enter to accept, or paste a revised JSON plan: ").strip()
    except EOFError:
        edited = ""

    if edited:
        try:
            state["plan"] = json.loads(edited)
            state["route"] = state["plan"].get("route", state.get("route", "both"))
        except json.JSONDecodeError:
            pass    # Placeholder kept for future use; the workflow is currently simplified to a direct lead -> router path.
    return state


@traceable(run_type="chain", name="router")
def router_node(state: WorkflowState) -> WorkflowState:
    state["route"] = state.get("route", "both")
    return state


@traceable(run_type="chain", name="researcher_worker")
def researcher_worker_node(state: WorkflowState) -> WorkflowState:
    state["narrative"] = run_researcher(state["question"])
    return state


@traceable(run_type="chain", name="quant_worker")
def quant_worker_node(state: WorkflowState) -> WorkflowState:
    state["facts"] = run_quant_agent(state["question"])
    return state


@traceable(run_type="chain", name="risk_worker")
def risk_worker_node(state: WorkflowState) -> WorkflowState:
    state["risk"] = run_risk_diff_agent(state["question"])
    return state


@traceable(run_type="chain", name="aggregate")
def aggregate_node(state: WorkflowState) -> WorkflowState:
    parts: list[str] = []
    if state.get("narrative"):
        parts.append("Narrative findings:\n" + state["narrative"])
    if state.get("facts"):
        parts.append("Quant findings:\n" + state["facts"])
    if state.get("risk"):
        parts.append("Risk comparison:\n" + state["risk"])
    state["final_answer"] = "\n\n".join(parts)
    return state


def build_workflow():
    workflow = StateGraph(WorkflowState)
    workflow.add_node("research_lead", research_lead_node)
    workflow.add_node("analyst_interrupt", analyst_interrupt_node)
    workflow.add_node("router", router_node)
    workflow.add_node("researcher_worker", researcher_worker_node)
    workflow.add_node("quant_worker", quant_worker_node)
    workflow.add_node("risk_worker", risk_worker_node)
    workflow.add_node("aggregate", aggregate_node)

    workflow.set_entry_point("research_lead")
    workflow.add_edge("research_lead", "router")
    workflow.add_edge("router", "researcher_worker")
    workflow.add_edge("researcher_worker", "quant_worker")
    workflow.add_edge("quant_worker", "risk_worker")
    workflow.add_edge("risk_worker", "aggregate")

    workflow.add_conditional_edges(
        "aggregate",
        lambda state: END,
        {END: END},
    )

    return workflow.compile()


def run_langgraph_workflow(question: str) -> str:
    app = build_workflow()
    result = app.invoke({"question": question})
    return result["final_answer"]
