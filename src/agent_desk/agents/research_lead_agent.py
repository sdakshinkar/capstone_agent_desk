"""Research lead: turn a user question into brief, sub-questions and a plan."""

from __future__ import annotations

from typing import Any

from langgraph.prebuilt import create_react_agent

from ..llm.llm import get_tool_llm

SYSTEM_PROMPT = """You are the research lead for a filings research assistant.

Your job is not to answer the user's question directly. First, produce a brief research plan.

Return a JSON object with exactly these keys:
{
  "goal": "short statement of the user goal",
  "sub_questions": ["3 to 5 short sub-questions"],
  "outline": ["3 to 5 short plan steps"],
  "route": "filing_retrieval" | "company_facts" | "both"
}

Rules:
- Use company and year when the user mentions them.
- If the question wants a reported number, choose "company_facts".
- If the question is about sections, risk factors, or narrative content, choose "filing_retrieval".
- If the question needs both numbers and narrative context, choose "both".
- Keep the values short, concrete and useful for a worker agent.
- Return only valid JSON.
"""


def build_research_lead(llm: Any | None = None):
    llm = llm or get_tool_llm()
    return create_react_agent(llm, tools=[], prompt=SYSTEM_PROMPT)


def run_research_lead(question: str, llm: Any | None = None) -> str:
    agent = build_research_lead(llm)
    result = agent.invoke({"messages": [("user", question)]}, {"recursion_limit": 10})
    return result["messages"][-1].content
