"""Agent-facing tool for searching the saved 10-K."""

import json

from langchain_core.tools import tool

from .filing_rag import search_chunks


@tool
def search_filing(query: str, k: int = 4) -> str:
    """Find relevant passages in the locally saved 10-K and return their metadata."""
    if not query.strip():
        raise ValueError("The retrieval query must not be empty.")
    if not 1 <= k <= 10:
        raise ValueError("k must be between 1 and 10.")

    return json.dumps(
        [
            {"text": match.page_content, "metadata": match.metadata}
            for match in search_chunks(query, k)
        ],
        ensure_ascii=False,
        indent=2,
    )
