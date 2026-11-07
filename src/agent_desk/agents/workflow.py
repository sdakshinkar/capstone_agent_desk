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


# Formats one worker result as "Q: <brief>\nA: <answer>".
# narrative, facts and risk are lists that every worker call appends to (operator.add reducer in
# TeamState), so a second call, e.g. quant_worker for Alphabet after Microsoft, adds an entry
# instead of overwriting the first. Prefixing the brief keeps each entry self-describing, because
# a worker's answer does not always name the company or years it was asked about.
# aggregate_node later joins these entries under "Narrative findings", "Quant findings" and
# "Risk comparison".
# Example: _entry("What were Alphabet's operating margins for 2023-2025?", "27.4%, 32.1%, 32.0%")
#   -> "Q: What were Alphabet's operating margins for 2023-2025?\nA: 27.4%, 32.1%, 32.0%"
def _entry(task: str, output: str) -> str:
    """Label a worker result with the brief it answered, so repeat calls stay distinguishable."""
    return f"Q: {task}\nA: {output}"

#state[task] = 'Find the risk factors disclosed by Microsoft in their 10-K filings for fiscal years 2023, 2024, and 2025, specifically in Item 1A.'
#result:
#state['narrative']=['Q: Find the risk factors disclosed by Microsoft in their 10-K filings for fiscal years 2023, 2024, and 2025, specifically in Item 1A.\n
# A: The risk factors disclosed by Microsoft in their 10-K filings for fiscal years 2023, 2024, and 2025, 
# specifically in Item 1A, include risks related to the evolution of their business, economic conditions, challenges, and risks, as well as regulatory matters. 
# The filings for each year can be found in the sources listed in the output.']
def researcher_worker_node(state: TeamState) -> dict:
    try:
        narrative = run_researcher(state["task"])
    except Exception as exc:
        return _failed("researcher_worker", exc)
    return {
        "narrative": [_entry(state["task"], narrative)],
        "messages": [HumanMessage(content=narrative, name="researcher_worker")],
    }


# state["task"] is the supervisor's brief, for example
# "What were Microsoft's operating margins for fiscal years 2023, 2024 and 2025?"

#result: state["facts"] =
#["Q: What was Microsoft's operating margin for fiscal years 2023, 2024 and 2025?\n
# A: Microsoft's operating margin for fiscal years 2023, 2024, and 2025 are as follows:\n\n- 
# 2023: (88.523 billion / 211.915 billion) = 41.8%\n- 
# 2024: (109.433 billion / 245.122 billion) = 44.7%\n- 
# 2025: (128.528 billion / 281.724 billion) = 45.6%\n\n
# Note: The operating margin is calculated by dividing the operating income by the revenue for each fiscal year. 
# The values used are based on the output of the get_company_fact function calls.",
#
# "Q: What was Alphabet's operating margin for fiscal years 2023, 2024 and 2025?\n
# A: Alphabet's operating margin for fiscal years 2023, 2024 and 2025 is as follows:\n\n* 
# 2023: Operating income of $84,293,000,000 and revenue of $307,394,000,000, resulting in an operating margin of 27.4% (fiscal year 2023, form 10-K, period 2023-01-01 to 2023-12-31).\n* 
# 2024: Operating income of $112,390,000,000 and revenue of $350,018,000,000, resulting in an operating margin of 32.1% (fiscal year 2024, form 10-K, period 2024-01-01 to 2024-12-31).\n* 
# 2025: Operating income of $129,039,000,000 and revenue of $402,836,000,000, resulting in an operating margin of 32.0% (fiscal year 2025, form 10-K, period 2025-01-01 to 2025-12-31).\n\n
# Note: The operating margin is calculated by dividing the operating income by the revenue for each fiscal year."]
def quant_worker_node(state: TeamState) -> dict:
    try:
        facts = run_quant_agent(state["task"])
    except Exception as exc:
        return _failed("quant_worker", exc)
    return {
        "facts": [_entry(state["task"], facts)],
        "messages": [HumanMessage(content=facts, name="quant_worker")],
    }


def risk_worker_node(state: TeamState) -> dict:
    try:
        risk = run_risk_diff_agent(state["task"])
    except Exception as exc:
        return _failed("risk_worker", exc)
    return {
        "risk": [_entry(state["task"], risk)],
        "messages": [HumanMessage(content=risk, name="risk_worker")],
    }


def aggregate_node(state: TeamState) -> dict:
    parts: list[str] = []
    if state.get("narrative"):
        parts.append("Narrative findings:\n" + "\n\n".join(state["narrative"]))
    if state.get("facts"):
        parts.append("Quant findings:\n" + "\n\n".join(state["facts"]))
    if state.get("risk"):
        parts.append("Risk comparison:\n" + "\n\n".join(state["risk"]))
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
        "narrative": [],
        "facts": [],
        "risk": [],
        "final_answer": "",
    }
    result = app.invoke(initial, {"recursion_limit": 30})
    return result["final_answer"]
