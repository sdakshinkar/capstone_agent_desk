import json

import pytest
from langchain_core.documents import Document

from agent_desk.tools import rag_tools


def test_search_filing_tool_passes_filters_and_returns_metadata(monkeypatch):
    document = Document(
        page_content="Supply chain risk factors.",
        metadata={"company": "apple", "year": "2025", "item": "Item 1A"},
    )
    calls = []

    def fake_search_chunks(query, k, company=None, year=None, mode="semantic"):
        calls.append((query, k, company, year, mode))
        return [document]

    monkeypatch.setattr(rag_tools, "search_chunks", fake_search_chunks)

    result = json.loads(
        rag_tools.search_filing.invoke(
            {"query": "supply chain", "company": "apple", "year": 2025, "k": 1}
        )
    )

    assert calls == [("supply chain", 1, "apple", 2025, "semantic")]
    assert result == [
        {
            "text": "Supply chain risk factors.",
            "metadata": {"company": "apple", "year": "2025", "item": "Item 1A"},
        }
    ]


@pytest.mark.parametrize("mode", ["semantic", "keyword", "hybrid"])
def test_search_filing_tool_passes_mode(monkeypatch, mode):
    seen = []
    monkeypatch.setattr(
        rag_tools,
        "search_chunks",
        lambda query, k, company=None, year=None, mode="semantic": seen.append(mode) or [],
    )

    assert json.loads(rag_tools.search_filing.invoke({"query": "risk", "mode": mode})) == []
    assert seen == [mode]


@pytest.mark.parametrize(
    ("query", "year", "k", "mode", "message"),
    [
        (" ", None, 4, "semantic", "must not be empty"),
        ("risk", None, 0, "semantic", "between 1 and 10"),
        ("risk", 25, 4, "semantic", "four-digit fiscal year"),
        ("risk", None, 4, "fuzzy", "mode must be one of"),
    ],
)
def test_search_filing_rejects_invalid_input(query, year, k, mode, message):
    with pytest.raises(ValueError, match=message):
        rag_tools.search_filing.func(query, year=year, k=k, mode=mode)


def test_search_filing_records_passage_ids_only_with_a_register(monkeypatch):
    from agent_desk.evidence import Register, use_register

    document = Document(page_content="We employed 166,000 people.",
                        metadata={"company": "apple", "year": "2025", "item": "Item 1"})
    monkeypatch.setattr(rag_tools, "search_chunks",
                        lambda query, k, company=None, year=None, mode="semantic": [document])
    args = {"query": "employees", "company": "apple", "year": 2025, "k": 1, "mode": "hybrid"}

    assert "passage_id" not in json.loads(rag_tools.search_filing.invoke(args))[0]

    register = Register()
    use_register(register)
    entry = json.loads(rag_tools.search_filing.invoke(args))[0]
    assert entry["passage_id"] == "P1"
    assert register.get("P1") is not None  # the critic can look the passage up
