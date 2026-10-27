import json

import pytest
from langchain_core.documents import Document

from agent_desk import rag_tools


def test_search_filing_tool_returns_text_and_metadata(monkeypatch):
    document = Document(
        page_content="Supply chain risk factors.",
        metadata={"company": "apple", "year": "2025", "item": "Item 1A"},
    )

    def fake_search_chunks(query, k):
        assert query == "supply chain"
        assert k == 1
        return [document]

    monkeypatch.setattr(rag_tools, "search_chunks", fake_search_chunks)

    result = json.loads(rag_tools.search_filing.invoke({"query": "supply chain", "k": 1}))

    assert result == [
        {
            "text": "Supply chain risk factors.",
            "metadata": {"company": "apple", "year": "2025", "item": "Item 1A"},
        }
    ]


@pytest.mark.parametrize(
    ("query", "k", "message"),
    [(" ", 4, "must not be empty"), ("risk", 0, "between 1 and 10")],
)
def test_search_filing_rejects_invalid_input(query, k, message):
    with pytest.raises(ValueError, match=message):
        rag_tools.search_filing.func(query, k)
