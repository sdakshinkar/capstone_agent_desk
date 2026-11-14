"""Tests for the eval checkers, using recorded agent outputs (no LLM, no network)."""

import pytest

from evals.cases.loader import load_truth, validate
from evals.checkers import grade as g
from evals.checkers.numbers import extract_numbers, find_value, matches

TRUTH = load_truth()

# Real quant_worker outputs, copied from the comments in agents/workflow.py.
MSFT_MARGINS = (
    "Microsoft's operating margin for fiscal years 2023, 2024, and 2025 are as follows:\n"
    "- 2023: (88.523 billion / 211.915 billion) = 41.8%\n"
    "- 2024: (109.433 billion / 245.122 billion) = 44.7%\n"
    "- 2025: (128.528 billion / 281.724 billion) = 45.6%"
)
GOOGL_MARGINS = (
    "* 2023: Operating income of $84,293,000,000 and revenue of $307,394,000,000, resulting in an "
    "operating margin of 27.4%\n* 2024: Operating income of $112,390,000,000 and revenue of "
    "$350,018,000,000, resulting in an operating margin of 32.1%\n* 2025: Operating income of "
    "$129,039,000,000 and revenue of $402,836,000,000, resulting in an operating margin of 32.0%"
)


def _case(ctype, expected, tools=()):
    return {"id": "x", "type": ctype, "expected": expected, "expected_tools": list(tools)}


def _record(answer, tools=(), contexts=()):
    calls = [{"name": n, "args": {}, "output": o} for n, o in tools]
    return {"answer": answer, "trajectory": {"tool_calls": calls, "contexts": list(contexts)}}


# ------------------------------------------------------------------ golden set


def test_golden_set_is_valid():
    assert validate() == []


# ------------------------------------------------------------------ number parsing


@pytest.mark.parametrize(
    "text, value",
    [
        ("$245.1 billion", 245.1e9),
        ("245,122 million", 245_122e6),
        ("$88,523,000,000", 88_523_000_000),
        ("245.12B", 245.12e9),
        ("$3.41 trillion", 3.41e12),
        ("44.7%", 44.7),
        ("12 percent", 12.0),
        ("$23.49", 23.49),
    ],
)
def test_extract_numbers(text, value):
    numbers = extract_numbers(text)
    assert numbers and numbers[0].value == pytest.approx(value)


def test_precision_rules():
    four_point_two = extract_numbers("$4.2 billion")[0]
    assert matches(four_point_two, 4_224_000_000, percent=False)  # rounded to one decimal
    assert not matches(extract_numbers("$4.5 billion")[0], 4_224_000_000, percent=False)
    assert matches(extract_numbers("44.7%")[0], 44.6443, percent=True)
    assert not matches(extract_numbers("45.7%")[0], 44.6443, percent=True)
    # A dollar amount never matches a percentage and vice versa.
    assert not matches(extract_numbers("44.6")[0], 44.6443, percent=True)


def test_truncated_percent_is_accepted():
    # Apple FY2025 operating margin is 31.97%; the agent wrote 31.9% (cut off, not rounded).
    assert matches(extract_numbers("31.9%")[0], 31.9708, percent=True)
    assert matches(extract_numbers("31.97%")[0], 31.9708, percent=True)
    assert not matches(extract_numbers("31.8%")[0], 31.9708, percent=True)
    assert not matches(extract_numbers("31%")[0], 31.9708, percent=True)  # whole numbers must round
    assert matches(extract_numbers("-2.3%")[0], -2.38, percent=True)


def test_unscaled_table_number_does_not_match():
    # "245,122" without "million" is ambiguous, so it must not count as $245.1 billion.
    assert find_value(extract_numbers("Revenue was 245,122."), [245_122e6], percent=False) is None


# ------------------------------------------------------------------ numeric cases


def test_recorded_microsoft_margins_pass():
    facts = [{"company": "microsoft", "year": y, "metric": "operating_margin"} for y in (2023, 2024, 2025)]
    result = g.check_facts(MSFT_MARGINS, facts, TRUTH)
    assert result["pass"], result


