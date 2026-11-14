"""C1 baseline for experiment E1: one ReAct agent that holds every tool the team uses.

Same model and the same six tools as the supervisor team (C2), but no research lead, no
supervisor and no specialist split: one agent plans, calls tools and writes the answer itself.
Comparing it with the team shows what the extra orchestration buys, and at what cost.
"""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from ..llm.llm import get_tool_llm
from ..tools.edgar_tools import get_company_fact, list_company_facts, list_edgar_companies
from ..tools.rag_tools import search_filing
from ..tools.risk_tools import compare_risk_factors
from ..tools.sandbox_tools import run_python

# The same six tools the team uses (run_python is the quant worker's calculator).
TOOLS = [
    search_filing, list_edgar_companies, list_company_facts, get_company_fact,
    compare_risk_factors, run_python,
]

SYSTEM_PROMPT = """You are a research assistant for companies' 10-K filings. Answer using only
your tools; never answer from memory.

Tools:
- search_filing: search 10-K text (risk factors, MD&A, business description) for a company and
  fiscal year. Use it for narrative questions and cite the Item and fiscal year.
- list_edgar_companies, list_company_facts, get_company_fact: reported numbers from SEC Company
  Facts. Always call list_edgar_companies first and use the CIK it returns. Cite the fiscal year,
  form, period and unit of every number and show any ratio you compute. A row's fiscal_year is
  the filing year; use its start and end dates to pair numerator and denominator.
- compare_risk_factors: what was added, removed or changed in a company's Item 1A between two
  fiscal years. Use it for every question about changes in risk factors and report the passage
  ids it returns.
- run_python: a calculator. Never do arithmetic yourself: for every ratio, margin, percentage,
  difference, growth rate, sum or average, call run_python with the exact values returned by
  get_company_fact, print each result, and report the printed value with the formula.

Fiscal years are named by the year their period ends (Microsoft's ends in June, Alphabet's in
December). If data for a company or year is not available, say so plainly; never guess.

Call tools only through the tool-calling interface. Never write a tool call such as
compare_risk_factors(...) as text in your reply: text is treated as your final answer and the tool
does not run. Your final answer must be prose based on the tool results."""


def build_single_agent(llm=None):
    llm = llm or get_tool_llm()
    return create_react_agent(llm, TOOLS, prompt=SYSTEM_PROMPT)


def run_single_agent(question: str, llm=None, recursion_limit: int = 40) -> str:
    agent = build_single_agent(llm)
    result = agent.invoke({"messages": [("user", question)]}, {"recursion_limit": recursion_limit})
    return result["messages"][-1].content
