"""Single standalone researcher: a LangGraph ReAct agent over the EDGAR tools."""

from langgraph.prebuilt import create_react_agent

from .edgar_tools import get_company_fact, list_company_facts, list_edgar_companies
from .rag_tools import search_filing
from .llm import get_tool_llm

TOOLS = [list_edgar_companies, list_company_facts, get_company_fact, search_filing]

SYSTEM_PROMPT = """You are a filings researcher. Answer using only data returned by your tools.
Use search_filing for narrative questions about 10-K sections, and use the EDGAR Company
Facts tools for reported financial data. Use both when a question needs both sources.
Call tools one at a time. Cite the Item for filing passages and the fiscal year and form
for every reported number. Show any ratio you compute, and do not guess when data is absent.
The filing search currently covers only the locally saved Apple 10-K; do not claim that
other companies' filing text was searched unless the tool returns it."""


def build_researcher(llm=None):
    llm = llm or get_tool_llm()
    return create_react_agent(llm, TOOLS, prompt=SYSTEM_PROMPT)


def run_researcher(question: str, llm=None) -> str:
    agent = build_researcher(llm)
    result = agent.invoke({"messages": [("user", question)]}, {"recursion_limit": 25})
    return result["messages"][-1].content