def test_recorded_alphabet_margins_and_amounts_pass():
    facts = [{"company": "alphabet", "year": y, "metric": m}
             for y in (2023, 2024, 2025) for m in ("operating_margin", "operating_income", "revenue")]
    assert g.check_facts(GOOGL_MARGINS, facts, TRUTH)["pass"]


def test_wrong_number_fails():
    facts = [{"company": "apple", "year": 2025, "metric": "revenue"}]
    assert g.check_facts("Apple's FY2025 revenue was $391.0 billion.", facts, TRUTH)["pass"] is False
    assert g.check_facts("Apple's FY2025 revenue was $416.2 billion.", facts, TRUTH)["pass"] is True


def test_restated_value_is_accepted():
    facts = [{"company": "bank_of_america", "year": 2024, "metric": "net_income"}]
    for answer in ("$27.13 billion", "$26.97 billion"):  # original and restated
        assert g.check_facts(answer, facts, TRUTH)["pass"]


def test_growth_and_years():
    derived = [{"kind": "growth", "company": "nvidia", "metric": "revenue", "from": 2024, "to": 2025}]
    assert g.check_derived("Revenue grew 114.2% from FY2024 to FY2025.", derived, TRUTH)["pass"]
    assert not g.check_derived("Revenue grew 50%.", derived, TRUTH)["pass"]
    facts = [{"company": "nvidia", "year": 2024, "metric": "revenue"}, {"company": "nvidia", "year": 2025, "metric": "revenue"}]
    assert g.check_years("In FY24 and fiscal 2025 ...", facts)["pass"]
    assert g.check_years("In fiscal 2025 ...", facts)["missing_years"] == [2024]


# ------------------------------------------------------------------ other case types


def test_must_include_and_evidence():
    groups = [["39,800"], ["70%", "70 percent"]]
    assert g.check_must_include("About 39,800 people, 70 percent outside the U.S.", groups)["pass"]
    assert g.check_must_include("About 39,800 people.", groups)["missing"] == [["70%", "70 percent"]]
    evidence = {"text": "we employed approximately 39,800 persons globally"}
    hit = _record("x", tools=[("search_filing", "... As of 2025, we employed approximately\n39,800 persons globally ...")])
    assert g.check_evidence_retrieved(hit, evidence)["pass"] is True
    assert g.check_evidence_retrieved(_record("x"), evidence)["pass"] is None


def test_risk_labels_coverage():
    expected = {"labels": [
        {"kind": "added", "label": "power", "keywords": ["power", "electric"]},
        {"kind": "added", "label": "zoning", "keywords": ["zoning", "permit"]},
        {"kind": "added", "label": "labor", "keywords": ["labor"]},
    ]}
    two_of_three = "New risks: electricity supply for datacenters and permitting delays."
    assert g.check_risk_labels(two_of_three, expected)["coverage"] == 0.67
    assert g.check_risk_labels(two_of_three, expected)["pass"]
    assert not g.check_risk_labels("Comparison not possible: power, zoning", expected)["pass"]


def test_no_material_change():
    expected = {"labels": [], "no_material_change": True}
    assert g.check_risk_labels("Amazon's risk factors remained largely unchanged.", expected)["pass"]
    assert not g.check_risk_labels("Amazon added three new AI risks.", expected)["pass"]


def test_refusal():
    assert g.check_refusal("Tesla is not one of the covered companies.")["pass"]
    assert g.check_refusal("Alphabet's fiscal 2026 10-K has not been filed yet.")["pass"]
    assert g.check_refusal("Comparison not possible: no filing for 2026.")["pass"]
    assert not g.check_refusal("Tesla's operating income was $7.1 billion.")["pass"]


def test_passage_ids(monkeypatch):
    monkeypatch.setattr(g, "_passage_ids", lambda c, y: frozenset({"microsoft-2025-1A-37"}))
    assert g.check_passage_ids("See microsoft-2025-1A-37.")["pass"]
    assert g.check_passage_ids("See microsoft-2025-1A-999.")["invalid"] == ["microsoft-2025-1A-999"]


# ------------------------------------------------------------------ whole case


