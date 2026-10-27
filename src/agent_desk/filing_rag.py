"""Local FAISS retrieval over a saved 10-K filing."""

import json
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .filing_parser import DEFAULT_FILING, load_passages

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILING = PROJECT_ROOT / DEFAULT_FILING
INDEX_DIR = PROJECT_ROOT / "data" / "faiss_index" / "apple_2025"
MANIFEST_PATH = INDEX_DIR / "manifest.json"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

_embeddings: HuggingFaceEmbeddings | None = None


def _get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    return _embeddings


def _current_manifest(source: Path) -> dict[str, str | int]:
    stat = source.stat()
    return {
        "source": str(source.resolve()),
        "source_size": stat.st_size,
        "source_mtime_ns": stat.st_mtime_ns,
        "embedding_model": EMBEDDING_MODEL,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }


def _load_or_build_store(source: Path = SOURCE_FILING) -> FAISS:
    manifest = _current_manifest(source)
    index_file = INDEX_DIR / "index.faiss"
    docstore_file = INDEX_DIR / "index.pkl"

    if index_file.exists() and docstore_file.exists() and MANIFEST_PATH.exists():
        saved_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if saved_manifest == manifest:
            return FAISS.load_local(
                str(INDEX_DIR),
                _get_embeddings(),
                allow_dangerous_deserialization=True,
            )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        add_start_index=True,
    )
    passages = load_passages(source)
    documents = [
        Document(
            page_content=passage.text,
            metadata={
                "company": source.parent.parent.name,
                "year": source.parent.name,
                "item": passage.item,
                "source": str(source.resolve()),
            },
        )
        for passage in passages
    ]
    chunks = splitter.split_documents(documents)
    if not chunks:
        raise ValueError(f"No text passages found in filing: {source}")

    store = FAISS.from_documents(chunks, _get_embeddings())
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    store.save_local(str(INDEX_DIR))
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return store


def search_chunks(query: str, k: int = 4) -> list[Document]:
    """Return the k chunks of the saved filing most similar to the query."""
    return _load_or_build_store().similarity_search(query, k=k)
