import argparse
import sys
from pathlib import Path

from agent_desk.filing_search import DEFAULT_FILING, load_passages, search

EXCERPT_CHARS = 600


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="agent_desk",
        description="Ask the filings researcher, or keyword-search a saved 10-K.",
    )
    parser.add_argument("query", nargs="+", help="keywords or a question")
    parser.add_argument(
        "--search",
        action="store_true",
        help="keyword search the saved 10-K instead of using the agent",
    )
    parser.add_argument("--filing", type=Path, default=DEFAULT_FILING)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not args.search:
        from agent_desk.researcher_agent import run_researcher

        try:
            print(run_researcher(" ".join(args.query)))
        except Exception as exc:
            print(f"Agent failed: {exc}", file=sys.stderr)
            return 1
        return 0

    if not args.filing.exists():
        print(f"Filing not found: {args.filing}", file=sys.stderr)
        return 1

    passages = load_passages(args.filing)
    matches = search(passages, " ".join(args.query), args.limit)
    if not matches:
        print("No matching passages found.")
        return 0

    for rank, match in enumerate(matches, start=1):
        text = match.passage.text
        if len(text) > EXCERPT_CHARS:
            text = text[:EXCERPT_CHARS].rstrip() + "..."
        print(f"[{rank}] {match.passage.item} (score {match.score})")
        print(f"    {text}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
