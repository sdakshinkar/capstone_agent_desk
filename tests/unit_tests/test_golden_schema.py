"""Every golden case must match evals/golden_case.schema.json (no LLM, no network)."""

import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "evals" / "golden_case.schema.json").read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def _cases():
    for split in ("dev", "heldout"):
        path = ROOT / "tests" / "evals" / "cases" / split / "golden.jsonl"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip():
                yield f"{split}:{n}", json.loads(line)


def test_schema_is_valid():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("where, case", list(_cases()), ids=lambda v: v if isinstance(v, str) else "")
def test_golden_case_matches_schema(where, case):
    errors = [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in VALIDATOR.iter_errors(case)]
    assert not errors, f"{where} ({case.get('id')}): {errors}"


def test_schema_rejects_broken_cases():
    good = {"id": "n01", "group": "apple-num", "type": "numeric", "question": "Apple revenue FY2025?",
            "expected": {"facts": [{"company": "apple", "year": 2025, "metric": "revenue"}]},
            "expected_tools": ["get_company_fact"]}
    assert VALIDATOR.is_valid(good)
    assert not VALIDATOR.is_valid({**good, "id": "N-001"})                     # wrong id style
    assert not VALIDATOR.is_valid({**good, "expected": {"facts": [{"company": "tesla", "year": 2025, "metric": "revenue"}]}})
    assert not VALIDATOR.is_valid({**good, "type": "narrative"})               # narrative needs must_include
    assert not VALIDATOR.is_valid({**good, "type": "missing", "expected": {"refuse": False, "refuse_about": "x y z"}})
    risk = {**good, "id": "k01", "type": "risk_change",
            "expected": {"company": "apple", "year_from": 2024, "year_to": 2025, "labels": []}}
    assert not VALIDATOR.is_valid(risk)                                         # needs labels or no_material_change
    risk["expected"]["no_material_change"] = True
    assert VALIDATOR.is_valid(risk)
