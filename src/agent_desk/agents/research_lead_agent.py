"""Research lead: turn a user question into brief, sub-questions and a plan."""

from __future__ import annotations

from typing import Any

from langgraph.prebuilt import create_react_agent

from ..llm.llm import get_tool_llm

SYSTEM_PROMPT = """You are the research lead for a filings research assistant.

Your job is not to answer the user's question directly. Produce a brief research plan.

Return a JSON object with exactly these keys:
{
  "goal": "short statement of the user goal",
  "sub_questions": ["3 to 5 short sub-questions"],
  "outline": ["3 to 5 short plan steps"]
}

Rules:
- Use company and year when the user mentions them.
- Each outline step says what evidence is needed (for example "get Apple FY2025 operating
  income"), not which agent or tool to use.
- Keep the values short and concrete.
- If you are given feedback about a failed earlier plan, write a revised plan that takes a
  different approach and does not repeat the failed step.
- Return only valid JSON.
"""


def build_research_lead(llm: Any | None = None):
    llm = llm or get_tool_llm()
    return create_react_agent(llm, tools=[], prompt=SYSTEM_PROMPT)


def run_research_lead(question: str, feedback: str | None = None, llm: Any | None = None) -> str:
    agent = build_research_lead(llm)
    content = question
    if feedback:
        content = f"Original question: {question}\n\nReplanning feedback:\n{feedback}"
    result = agent.invoke({"messages": [("user", content)]}, {"recursion_limit": 10})
    return result["messages"][-1].content
