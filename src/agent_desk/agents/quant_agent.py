"""Quant specialist: EDGAR Company Facts tools only."""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from ..llm.llm import get_tool_llm
from ..tools.edgar_tools import get_company_fact, list_company_facts, list_edgar_companies

TOOLS = [list_edgar_companies, list_company_facts, get_company_fact]

SYSTEM_PROMPT = """You are the quantitative specialist for a filings research assistant.
Answer using only the SEC Company Facts tools.
Use list_edgar_companies to discover candidate companies, list_company_facts to inspect available facts,
and get_company_fact to retrieve the exact reported value for a company, metric and year.
Cite the fiscal year, form, period and unit for every reported number. Show any ratio you compute,
and do not guess when data is absent."""


def build_quant_agent(llm=None):
    llm = llm or get_tool_llm()
    return create_react_agent(llm, TOOLS, prompt=SYSTEM_PROMPT)


def run_quant_agent(question: str, llm=None) -> str:
    agent = build_quant_agent(llm)
    result = agent.invoke({"messages": [("user", question)]}, {"recursion_limit": 25})
    return result["messages"][-1].content