def test_grade_numeric_case():
    case = _case("numeric", {"facts": [{"company": "apple", "year": 2025, "metric": "revenue"}]}, ["get_company_fact"])
    good = _record("Apple's fiscal 2025 revenue was $416.16 billion (10-K).", tools=[("get_company_fact", "{}")])
    result = g.grade(case, good, TRUTH)
    assert result["code_pass"] and result["checks"]["tools"]["pass"]
    # Missing the tool call is reported but does not fail the task itself.
    no_tool = g.grade(case, _record("Apple's fiscal 2025 revenue was $416.16 billion."), TRUTH)
    assert no_tool["code_pass"] and no_tool["checks"]["tools"]["pass"] is False


def test_grade_crash_fails():
    case = _case("numeric", {"facts": [{"company": "apple", "year": 2025, "metric": "revenue"}]})
    record = {"answer": "", "error": "TimeoutError", "trajectory": {}}
    assert g.grade(case, record, TRUTH)["code_pass"] is False


def test_grade_partial_missing_case():
    case = _case("missing", {"refuse": True, "facts": [{"company": "meta", "year": 2024, "metric": "revenue"}]})
    answer = "Netflix is not covered. Meta's fiscal 2024 revenue was $164.5 billion."
    assert g.grade(case, _record(answer), TRUTH)["code_pass"]
    assert not g.grade(case, _record("Netflix is not covered."), TRUTH)["code_pass"]


def test_numbers_verified_counts_real_and_unreal_figures():
    expected = {"facts": [{"company": "apple", "year": 2025, "metric": "revenue"}]}
    answer = ("Apple's fiscal 2025 revenue was $416.16 billion, up 6.4% from fiscal 2024. "
              "It employs 166,000 people and spent $999.9 billion on snacks.")
    result = g.check_numbers_verified(answer, expected, TRUTH)
    assert result["pass"] is None  # diagnostic, never fails a case
    # $416.16 billion and the 6.4% growth are real; the snack figure is not; 166,000 has no unit.
    assert (result["verified"], result["total"]) == (2, 3)
    assert result["unverified"] == ["$999.9 billion"]


def test_recorded_margins_are_fully_verified():
    facts = [{"company": "microsoft", "year": y, "metric": "operating_margin"} for y in (2023, 2024, 2025)]
    result = g.check_numbers_verified(MSFT_MARGINS, {"facts": facts}, TRUTH)
    assert result["verified"] == result["total"] > 0


def test_calc_in_sandbox():
    margin = {"facts": [{"company": "apple", "year": 2025, "metric": "operating_margin"}]}
    revenue = {"facts": [{"company": "apple", "year": 2025, "metric": "revenue"}]}
    used = _record("31.97%", tools=[("get_company_fact", "{}"), ("run_python", "31.97")])
    skipped = _record("31.97%", tools=[("get_company_fact", "{}")])
    assert g.check_calc_in_sandbox(used, margin, has_sandbox=True)["used"] is True
    assert g.check_calc_in_sandbox(skipped, margin, has_sandbox=True)["used"] is False
    assert g.check_calc_in_sandbox(skipped, revenue, has_sandbox=True)["applies"] is False  # no calculation needed
    assert g.check_calc_in_sandbox(skipped, margin, has_sandbox=False)["applies"] is False  # C0 / C1


def test_markdown_bullet_is_not_a_minus_sign():
    assert extract_numbers("- 11.16%")[0].value == pytest.approx(11.16)
    assert extract_numbers("-11.16%")[0].value == pytest.approx(-11.16)
    assert extract_numbers("−$4.2 billion")[0].value == pytest.approx(-4.2e9)


def test_answers_with_evidence_ids_are_graded_normally():
    # C2's writer now puts evidence ids after every figure and claim.
    answer = ("Apple's fiscal 2025 revenue was $416.16 billion [F1] and its operating margin "
              "31.97% [D1]. New risks cover age verification [apple-2025-1A-12] [P3].")
    facts = [{"company": "apple", "year": 2025, "metric": "revenue"},
             {"company": "apple", "year": 2025, "metric": "operating_margin"}]
    assert g.check_facts(answer, facts, TRUTH)["pass"]
    verified = g.check_numbers_verified(answer, {"facts": facts}, TRUTH)
    assert (verified["verified"], verified["total"]) == (2, 2)  # ids and the passage year are not figures
