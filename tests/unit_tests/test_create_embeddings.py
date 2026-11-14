from agent_desk.rag.filing_parser import Passage
from agent_desk.utils import create_embeddings


def _fake_passages(monkeypatch, passages):
    monkeypatch.setattr(create_embeddings, "load_passages", lambda path: passages)


def test_consecutive_passages_of_one_item_are_merged(tmp_path, monkeypatch):
    _fake_passages(
        monkeypatch,
        [
            Passage("Item 1", "Header line of the filing page."),
            Passage("Item 1", "As of 2025, we had approximately 36,000 employees in 38 countries."),
            Passage("Item 1A", "Export controls could restrict our sales."),
            Passage("Item 1", "A later passage under Item 1 again."),
        ],
    )

    merged = create_embeddings._merge_passages_by_item(tmp_path / "f.html")

    assert [item for item, _ in merged] == ["Item 1", "Item 1A", "Item 1"]
    assert merged[0][1] == (
        "Header line of the filing page.\n\n"
        "As of 2025, we had approximately 36,000 employees in 38 countries."
    )


def test_chunks_are_built_from_merged_passages(tmp_path, monkeypatch):
    filing = tmp_path / "nvidia" / "2025" / "nvda.html"
    # 60 short paragraphs of ~50 characters each, all in one Item.
    _fake_passages(monkeypatch, [Passage("Item 1", f"Paragraph number {i:02d} of the business section.") for i in range(60)])

    chunks = create_embeddings._chunk_filing(filing)

    # Merged into a few full-size chunks instead of one tiny chunk per paragraph.
    assert 2 <= len(chunks) <= 5
    assert all(len(c.page_content) <= create_embeddings.CHUNK_SIZE for c in chunks)
    assert max(len(c.page_content) for c in chunks) > create_embeddings.CHUNK_SIZE // 2
    assert {(c.metadata["company"], c.metadata["year"], c.metadata["item"]) for c in chunks} == {
        ("nvidia", "2025", "Item 1")
    }
