"""LangGraph workflow for the supervisor + specialist team.

This file holds only the graph wiring and node orchestration. The supervisor
routing logic itself is kept in supervisor_agent.py, and the shared state schema
is kept in team_state.py.

Plan approval: after the research lead writes a plan, the approve_plan node pauses the run with
interrupt() so a person can approve it or edit it. It needs a checkpointer and a thread id (see
build_team_workflow). run_team_workflow is the unattended path: it builds the graph without a
checkpointer, so there is no approval step.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from .quant_agent import run_quant_agent
from ..evidence import Register, current_register, use_register
from ..llm.llm import get_tool_llm
from .compliance_critic import _TAG_RE, critique, unknown_ids
from .research_lead_agent import run_research_lead
from .researcher_agent import run_researcher
from .risk_diff_agent import run_risk_diff_agent
from .supervisor_agent import supervisor_decision
from .team_state import RESET, TeamState


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
#{'goal': "Compare Microsoft's and Alphabet's operating margins for fiscal years 2023, 2024 and 2025, 
# and describe the changes in their risk factors between consecutive years; 
# note that the goal uses the latest three available fiscal years for both companies", 
# 'sub_questions': ["What was Microsoft's operating margin for fiscal years 2023, 2024 and 2025?", 
# "What was Alphabet's operating margin for fiscal years 2023, 2024 and 2025?", 
# "What changed in Microsoft's risk factors between fiscal 2023 and fiscal 2024?", 
# "What changed in Microsoft's risk factors between fiscal 2024 and fiscal 2025?", 
# "What changed in Alphabet's risk factors between fiscal 2023 and fiscal 2024?", 
# "What changed in Alphabet's risk factors between fiscal 2024 and fiscal 2025?"], 
# 'outline': ['Operating margin comparison', 'Microsoft risk factor changes', 'Alphabet risk factor changes']}
def research_lead_node(state: TeamState) -> dict:
    question = state["question"]
    replan_count = state.get("replan_count", 0)
    replanning = bool(state.get("replan_reason"))
    feedback = None
    if replanning:
        feedback = (
            f"Previous plan: {json.dumps(state.get('plan', {}))}\n"
            f"Failed task: {state.get('task', '')}\n"
            f"Reason: {state['replan_reason']}"
        )
        replan_count += 1

    plan = _parse_plan(run_research_lead(question, feedback=feedback), question)
    summary = _plan_summary(plan, question)
    update: dict = {
        "plan": plan,
        "plan_step": 0,
        "replan_count": replan_count,
        "replan_reason": "",
        "messages": [HumanMessage(content=summary, name="research_lead")],
    }
    if replanning:
        # messages[0] is the user's question; everything after it came from the failed plan.
        removed = [RemoveMessage(id=m.id) for m in state["messages"][1:] if m.id]
        update["messages"] = removed + update["messages"]
        update["narrative"] = [RESET]
        update["facts"] = [RESET]
        update["risk"] = [RESET]
    return update


# The plan as the text message the supervisor reads in its conversation.
def _plan_summary(plan: dict, question: str) -> str:
    steps = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(plan.get("sub_questions", [])))
    structure = ", ".join(plan.get("outline", []))
    return (
        f"Plan goal: {plan.get('goal', question)}\n"
        f"Sub-questions (work steps):\n{steps}\n"
        f"Answer structure: {structure}"
    )


# Pauses the run so a person can approve or edit the plan the research lead just wrote.
#
# interrupt(payload) stops the graph and hands `payload` to whoever called invoke(); the run
# continues when they call invoke(Command(resume=answer)) on the same thread. The answer is one of:
#   {"action": "approve"}                 keep the plan as written (the string "approve" works too)
#   {"action": "edit", "plan": {...}}     use this plan instead, exactly as given
# Kept simple on purpose: an edited plan is not checked (a malformed one is the caller's problem),
# there is no reject action, and any other answer counts as approve. Checking edits and sending a
# rejected plan back to the research lead can be added later.
#
# LangGraph runs this node again from the top on resume, so nothing before interrupt() may have
# side effects (no model calls, no writes). This node only reads the state and asks.
#
# With config["configurable"]["auto_approve"] set the node returns at once without pausing.
def approve_plan_node(state: TeamState, config: RunnableConfig) -> dict:
    if (config.get("configurable") or {}).get("auto_approve"):
        return {}

    answer = interrupt({"type": "plan_approval", "question": state["question"], "plan": state["plan"]})
    if isinstance(answer, str):
        answer = {"action": answer}
    if not (isinstance(answer, dict) and answer.get("action") == "edit" and isinstance(answer.get("plan"), dict)):
        return {}

    edited = answer["plan"]
    summary = HumanMessage(
        content=_plan_summary(edited, state["question"]) + "\n(Plan edited by the user.)",
        name="research_lead",
    )
    last = state["messages"][-1]
    # Replace the lead's summary so the supervisor reads the edited plan, not the old one.
    replace = [RemoveMessage(id=last.id)] if getattr(last, "name", None) == "research_lead" and last.id else []
    return {"plan": edited, "plan_step": 0, "messages": replace + [summary]}


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
# writer_node later joins these entries under "Narrative findings", "Quant findings" and
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
    task = state["task"]
    register = current_register()
    try:
        facts = run_quant_agent(task)
        # The quant agent sometimes cites an id no tool returned (for example a calculation id
        # without having called run_python). Ask once more; if it happens again the supervisor is
        # told the worker failed and can retry or replan.
        unknown = unknown_ids(facts, register) if register else []
        if unknown:
            facts = run_quant_agent(
                f"{task}\n\nYour previous answer cited {', '.join(unknown)}, which no tool returned. "
                "Answer again: call run_python for every calculation and cite only ids that the "
                "tools returned."
            )
            unknown = unknown_ids(facts, register)
    except Exception as exc:
        return _failed("quant_worker", exc)
    if unknown:
        return _failed("quant_worker", ValueError(f"the answer cited ids no tool returned: {', '.join(unknown)}"))
    return {
        "facts": [_entry(task, facts)],
        "messages": [HumanMessage(content=facts, name="quant_worker")],
    }


#"Compare Alphabet's Item 1A risk factors for fiscal years 2024 and 2025, and list any added, removed, or materially changed risks."
def risk_worker_node(state: TeamState) -> dict:
    try:
        risk = run_risk_diff_agent(state["task"])
    except Exception as exc:
        return _failed("risk_worker", exc)
    return {
        "risk": [_entry(state["task"], risk)],
        "messages": [HumanMessage(content=risk, name="risk_worker")],
    }


# System prompt for the final writer call inside writer_node.
WRITER_PROMPT = """You write the final answer to a user's question about companies' 10-K filings.
You are given the question, a suggested answer structure (outline), the findings that research
workers returned (each as Q: and A:), and the supervisor's notes.

