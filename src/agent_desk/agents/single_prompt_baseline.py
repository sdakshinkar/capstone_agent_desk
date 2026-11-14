"""C0 baseline for experiment E1: a fixed retrieve-then-answer pipeline with one LLM call.

No agent makes any decision. Code finds the company names in the question, retrieves passages
from the 10-K index for each, and the model answers in a single call from those passages only.
There are no SEC Company Facts lookups and no risk comparison tool, so numbers must come from
the financial statement text in the index. This is the "single retrieval prompt" baseline the
brief asks for: what you get without planning, routing or tools.
"""

from __future__ import annotations

import re

from ..llm.llm import get_tool_llm
from ..rag.filing_rag import search_chunks

PASSAGES_PER_COMPANY = 6
PASSAGES_WITHOUT_COMPANY = 8

# Lowercase aliases found in questions -> folder names used as index metadata.
COMPANY_ALIASES = {
    "microsoft": "microsoft", "msft": "microsoft",
    "apple": "apple", "aapl": "apple",
    "alphabet": "alphabet", "google": "alphabet", "googl": "alphabet",
    "amazon": "amazon", "amzn": "amazon",
    "meta": "meta", "facebook": "meta",
    "nvidia": "nvidia", "nvda": "nvidia",
    "jpmorgan": "jpmorgan", "jp morgan": "jpmorgan", "jpm": "jpmorgan",
    "bank of america": "bank_of_america", "bofa": "bank_of_america",
    "goldman": "goldman_sachs",
    "mastercard": "mastercard",
}

SYSTEM_PROMPT = """You answer questions about companies' 10-K filings using only the passages
provided. Each passage is labelled with its company, fiscal year and Item. Cite the company,
fiscal year and Item for every fact. Copy numbers exactly as written in the passages, with their
units. If the passages do not contain the answer, say that the information is not available in
the provided filings; never use outside knowledge or guess."""


def companies_in(question: str) -> list[str]:
    """Covered companies named in the question, in order of first mention (no duplicates)."""
    text = question.lower()
    hits: list[tuple[int, str]] = []
    for alias, company in COMPANY_ALIASES.items():
        match = re.search(rf"\b{re.escape(alias)}\b", text)
        if match:
            hits.append((match.start(), company))
    ordered: list[str] = []
    for _, company in sorted(hits):
        if company not in ordered:
            ordered.append(company)
    return ordered


def retrieve(question: str) -> list[dict]:
    companies = companies_in(question)
    docs = []
    if companies:
        for company in companies:
            docs.extend(search_chunks(question, k=PASSAGES_PER_COMPANY, company=company))
    else:
        docs = search_chunks(question, k=PASSAGES_WITHOUT_COMPANY)
    return [{"text": d.page_content, "metadata": d.metadata} for d in docs]


def format_passages(passages: list[dict]) -> str:
    blocks = []
    for n, p in enumerate(passages, start=1):
        m = p["metadata"]
        blocks.append(f"[{n}] {m.get('company')} | fiscal {m.get('year')} | {m.get('item')}\n{p['text']}")
    return "\n\n".join(blocks) or "(no passages found)"


def run_single_prompt(question: str, llm=None) -> tuple[str, list[dict]]:
    """Return the answer and the passages it was given (the harness records them)."""
    passages = retrieve(question)
    llm = llm or get_tool_llm()
    reply = llm.invoke(
        [
            ("system", SYSTEM_PROMPT),
            ("user", f"Passages:\n\n{format_passages(passages)}\n\nQuestion: {question}"),
        ]
    )
    return str(reply.content), passages
