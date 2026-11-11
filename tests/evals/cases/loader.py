"""Load and validate the golden set (no LLM).

The golden set lives in two folders:
    tests/evals/cases/dev/*.jsonl      about 20 cases used while improving the system
    tests/evals/cases/heldout/*.jsonl  40+ cases run only for the final comparison

Neither folder is read by the agent: its tools only read data/. Expected numbers are not stored
in the cases at all; a case names (company, year, metric) and the checker looks the value up in
tests/evals/truth/xbrl_truth.json, so gold answers never sit next to a question.

Run from the project root to validate:  python -m evals.cases.loader   (with tests on the path)
"""

from __future__ import annotations

import json
from pathlib import Path

CASES_DIR = Path(__file__).resolve().parent
TRUTH_FILE = CASES_DIR.parent / "truth" / "xbrl_truth.json"
SPLITS = ("dev", "heldout")
TYPES = {"numeric", "comparison", "narrative", "risk_change", "missing"}


def load_truth(path: Path = TRUTH_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_split(split: str, cases_dir: Path = CASES_DIR) -> list[dict]:
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}")
    cases = []
    for path in sorted((cases_dir / split).glob("*.jsonl")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip():
                case = json.loads(line)
                case["split"] = split
                case["_source"] = f"{path.name}:{n}"
                cases.append(case)
    return cases


def truth_value(truth: dict, company: str, year: int, metric: str) -> dict | None:
    return truth.get(company, {}).get("years", {}).get(str(year), {}).get(metric)


def validate(cases_dir: Path = CASES_DIR, truth: dict | None = None) -> list[str]:
    """Return a list of problems; an empty list means the golden set is valid."""
    truth = truth if truth is not None else load_truth()
    problems: list[str] = []
    seen_ids: dict[str, str] = {}
    groups: dict[str, set[str]] = {s: set() for s in SPLITS}

    for split in SPLITS:
        for case in load_split(split, cases_dir):
            where = f"{split}/{case['_source']}"
            cid = case.get("id")
            if not cid:
                problems.append(f"{where}: missing id")
                continue
            if cid in seen_ids:
                problems.append(f"{where}: duplicate id {cid} (also {seen_ids[cid]})")
            seen_ids[cid] = where
            if case.get("type") not in TYPES:
                problems.append(f"{where}: unknown type {case.get('type')}")
            if not case.get("question"):
                problems.append(f"{where}: missing question")
            if not case.get("group"):
                problems.append(f"{where}: missing group")
            groups[split].add(case.get("group", ""))

            expected = case.get("expected", {})
            for fact in expected.get("facts", []):
                if truth_value(truth, fact["company"], fact["year"], fact["metric"]) is None:
                    problems.append(f"{where}: no truth for {fact}")
            for d in expected.get("derived", []):
                for year in (d["from"], d["to"]):
                    if truth_value(truth, d["company"], year, d["metric"]) is None:
                        problems.append(f"{where}: no truth for derived {d} year {year}")
            if case.get("type") == "narrative" and not expected.get("must_include"):
                problems.append(f"{where}: narrative case needs must_include")
            if case.get("type") == "risk_change":
                if not expected.get("labels") and not expected.get("no_material_change"):
                    problems.append(f"{where}: risk case needs labels or no_material_change")
            if case.get("type") == "missing" and not expected.get("refuse"):
                problems.append(f"{where}: missing case needs refuse: true")

    leaked = (groups["dev"] & groups["heldout"]) - {""}
    for group in sorted(leaked):
        problems.append(f"group '{group}' appears in both dev and heldout")
    return problems


def main() -> int:
    problems = validate()
    for split in SPLITS:
        cases = load_split(split)
        by_type: dict[str, int] = {}
        for c in cases:
            by_type[c["type"]] = by_type.get(c["type"], 0) + 1
        print(f"{split:8} {len(cases):3} cases  {dict(sorted(by_type.items()))}")
    for p in problems:
        print("PROBLEM", p)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
