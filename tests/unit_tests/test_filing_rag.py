import pytest
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings.fake import FakeEmbeddings

from agent_desk.rag import filing_rag

MODES = ["semantic", "keyword", "hybrid"]


class FakeReranker:
    """Scores a (query, text) pair by how many query words the text contains."""

    def __init__(self):
        self.calls = []

    def predict(self, pairs):
        self.calls.append(pairs)
        return [sum(w in text.lower() for w in query.lower().split()) for query, text in pairs]


@pytest.fixture(autouse=True)
def fake_reranker(monkeypatch):
    """Never download the real cross-encoder in unit tests."""
    reranker = FakeReranker()
    monkeypatch.setattr(filing_rag, "_reranker", reranker)
    return reranker


def _build_index(tmp_path, monkeypatch, docs):
    embeddings = FakeEmbeddings(size=16)
    FAISS.from_documents(docs, embeddings).save_local(str(tmp_path))
    monkeypatch.setattr(filing_rag, "INDEX_DIR", tmp_path)
    monkeypatch.setattr(filing_rag, "_embeddings", embeddings)
    monkeypatch.setattr(filing_rag, "_store_cache", None)
    monkeypatch.setattr(filing_rag, "_bm25_cache", {})
    return tmp_path


@pytest.fixture
def index_dir(tmp_path, monkeypatch):
    docs = [
        Document(page_content=f"{company} {year} risk {i}", metadata={"company": company, "year": year})
        for i in range(4)
        for company in ("apple", "microsoft")
        for year in ("2024", "2025")
    ]
    return _build_index(tmp_path, monkeypatch, docs)


@pytest.fixture
def text_index(tmp_path, monkeypatch):
    texts = [
        ("jpmorgan", "2025", "We recorded a $588 million First Republic-related gain in 2025."),
        ("jpmorgan", "2025", "Credit card net charge-offs increased during the year."),
        ("jpmorgan", "2024", "The First Republic acquisition was completed in May 2023."),
        ("apple", "2025", "The Company had approximately 166,000 full-time equivalent employees."),
        ("apple", "2025", "Supply chain disruptions could affect product availability."),
        ("meta", "2025", "Meta's headcount was 78,865 as of December 31, 2025."),
    ]
    docs = [
        Document(page_content=text, metadata={"company": c, "year": y, "start_index": i})
        for i, (c, y, text) in enumerate(texts)
    ]
    return _build_index(tmp_path, monkeypatch, docs)


@pytest.mark.parametrize("mode", MODES)
def test_search_filters_by_company_and_year(index_dir, mode):
    results = filing_rag.search_chunks("risk", k=3, company="Apple", year=2025, mode=mode)

    assert len(results) == 3
    assert {(d.metadata["company"], d.metadata["year"]) for d in results} == {("apple", "2025")}


@pytest.mark.parametrize("mode", MODES)
def test_search_without_filters_and_unknown_company(index_dir, mode):
    assert len(filing_rag.search_chunks("risk", k=5, mode=mode)) == 5
    assert filing_rag.search_chunks("risk", company="google", mode=mode) == []


def test_default_mode_is_semantic(index_dir, monkeypatch):
    calls = []
    monkeypatch.setitem(
        filing_rag._SEARCHERS, "semantic", lambda q, k, company=None, year=None: calls.append(q) or []
    )
    filing_rag.search_chunks("risk")
    assert calls == ["risk"]


def test_unknown_mode_is_rejected(index_dir):
    with pytest.raises(ValueError, match="mode must be one of"):
        filing_rag.search_chunks("risk", mode="fuzzy")


def test_tokenize_keeps_numbers_and_splits_punctuation():
    assert filing_rag.tokenize("Meta's 78,865 ride-hailing $72.22B") == [
        "meta", "78,865", "ride", "hail", "72.22", "b",
    ]


def test_tokenize_drops_stopwords():
    assert filing_rag.tokenize("How many employees does the Company have?") == [
        "many", "employ", "company",
    ]


@pytest.mark.parametrize(
    "words, stem",
    [
        (["employ", "employed", "employees", "employs"], "employ"),
        (["segment", "segments"], "segment"),
        (["company", "companies"], "company"),
        (["acquisition", "acquisitions"], "acquisition"),
    ],
)
def test_stem_maps_word_forms_to_one_token(words, stem):
    assert {filing_rag.stem(w) for w in words} == {stem}


def test_stem_leaves_numbers_and_short_words():
    assert [filing_rag.stem(w) for w in ("166,000", "2025", "uses", "gas")] == ["166,000", "2025", "uses", "gas"]


def test_keyword_search_matches_other_word_forms(text_index):
    # The query says "employ"; the chunk says "employees".
    top = filing_rag.keyword_search("How many people does Apple employ?", k=1)
    assert "166,000" in top[0].page_content


