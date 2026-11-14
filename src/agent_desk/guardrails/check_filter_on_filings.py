"""How much real 10-K text would the tool-result filter cut? (false-positive check)

Run after the search index is built (python -m redteam.prepare_data):

  python -m agent_desk.guardrails.check_filter_on_filings   (from src/, or with PYTHONPATH=src)

Runs clean_text() over every chunk in data/faiss_index and prints how many chunks it changed,
with examples. Real filings contain no instructions to an AI, so every hit is a false positive
that hides real text from the agents.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agent_desk.rag.filing_rag import _load_store  # noqa: E402

from .tool_guards import _HIDDEN_HTML, _INSTRUCTION_RE, _SENTENCE_SPLIT, clean_text  # noqa: E402


def main() -> int:
    docs = list(_load_store().docstore._dict.values())
    hits, per_company = [], Counter()
    for doc in docs:
        _, removed = clean_text(doc.page_content)
        if removed:
            hits.append(doc)
            per_company[doc.metadata.get("company", "?")] += 1
    print(f"Chunks checked: {len(docs)}")
    print(f"Chunks changed by the filter: {len(hits)} ({100 * len(hits) / max(len(docs), 1):.2f}%)")
    print("By company:", dict(per_company))
    for doc in hits[:15]:
        for sentence in _SENTENCE_SPLIT.split(_HIDDEN_HTML.sub("", doc.page_content)):
            m = _INSTRUCTION_RE.search(sentence)
            if m:
                print(f"\n[{doc.metadata.get('company')} {doc.metadata.get('year')}] matched {m.group(0)!r}\n  {sentence[:220]}")
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
