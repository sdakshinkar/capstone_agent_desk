"""Single standalone researcher: a LangGraph ReAct agent over the EDGAR tools."""

from langgraph.prebuilt import create_react_agent

from .edgar_tools import get_company_fact, list_company_facts, list_edgar_companies
from .llm import get_tool_llm

TOOLS = [list_edgar_companies, list_company_facts, get_company_fact]

SYSTEM_PROMPT = """You are a filings researcher. Answer using only data returned by your tools.
Call tools one at a time. First list companies, then list facts, then fetch the exact fact.
Cite the fiscal year and form for every number you report, and show any ratio you compute.
Your tools only return reported XBRL numbers. They cannot read narrative text such as
risk factors. If asked about those, say so plainly instead of guessing."""


def build_researcher(llm=None):
    llm = llm or get_tool_llm()
    return create_react_agent(llm, TOOLS, prompt=SYSTEM_PROMPT)


def run_researcher(question: str, llm=None) -> str:
    agent = build_researcher(llm)
    result = agent.invoke({"messages": [("user", question)]}, {"recursion_limit": 25})
    return result["messages"][-1].content