Rules:
- Use only facts and numbers that appear in the findings. Do not add outside knowledge.
- Findings carry evidence ids in square brackets, such as [F1] (a reported fact), [D1] (a
  calculation) and [P3] or [microsoft-2025-1A-37] (a filing passage). Every figure you write
  must keep the id it has in the findings, written right after it, for example "operating
  margin 45.6% [D1]". Every claim taken from a filing passage must end with that passage's id.
  Copy ids exactly; never invent, merge or move an id.
- A claim from filing passages is followed by at most 3 passage ids: the 3 that best support it,
  even when the findings list many more. Keep one claim per sentence.
- Do not calculate new numbers. Make comparisons in words using figures the findings already
  contain. If a comparison needs a figure no worker produced, say it was not calculated.
- Answer the question directly and make the comparison it asks for, across companies, across
  years, or both.
- Follow the outline's headings where they fit.
- If something the question asks for is missing, or a finding says it was not available, say so
  plainly. Do not fill the gap with a guess.
- If the notes say an attempt was superseded (for example a year was not available so another
  year is reported), state which year the numbers are for.
- Do not promise returns, recommend buying, selling or holding, or give price targets.
- Be concise. Do not repeat the findings verbatim; they are attached separately.

If a previous draft and a list of issues are given, return a corrected version of that draft:
fix every issue, change nothing else, and keep the same rules. If an issue says the draft was cut
off, write the whole note again, shorter."""


# Formats everything the writer needs into one user message: question, outline, supervisor notes
# and the worker findings. `evidence` is the already-built "Quant findings: ..." text blocks.
# On a revision it also carries the previous draft and the critic's issues.
def _writer_input(state: TeamState, notes: str, evidence: list[str]) -> str:
    outline = "\n".join(f"- {h}" for h in (state.get("plan") or {}).get("outline", []))
    message = (
        f"Question:\n{state.get('question', '')}\n\n"
        f"Suggested answer structure:\n{outline or '(none)'}\n\n"
        f"Supervisor notes:\n{notes or '(none)'}\n\n"
        "Findings:\n\n" + "\n\n".join(evidence)
    )
    if state.get("draft") and state.get("critic_issues"):
        issues = "\n".join(
            f"- {i['type']}: \"{i['text']}\": {i['detail']}" for i in state["critic_issues"]
        )
        message += f"\n\nPrevious draft:\n{state['draft']}\n\nIssues to fix:\n{issues}"
    return message


# The worker findings as text blocks, one per kind of worker that returned something.
def _evidence(state: TeamState) -> list[str]:
    evidence: list[str] = []
    if state.get("narrative"):
        evidence.append("Narrative findings:\n" + "\n\n".join(state["narrative"]))
    if state.get("facts"):
        evidence.append("Quant findings:\n" + "\n\n".join(state["facts"]))
    if state.get("risk"):
        evidence.append("Risk comparison:\n" + "\n\n".join(state["risk"]))
    return evidence


# The answer the user sees: the written draft, then the findings attached unchanged.
def _assemble(written: str, evidence: list[str]) -> str:
    parts: list[str] = []
    if written:
        parts.append(written)
    if evidence:
        parts.append("Supporting findings:\n\n" + "\n\n".join(evidence))
    return "\n\n".join(parts)


# The writer node. It runs after the supervisor chooses FINISH (supervisor -> writer -> critic),
# and again after each critic rejection, and sets two things:
#   draft:        one model call that reads the question, the plan's outline, every worker entry
#                 (Q:/A:) and the supervisor's FINISH report (kept in state["task"]; it explains
#                 superseded attempts such as "FY2026 not available, used FY2025") and writes the
#                 comparison the user asked for. On a revision the call also gets the previous
#                 draft and the critic's issues.
#   final_answer: the draft plus "Supporting findings", the worker entries appended unchanged by
#                 code. The model never rewrites them, so every number in the draft can be checked
#                 against its source.
# The model is called every time there are findings. With no worker output there is nothing to
# write from, so the supervisor's report is the draft. If the call fails, the draft falls back to
# the supervisor's report, so a model error cannot lose the results.
def writer_node(state: TeamState) -> dict:
    notes = state.get("task", "") if state.get("next") == "FINISH" else ""
    evidence = _evidence(state)

    written = notes
    truncated = False
    if evidence:
        try:
            reply = get_tool_llm(max_tokens=WRITER_MAX_TOKENS).invoke(
                [("system", WRITER_PROMPT), ("user", _writer_input(state, notes, evidence))]
            )
            written = _cap_ids_per_tag(str(reply.content).strip()) or notes
            # finish_reason "length" means the reply hit the output limit and stops mid-text.
            truncated = (getattr(reply, "response_metadata", None) or {}).get("finish_reason") == "length"
        except Exception:
            written = notes

    # A draft already exists and the critic rejected it, so this call is a revision.
    revising = bool(state.get("draft") and state.get("critic_issues"))
    return {
        "draft": written,
        "draft_truncated": truncated,
        "final_answer": _assemble(written, evidence),
        "revision": state.get("revision", 0) + (1 if revising else 0),
    }


MAX_REVISIONS = 2
# Output limit for the writer's reply; a note that needs more is treated as cut off.
WRITER_MAX_TOKENS = 3000
# The writer is told to cite at most this many passages per claim but often lists dozens, which
# bloats the note and risks the output limit, so the draft is trimmed in code.
MAX_IDS_PER_TAG = 3


def _cap_ids_per_tag(text: str) -> str:
    """Keep at most MAX_IDS_PER_TAG ids in each evidence tag, spread across the list.

    The old year's ids come first in a risk comparison and the new year's last, so picking the
    first, middle and last keeps both years.
    Example: "[a-2023-1A-1, a-2023-1A-2, a-2024-1A-1, a-2024-1A-2, a-2024-1A-3]"
             -> "[a-2023-1A-1, a-2024-1A-1, a-2024-1A-3]"
    """
    def trim(match) -> str:
        ids = [i.strip() for i in match.group(1).split(",")]
        if len(ids) <= MAX_IDS_PER_TAG:
            return match.group(0)
        last = len(ids) - 1
        picks = sorted({round(n * last / (MAX_IDS_PER_TAG - 1)) for n in range(MAX_IDS_PER_TAG)})
        return "[" + ", ".join(ids[p] for p in picks) + "]"

    return _TAG_RE.sub(trim, text)


# The compliance critic node. It checks the draft against the evidence register (see
# agents/compliance_critic.py). A draft that passes ends the run. A draft that fails goes back to
# the writer with the issues, up to MAX_REVISIONS times. After the last revision the answer is
# returned anyway, with the unresolved issues listed above the findings, so a failing note is
# never passed off as checked. Without an active register there is nothing to check against and
# the critic does nothing.
def critic_node(state: TeamState) -> dict:
    register = current_register()
    if register is None:
        # Nothing to check against: report "not checked" (None), never a pass.
        return {"critic_passed": None, "critic_issues": []}

    verdict = critique(state.get("draft", ""), register)
    issues = list(verdict["issues"])
    if state.get("draft_truncated"):
        # The check cannot judge text that was never written, so a cut-off draft always fails.
        issues.insert(0, {
            "type": "truncated", "text": "", "start": 0,
            "detail": "The draft was cut off before the end. Write the whole note again, shorter.",
        })
    update: dict = {"critic_passed": not issues, "critic_issues": issues}
    if not issues or state.get("revision", 0) < MAX_REVISIONS:
        return update

    unresolved = "\n".join(f"- {i['detail']} (\"{i['text']}\")" if i["text"] else f"- {i['detail']}"
                           for i in issues)
    flagged = (
        f"{state.get('draft', '')}\n\n**Compliance review: this note did not pass after "
        f"{MAX_REVISIONS} revisions. Unresolved issues:**\n{unresolved}"
    )
    update["final_answer"] = _assemble(flagged, _evidence(state))
    return update


# After the critic: back to the writer for a revision, or finished (passed, or out of revisions).
def after_critic(state: TeamState) -> str:
    if state.get("critic_passed") is False and state.get("revision", 0) < MAX_REVISIONS:
        return "writer"
    return END


# Builds the graph: research_lead -> approve_plan -> supervisor <-> workers -> writer -> critic,
# with the critic sending a failing draft back to the writer (at most MAX_REVISIONS times).
# After a supervisor REPLAN the new plan goes through approval again.
# The approval step needs a `checkpointer` (for example langgraph.checkpoint.memory.InMemorySaver()):
# it saves the run's state so interrupt() can pause and a later call can resume, and every run
# needs a thread id in its config. WITHOUT a checkpointer the approve_plan node is left out
# (research_lead -> supervisor), because a pause that cannot be saved would silently stop the run
# with an empty answer. Pass config={"configurable": {"auto_approve": True}} to skip the pause on
# a graph that has a checkpointer.
def build_team_workflow(checkpointer: Any | None = None):
    workflow = StateGraph(TeamState)
    workflow.add_node("research_lead", research_lead_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("researcher_worker", researcher_worker_node)
    workflow.add_node("quant_worker", quant_worker_node)
    workflow.add_node("risk_worker", risk_worker_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("critic", critic_node)

    workflow.set_entry_point("research_lead")
    if checkpointer is None:
        workflow.add_edge("research_lead", "supervisor")
    else:
        workflow.add_node("approve_plan", approve_plan_node)
        workflow.add_edge("research_lead", "approve_plan")
        workflow.add_edge("approve_plan", "supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        lambda state: state.get("next", "FINISH"),
        {
            "researcher_worker": "researcher_worker",
            "quant_worker": "quant_worker",
            "risk_worker": "risk_worker",
            "REPLAN": "research_lead",
            "FINISH": "writer",
        },
    )

    workflow.add_edge("researcher_worker", "supervisor")
    workflow.add_edge("quant_worker", "supervisor")
    workflow.add_edge("risk_worker", "supervisor")
    workflow.add_edge("writer", "critic")
    workflow.add_conditional_edges("critic", after_critic, {"writer": "writer", END: END})

    return workflow.compile(checkpointer=checkpointer)


# The state a run starts from. Kept in one place so run_team_workflow and an interactive caller
# (which resumes the same thread after approval) start identically.
def initial_state(question: str) -> TeamState:
    return {
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
        "draft": "",
        "draft_truncated": False,
        "revision": 0,
        "critic_issues": [],
        "critic_passed": False,
        "final_answer": "",
    }


# The unattended path: runs the whole graph in one call with no approval step (no checkpointer, so
# nobody is asked). The recursion limit counts graph steps; it is 40 to leave room for the extra
# rounds of a plan with many sub-questions and for one replan.
#question='Compare Microsoft’s and Alphabet’s operating margins over the last three fiscal years,
#  and tell me what changed in their risk factors.'
def run_team_workflow(question: str, register: Register | None = None) -> str:
    # The tools record their evidence in the active register. Pass one to keep the records
    # afterwards (for example for the critic); otherwise a fresh one is used for this run.
    use_register(register if register is not None else Register())
    app = build_team_workflow()
    result = app.invoke(initial_state(question), {"recursion_limit": 50})
    return result["final_answer"]
