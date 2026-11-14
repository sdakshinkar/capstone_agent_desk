"""Download the 10-Ks the attacks need and build the search index, using the team's own code.

Run once from the project root (needs SEC_USER_AGENT in .env and internet):

  python -m redteam.prepare_data

The attacks ask about Apple, Microsoft and Alphabet for fiscal 2023-2025. The team's
filling_download.py is set up for Apple 2023-2024 only, so this script calls the same
functions with the full list instead of editing that file. Files that are already downloaded
are skipped. Building the index loads a small embedding model the first time (about 90 MB).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from agent_desk.utils.create_embeddings import create_all_embeddings  # noqa: E402
from agent_desk.utils.filling_download import download_filings  # noqa: E402

COMPANIES = [
    {"company_name": "apple", "cik": "0000320193"},
    {"company_name": "microsoft", "cik": "0000789019"},
    {"company_name": "alphabet", "cik": "0001652044"},
]
YEARS = [2023, 2024, 2025]


def main() -> int:
    for spec in COMPANIES:
        result = download_filings(spec["company_name"], spec["cik"], YEARS)
        for year, info in sorted(result.items()):
            print(f"{spec['company_name']:10s} {year}: {info['status']}")
    print("\nBuilding the search index (takes a few minutes the first time)...")
    print(create_all_embeddings())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