def test_keyword_search_ranks_exact_terms_first(text_index):
    top = filing_rag.keyword_search("First Republic gain", k=2, company="jpmorgan")

    assert top[0].page_content.startswith("We recorded a $588 million First Republic")
    assert all(d.metadata["company"] == "jpmorgan" for d in top)


def test_keyword_search_matches_numbers(text_index):
    top = filing_rag.keyword_search("166,000 employees", k=1)
    assert "166,000" in top[0].page_content


def test_keyword_search_respects_year_filter(text_index):
    top = filing_rag.keyword_search("First Republic", k=5, company="jpmorgan", year=2024)
    assert [d.metadata["year"] for d in top] == ["2024"]


def test_keyword_search_with_no_tokens_returns_nothing(text_index):
    assert filing_rag.keyword_search("?!", k=3) == []


def test_keyword_index_is_cached_per_filter(text_index):
    filing_rag.keyword_search("gain", company="jpmorgan")
    filing_rag.keyword_search("loss", company="jpmorgan")
    filing_rag.keyword_search("gain")
    assert len(filing_rag._bm25_cache) == 2


def test_hybrid_returns_unique_chunks_including_keyword_hit(text_index):
    results = filing_rag.hybrid_search("First Republic gain", k=3, company="jpmorgan")

    contents = [d.page_content for d in results]
    assert len(contents) == len(set(contents)) == 3
    assert any("$588 million" in c for c in contents)


def test_hybrid_reranks_fused_candidates(text_index, fake_reranker):
    results = filing_rag.hybrid_search("First Republic gain", k=1, company="jpmorgan")

    assert len(fake_reranker.calls) == 1
    assert all(query == "First Republic gain" for query, _ in fake_reranker.calls[0])
    # The fake reranker scores the chunk with all three query words highest.
    assert results[0].page_content.startswith("We recorded a $588 million First Republic")


def test_hybrid_without_rerank_skips_reranker(text_index, fake_reranker, monkeypatch):
    monkeypatch.setattr(filing_rag, "HYBRID_RERANK", False)

    assert len(filing_rag.hybrid_search("First Republic gain", k=2, company="jpmorgan")) == 2
    assert fake_reranker.calls == []


def test_rerank_orders_by_score_and_cuts_to_k():
    docs = [_d("gain"), _d("first republic gain"), _d("first gain")]
    reranked = filing_rag.rerank("first republic gain", docs, k=2)
    assert [d.page_content for d in reranked] == ["first republic gain", "first gain"]
    assert filing_rag.rerank("anything", [], k=3) == []


def _d(text):
    return Document(page_content=text)


def test_rrf_rewards_documents_ranked_by_both_retrievers():
    a, b, c, d = _d("a"), _d("b"), _d("c"), _d("d")
    fused = filing_rag.reciprocal_rank_fusion(
        {"semantic": [a, b, c], "keyword": [d, c, b]}, weights={"semantic": 0.5, "keyword": 0.5}
    )
    # b and c appear in both lists, so they beat a and d, which appear in only one.
    assert {x.page_content for x in fused[:2]} == {"b", "c"}
    assert {x.page_content for x in fused} == {"a", "b", "c", "d"}


def test_rrf_weights_shift_the_ranking():
    a, b = _d("a"), _d("b")
    lists = {"semantic": [a, b], "keyword": [b, a]}
    assert filing_rag.reciprocal_rank_fusion(lists, {"semantic": 0.8, "keyword": 0.2})[0].page_content == "a"
    assert filing_rag.reciprocal_rank_fusion(lists, {"semantic": 0.2, "keyword": 0.8})[0].page_content == "b"


def test_search_without_index_explains_how_to_build(tmp_path, monkeypatch):
    monkeypatch.setattr(filing_rag, "INDEX_DIR", tmp_path / "missing")
    monkeypatch.setattr(filing_rag, "_store_cache", None)

    for mode in MODES:
        with pytest.raises(FileNotFoundError, match="create_embeddings"):
            filing_rag.search_chunks("risk", mode=mode)


def test_env_var_forces_the_search_mode(monkeypatch):
    calls = []
    for name in ("semantic", "keyword", "hybrid"):
        monkeypatch.setitem(filing_rag._SEARCHERS, name, lambda q, k, company=None, year=None, _n=name: calls.append(_n) or [])
    monkeypatch.delenv(filing_rag.FORCE_MODE_ENV, raising=False)
    filing_rag.search_chunks("q", mode="keyword")
    monkeypatch.setenv(filing_rag.FORCE_MODE_ENV, "hybrid")
    filing_rag.search_chunks("q")                  # the default would be semantic
    filing_rag.search_chunks("q", mode="keyword")  # an explicit choice is overridden too
    assert calls == ["keyword", "hybrid", "hybrid"]
