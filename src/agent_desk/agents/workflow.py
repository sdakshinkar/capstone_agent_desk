"""LangGraph workflow for the supervisor + specialist team.

This file holds only the graph wiring and node orchestration. The supervisor
routing logic itself is kept in supervisor_agent.py, and the shared state schema
is kept in team_state.py.
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from .quant_agent import run_quant_agent
from .research_lead_agent import run_research_lead
from .researcher_agent import run_researcher
from .risk_diff_agent import run_risk_diff_agent
from .supervisor_agent import supervisor_decision
from .team_state import TeamState


def _parse_plan(raw: str, question: str) -> dict:
    """Parse the lead's JSON, tolerating markdown code fences around it."""
    start, end = raw.find("{"), raw.rfind("}")
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {
            "goal": question,
            "sub_questions": [question],
            "outline": ["Gather evidence for the question", "Answer the question"],
        }

# Example plan from the research lead:
#{'goal': "Compare Microsoft and Alphabet's operating margins and risk factor changes", 
# 'sub_questions': ["What was Microsoft's operating margin for fiscal years 2023, 2024 and 2025?", 
# "What was Alphabet's operating margin for fiscal years 2023, 2024 and 2025?", 
# 'What risk factors did Microsoft disclose for fiscal years 2023, 2024 and 2025?', 
# 'What risk factors did Alphabet disclose for fiscal years 2023, 2024 and 2025?'], 
# 'outline': ['Operating margin comparison', 'Risk factor changes for Microsoft', 'Risk factor changes for Alphabet']}
def research_lead_node(state: TeamState) -> dict:
    question = state["question"]
    replan_count = state.get("replan_count", 0)
    feedback = None
    if state.get("replan_reason"):
        feedback = (
            f"Previous plan: {json.dumps(state.get('plan', {}))}\n"
            f"Failed task: {state.get('task', '')}\n"
            f"Reason: {state['replan_reason']}"
        )
        replan_count += 1

    plan = _parse_plan(run_research_lead(question, feedback=feedback), question)
    steps = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(plan.get("sub_questions", [])))
    structure = ", ".join(plan.get("outline", []))
    summary = (
        f"Plan goal: {plan.get('goal', question)}\n"
        f"Sub-questions (work steps):\n{steps}\n"
        f"Answer structure: {structure}"
    )
    return {
        "plan": plan,
        "plan_step": 0,
        "replan_count": replan_count,
        "replan_reason": "",
        "messages": [HumanMessage(content=summary, name="research_lead")],
    }


def supervisor_node(state: TeamState) -> dict:
    return supervisor_decision(state)


def _failed(worker: str, exc: Exception) -> dict:
    """Report a crashed worker to the supervisor so it can retry or replan."""
    report = f"WORKER FAILED: {type(exc).__name__}: {str(exc)[:200]}"
    return {"messages": [HumanMessage(content=report, name=worker)]}


def researcher_worker_node(state: TeamState) -> dict:
    try:
        narrative = run_researcher(state["task"])
    except Exception as exc:
        return _failed("researcher_worker", exc)
    return {
        "narrative": narrative,
        "messages": [HumanMessage(content=narrative, name="researcher_worker")],
    }

# state["task"]
# "What was Microsoft's operating margin for fiscal year 2023?"
def quant_worker_node(state: TeamState) -> dict:
    try:
        facts = run_quant_agent(state["task"])
    except Exception as exc:
        return _failed("quant_worker", exc)
    return {
        "facts": facts,
        "messages": [HumanMessage(content=facts, name="quant_worker")],
    }


def risk_worker_node(state: TeamState) -> dict:
    try:
        risk = run_risk_diff_agent(state["task"])
    except Exception as exc:
        return _failed("risk_worker", exc)
    return {
        "risk": risk,
        "messages": [HumanMessage(content=risk, name="risk_worker")],
    }


def aggregate_node(state: TeamState) -> dict:
    parts: list[str] = []
    if state.get("narrative"):
        parts.append("Narrative findings:\n" + state["narrative"])
    if state.get("facts"):
        parts.append("Quant findings:\n" + state["facts"])
    if state.get("risk"):
        parts.append("Risk comparison:\n" + state["risk"])
    # With no worker output, the supervisor's FINISH report is the answer.
    return {"final_answer": "\n\n".join(parts) or state.get("task", "")}


def build_team_workflow():
    workflow = StateGraph(TeamState)
    workflow.add_node("research_lead", research_lead_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("researcher_worker", researcher_worker_node)
    workflow.add_node("quant_worker", quant_worker_node)
    workflow.add_node("risk_worker", risk_worker_node)
    workflow.add_node("aggregate", aggregate_node)

    workflow.set_entry_point("research_lead")
    workflow.add_edge("research_lead", "supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        lambda state: state.get("next", "FINISH"),
        {
            "researcher_worker": "researcher_worker",
            "quant_worker": "quant_worker",
            "risk_worker": "risk_worker",
            "REPLAN": "research_lead",
            "FINISH": "aggregate",
        },
    )

    workflow.add_edge("researcher_worker", "supervisor")
    workflow.add_edge("quant_worker", "supervisor")
    workflow.add_edge("risk_worker", "supervisor")
    workflow.add_edge("aggregate", END)

    return workflow.compile()


#question='Compare Microsoft’s and Alphabet’s operating margins over the last three fiscal years,
#  and tell me what changed in their risk factors.'
def run_team_workflow(question: str) -> str:
    app = build_team_workflow()
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
    result = app.invoke(initial, {"recursion_limit": 30})
    return result["final_answer"]
