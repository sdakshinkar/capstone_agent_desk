"""Agent-facing tool for searching the indexed 10-K filings."""

import json

from langchain_core.tools import tool

from ..rag.filing_rag import DEFAULT_SEARCH_MODE, SEARCH_MODES, SearchMode, search_chunks


@tool
def search_filing(
    query: str,
    company: str | None = None,
    year: int | None = None,
    k: int = 4,
    mode: SearchMode = DEFAULT_SEARCH_MODE,
) -> str:
    """Find relevant passages in indexed 10-K filings and return them with metadata.

    company: lowercase company name such as "apple" or "microsoft"; omit to search all.
    year: fiscal year of the filing such as 2025; omit to search all years.
    mode: "semantic" matches meaning (paraphrases, broad topics); "keyword" matches exact
        words, names and numbers (e.g. "First Republic", "166,000"); "hybrid" combines both
        and is a good choice when unsure.
    """
    if not query.strip():
        raise ValueError("The retrieval query must not be empty.")
    if not 1 <= k <= 10:
        raise ValueError("k must be between 1 and 10.")
    if year is not None and not 1990 <= year <= 2100:
        raise ValueError("year must be a four-digit fiscal year, for example 2025.")
    if mode not in SEARCH_MODES:
        raise ValueError(f"mode must be one of {', '.join(SEARCH_MODES)}.")

    return json.dumps(
        [
            {"text": match.page_content, "metadata": match.metadata}
            for match in search_chunks(query, k, company=company, year=year, mode=mode)
        ],
        ensure_ascii=False,
        indent=2,
    )
