"""Retrieval eval: is the evidence sentence in the top-k chunks for each question? (no LLM)

Run from the project root:
    python tests/evals/run_retrieval_eval.py [--k 5] [--cases FILE] [--mode semantic|keyword|hybrid|all]

--mode all runs every retrieval mode and ends with a side-by-side summary.

Reports Recall@k (evidence found in the top k) and MRR (1 / rank of the first chunk that holds
the evidence, 0 if none, averaged). A case whose evidence does not occur in any indexed chunk at
all is reported as BAD: that is a broken case (or a chunk boundary splitting the sentence), not
a retrieval miss, and it is left out of the scores.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agent_desk.rag.filing_rag import SEARCH_MODES, _load_store, search_chunks  # noqa: E402

CASES_FILE = PROJECT_ROOT / "tests" / "evals" / "dev" / "retrieval.jsonl"


def normalize(text: str) -> str:
    """Ignore case and differences in spaces or line breaks."""
    return " ".join(text.split()).lower()


def load_cases(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def rank_of_evidence(case: dict, k: int, mode: str = "semantic") -> int | None:
    """1-based rank of the first returned chunk containing the evidence, or None."""
    chunks = search_chunks(
        case["query"], k=k, company=case.get("company"), year=case.get("year"), mode=mode
    )
    evidence = normalize(case["evidence"])
    for rank, chunk in enumerate(chunks, start=1):
        if evidence in normalize(chunk.page_content):
            return rank
    return None


def evidence_in_index(case: dict, all_texts: list[str]) -> bool:
    evidence = normalize(case["evidence"])
    return any(evidence in text for text in all_texts)


def evaluate(cases: list[dict], all_texts: list[str], k: int, mode: str) -> tuple[int, int, float] | None:
    """Print per-case results for one mode; return (hits, scored, MRR) or None if no valid case."""
    print(f"=== mode: {mode} ===")
    scored, hits, rr_sum = 0, 0, 0.0
    by_company: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for case in cases:
        if not evidence_in_index(case, all_texts):
            print(f"BAD   {case['id']}  evidence not found in any chunk: {case['evidence'][:60]}")
            continue
        rank = rank_of_evidence(case, k, mode)
        scored += 1
        hits += rank is not None
        rr_sum += 1 / rank if rank else 0.0
        group = case.get("company") or "(no filter)"
        by_company[group][0] += rank is not None
        by_company[group][1] += 1
        label = f"HIT@{rank}" if rank else "MISS "
        print(f"{label:6} {case['id']}  {case['query']}")

    if not scored:
        print("No valid cases.")
        return None
    print(f"\nRecall@{k}: {hits}/{scored} = {hits / scored:.2f}")
    print(f"MRR@{k}:    {rr_sum / scored:.2f}")
    print("\nBy company:")
    for group, (h, n) in sorted(by_company.items()):
        print(f"  {group:16} {h}/{n}")
    print()
    return hits, scored, rr_sum / scored


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--cases", type=Path, default=CASES_FILE)
    parser.add_argument("--mode", choices=[*SEARCH_MODES, "all"], default="semantic")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    store = _load_store()
    all_texts = [normalize(d.page_content) for d in store.docstore._dict.values()]

    modes = list(SEARCH_MODES) if args.mode == "all" else [args.mode]
    results = {mode: evaluate(cases, all_texts, args.k, mode) for mode in modes}
    if any(r is None for r in results.values()):
        return 1
    if len(modes) > 1:
        print(f"=== summary (k={args.k}) ===")
        print(f"  {'mode':10} {'Recall':>12} {'MRR':>6}")
        for mode, (hits, scored, mrr) in results.items():
            print(f"  {mode:10} {f'{hits}/{scored} {hits / scored:.2f}':>12} {mrr:>6.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
