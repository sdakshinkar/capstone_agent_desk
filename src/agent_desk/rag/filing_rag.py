"""Search the prebuilt FAISS index of 10-K filings (built by utils/create_embeddings.py).

Three retrieval modes share the same chunks and the same company/year filters:

- "semantic": dense vector similarity (FAISS + sentence-transformers embeddings).
- "keyword":  BM25 over the chunk text (LangChain's BM25Retriever). Good for exact terms,
              names and numbers such as "First Republic" or "166,000".
- "hybrid":   both of the above, merged with Reciprocal Rank Fusion (RRF).

The keyword index is built in memory from the chunks stored in the FAISS docstore, so it is
always in sync with the embeddings and needs no extra build step.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INDEX_DIR = PROJECT_ROOT / "data" / "faiss_index"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

SearchMode = Literal["semantic", "keyword", "hybrid"]
SEARCH_MODES: tuple[str, ...] = ("semantic", "keyword", "hybrid")
DEFAULT_SEARCH_MODE: SearchMode = "semantic"
# When set (for example by the eval harness), this mode is used for every search_chunks call.
FORCE_MODE_ENV = "AGENT_DESK_SEARCH_MODE"

# Hybrid search: how many candidates each retriever contributes before fusion, the RRF
# damping constant (60 is the value from the original RRF paper), and per-retriever weights.
HYBRID_CANDIDATES_PER_K = 4
HYBRID_MIN_CANDIDATES = 20
RRF_K = 60
HYBRID_WEIGHTS = {"semantic": 0.5, "keyword": 0.5}

_embeddings: HuggingFaceEmbeddings | None = None
_store_cache: tuple[int, FAISS] | None = None
# (index version, company, year) -> BM25 retriever over the matching chunks.
_bm25_cache: dict[tuple[int, str | None, str | None], BM25Retriever] = {}

# Numbers such as "166,000" or "72.22" stay single tokens; words split on any punctuation,
# so "Meta's" -> "meta", "s" and "ride-hailing" -> "ride", "hailing".
_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)+|\w+")


def _get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    return _embeddings


def _index_version() -> int:
    index_file = INDEX_DIR / "index.faiss"
    if not index_file.exists():
        raise FileNotFoundError(
            f"No embeddings found in {INDEX_DIR}. "
            "Run agent_desk/utils/create_embeddings.py first."
        )
    return index_file.stat().st_mtime_ns


def _load_store() -> FAISS:
    """Load the saved index, reloading only if create_embeddings rewrote it."""
    global _store_cache
    version = _index_version()
    if _store_cache is None or _store_cache[0] != version:
        store = FAISS.load_local(
            str(INDEX_DIR),
            _get_embeddings(),
            allow_dangerous_deserialization=True,
        )
        _store_cache = (version, store)
        _bm25_cache.clear()
    return _store_cache[1]


def _metadata_filter(company: str | None, year: int | str | None) -> dict[str, str]:
    metadata_filter: dict[str, str] = {}
    if company:
        metadata_filter["company"] = company.strip().lower()
    if year:
        metadata_filter["year"] = str(year)
    return metadata_filter


def tokenize(text: str) -> list[str]:
    """Lowercase word/number tokens used by the BM25 keyword index."""
    return _TOKEN_RE.findall(text.lower())


def semantic_search(
    query: str,
    k: int = 4,
    company: str | None = None,
    year: int | str | None = None,
) -> list[Document]:
    """Return the k chunks whose embeddings are closest to the query."""
    store = _load_store()
    metadata_filter = _metadata_filter(company, year)
    if not metadata_filter:
        return store.similarity_search(query, k=k)
    # Search every vector before filtering so the filter cannot starve the results.
    return store.similarity_search(
        query, k=k, filter=metadata_filter, fetch_k=store.index.ntotal
    )


def _get_bm25(company: str | None, year: int | str | None) -> BM25Retriever | None:
    """BM25 retriever over the chunks that pass the filter; None if no chunk does.

    The filter is applied before indexing (not after ranking) so it cannot starve the results,
    and each filter combination is built once per index version.
    """
    store = _load_store()
    version = _store_cache[0] if _store_cache else 0
    metadata_filter = _metadata_filter(company, year)
    key = (version, metadata_filter.get("company"), metadata_filter.get("year"))
    if key not in _bm25_cache:
        docs = [
            doc
            for doc in store.docstore._dict.values()
            if all(str(doc.metadata.get(f, "")).lower() == v for f, v in metadata_filter.items())
        ]
        if not docs:
            return None
        _bm25_cache[key] = BM25Retriever.from_documents(docs, preprocess_func=tokenize)
    return _bm25_cache[key]


def keyword_search(
    query: str,
    k: int = 4,
    company: str | None = None,
    year: int | str | None = None,
) -> list[Document]:
    """Return the k chunks with the highest BM25 keyword score for the query."""
    if not tokenize(query):
        return []
    retriever = _get_bm25(company, year)
    if retriever is None:
        return []
    retriever.k = k
    return retriever.invoke(query)


def _doc_key(doc: Document) -> tuple:
    """Identify a chunk across retrievers (the same chunk comes back as separate objects)."""
    meta = doc.metadata
    return (meta.get("source"), meta.get("start_index"), doc.page_content)


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[Document]],
    weights: dict[str, float] | None = None,
    rrf_k: int = RRF_K,
) -> list[Document]:
    """Merge several rankings: score(doc) = sum of weight / (rrf_k + rank) over the lists."""
    weights = weights or {}
    scores: dict[tuple, float] = {}
    docs: dict[tuple, Document] = {}
    for name, ranked in ranked_lists.items():
        weight = weights.get(name, 1.0)
        for rank, doc in enumerate(ranked, start=1):
            key = _doc_key(doc)
            docs.setdefault(key, doc)
            scores[key] = scores.get(key, 0.0) + weight / (rrf_k + rank)
    # sorted() is stable, so ties keep first-seen order (semantic list first).
    return [docs[key] for key in sorted(scores, key=scores.__getitem__, reverse=True)]


def hybrid_search(
    query: str,
    k: int = 4,
    company: str | None = None,
    year: int | str | None = None,
) -> list[Document]:
    """Fuse semantic and keyword rankings with Reciprocal Rank Fusion and return the top k."""
    candidates = max(k * HYBRID_CANDIDATES_PER_K, HYBRID_MIN_CANDIDATES)
    fused = reciprocal_rank_fusion(
        {
            "semantic": semantic_search(query, candidates, company=company, year=year),
            "keyword": keyword_search(query, candidates, company=company, year=year),
        },
        weights=HYBRID_WEIGHTS,
    )
    return fused[:k]


_SEARCHERS = {
    "semantic": semantic_search,
    "keyword": keyword_search,
    "hybrid": hybrid_search,
}


def search_chunks(
    query: str,
    k: int = 4,
    company: str | None = None,
    year: int | str | None = None,
    mode: SearchMode = DEFAULT_SEARCH_MODE,
) -> list[Document]:
    """Return the k best chunks, optionally limited to one company and/or year.

    mode: "semantic" (embeddings), "keyword" (BM25) or "hybrid" (both, fused with RRF).

    If the environment variable AGENT_DESK_SEARCH_MODE is set, it overrides `mode` for every
    call. The eval harness sets it (run_eval.py --search-mode) so that all agents and baselines
    search the same way in one run; normal app runs leave it unset.
    """
    forced = os.getenv(FORCE_MODE_ENV, "").strip().lower()
    if forced:
        mode = forced  # type: ignore[assignment]
    searcher = _SEARCHERS.get(mode)
    if searcher is None:
        raise ValueError(f"mode must be one of {', '.join(SEARCH_MODES)}; got {mode!r}.")
    return searcher(query, k, company=company, year=year)
