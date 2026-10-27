from langchain_core.embeddings.fake import FakeEmbeddings

from agent_desk import filing_rag

SAMPLE_FILING = """
<html><body>
<div>Item 1A. Risk Factors</div>
<p>Supply chain disruptions could materially affect the company's operations,
product availability, and financial results.</p>
</body></html>
"""


def test_faiss_index_keeps_metadata_and_is_reused(tmp_path, monkeypatch):
    source = tmp_path / "apple" / "2025" / "filing.html"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_FILING, encoding="utf-8")
    index_dir = tmp_path / "index"
    monkeypatch.setattr(filing_rag, "INDEX_DIR", index_dir)
    monkeypatch.setattr(filing_rag, "MANIFEST_PATH", index_dir / "manifest.json")
    monkeypatch.setattr(filing_rag, "_embeddings", FakeEmbeddings(size=16))

    original_load = filing_rag.load_passages
    load_count = 0

    def counted_load(path):
        nonlocal load_count
        load_count += 1
        return original_load(path)

    monkeypatch.setattr(filing_rag, "load_passages", counted_load)

    first_store = filing_rag._load_or_build_store(source)
    results = first_store.similarity_search("supply chain risk", k=1)
    second_store = filing_rag._load_or_build_store(source)

    assert load_count == 1
    assert (index_dir / "index.faiss").exists()
    assert results[0].metadata["company"] == "apple"
    assert results[0].metadata["year"] == "2025"
    assert results[0].metadata["item"] == "Item 1A - Risk Factors"
    assert second_store.similarity_search("supply chain", k=1)

    monkeypatch.setattr(filing_rag, "_load_or_build_store", lambda: second_store)
    assert filing_rag.search_chunks("supply chain", k=1)[0].metadata["year"] == "2025"
