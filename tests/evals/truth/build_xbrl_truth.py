"""Build the numeric ground truth for the evals from cached SEC Company Facts (no LLM).

Run from the project root:  python tests/evals/truth/build_xbrl_truth.py

Writes tests/evals/truth/xbrl_truth.json:
    {"microsoft": {"fiscal_year_end": "06-30", "years": {"2025": {"revenue": {...}, ...}}}}

Fiscal year means the year of the period end date, the same convention as data/filings/
(NVIDIA's 2025 ends in January 2025, Microsoft's in June 2025, Alphabet's in December 2025).
Each metric records the XBRL concept used, the period, the accession number of the filing it
came from, and `accepted`: every distinct value any 10-K reported for that period. A later 10-K
sometimes restates a number (Bank of America restated 2023 and 2024), and the agent may quote
either the original or the restated value, so both are accepted.

Ratios (operating margin, net margin) are computed here, by code, from the two reported values.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agent_desk.tools.edgar_tools import _fetch_company_facts  # noqa: E402

OUT_FILE = Path(__file__).with_name("xbrl_truth.json")
YEARS = (2023, 2024, 2025, 2026)

# Folder name (as in data/filings) -> CIK.
COMPANIES = {
    "microsoft": "0000789019",
    "apple": "0000320193",
    "alphabet": "0001652044",
    "amazon": "0001018724",
    "meta": "0001326801",
    "nvidia": "0001045810",
    "jpmorgan": "0000019617",
    "bank_of_america": "0000070858",
    "goldman_sachs": "0000886982",
    "mastercard": "0001141391",
}

# Metric -> concepts to try in order; the first one with a value for the year is used.
METRICS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenuesNetOfInterestExpense",
    ],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "rd_expense": ["ResearchAndDevelopmentExpense"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "total_assets": ["Assets"],
}
# Point-in-time (balance sheet) metrics have no start date.
INSTANT = {"total_assets"}


def _rows(facts: dict, concept: str, year: int, instant: bool) -> list[dict]:
    """Annual 10-K rows of one concept whose period ends in `year`."""
    fact = facts.get(concept)
    if not fact:
        return []
    unit = "USD" if "USD" in fact["units"] else next(iter(fact["units"]))
    rows = []
    for e in fact["units"][unit]:
        if e.get("form") != "10-K" or not str(e.get("end", "")).startswith(str(year)):
            continue
        if instant:
            if "start" in e:
                continue
        else:
            if "start" not in e:
                continue
            days = (date.fromisoformat(e["end"]) - date.fromisoformat(e["start"])).days
            if not 350 <= days <= 380:
                continue
        rows.append({**e, "unit": unit})
    return rows


def _metric(facts: dict, name: str, year: int) -> dict | None:
    for concept in METRICS[name]:
        rows = _rows(facts, concept, year, name in INSTANT)
        if not rows:
            continue
        # Keep only the latest period end in that year (a 52/53-week year can have two rows).
        latest_end = max(r["end"] for r in rows)
        rows = [r for r in rows if r["end"] == latest_end]
        # The original report is the earliest filing; restatements come later.
        rows.sort(key=lambda r: r["filed"])
        original = rows[0]
        accepted = sorted({r["val"] for r in rows})
        return {
            "value": original["val"],
            "accepted": accepted,
            "unit": original["unit"],
            "concept": concept,
            "start": original.get("start"),
            "end": original["end"],
            "accession": original["accn"],
            "filed": original["filed"],
        }
    return None


def _ratio(numerator: dict | None, denominator: dict | None, name: str) -> dict | None:
    if not numerator or not denominator or not denominator["value"]:
        return None
    candidates = sorted(
        {round(n / d * 100, 4) for n in numerator["accepted"] for d in denominator["accepted"] if d}
    )
    return {
        "value": round(numerator["value"] / denominator["value"] * 100, 4),
        "accepted": candidates,
        "unit": "percent",
        "formula": name,
        "end": denominator["end"],
    }


def build() -> dict:
    truth: dict = {}
    for company, cik in COMPANIES.items():
        data, error = _fetch_company_facts(cik)
        if error:
            raise RuntimeError(f"{company}: {error}")
        facts = data["facts"]["us-gaap"]
        years: dict = {}
        fy_end = None
        for year in YEARS:
            row = {name: _metric(facts, name, year) for name in METRICS}
            row["operating_margin"] = _ratio(
                row["operating_income"], row["revenue"], "operating_income / revenue"
            )
            row["net_margin"] = _ratio(row["net_income"], row["revenue"], "net_income / revenue")
            row = {k: v for k, v in row.items() if v is not None}
            if row:
                years[str(year)] = row
                fy_end = fy_end or (row.get("revenue") or row.get("net_income") or {}).get("end")
        truth[company] = {
            "cik": cik,
            "entity": data.get("entityName"),
            "fiscal_year_end": fy_end[5:] if fy_end else None,
            "years": years,
        }
    return truth


def main() -> int:
    truth = build()
    OUT_FILE.write_text(json.dumps(truth, indent=2), encoding="utf-8")
    for company, info in truth.items():
        print(f"{company:16} FY ends {info['fiscal_year_end']}  years {sorted(info['years'])}")
    print(f"Wrote {OUT_FILE.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
