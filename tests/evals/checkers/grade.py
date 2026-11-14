"""Code checks for one eval run (no LLM). The judge only handles what these cannot decide.

grade(case, record, truth) takes a golden case, the run record the harness saved for it, and
the XBRL truth, and returns {"checks": {...}, "code_pass": bool}.

A run record looks like:
    {"case_id": "n01", "answer": "...", "error": None, "timed_out": False,
     "trajectory": {"workers": ["quant_worker"], "replans": 0,
                    "tool_calls": [{"name": "get_company_fact", "args": {...}, "output": "..."}]}}

Checks by case type:
    numeric / comparison  every expected number (and derived growth) appears in the answer at
                          the precision written; every expected fiscal year is named
    narrative             the answer contains each must_include group; whether the evidence
                          sentence was among the passages the tools returned (a retrieval signal)
    risk_change           share of hand labels whose keywords appear in the answer; a
                          "no material change" case must say so; cited passage ids must exist
    missing               the answer says the data is unavailable; any partial facts are right
    all                   no crash or timeout; expected tools were called (when the config
                          has tools); cited passage ids are real
"""

from __future__ import annotations

import re
from functools import lru_cache

from .numbers import extract_numbers, find_value

REFUSAL_PATTERNS = [
    r"not (?:yet )?(?:available|covered|included|reported|found|stored|filed|disclosed|provided)",
    r"no (?:data|filing|information|record|results?|passages?|10-k)",
    r"(?:unable|cannot|can't|could not|couldn't) (?:to )?(?:find|provide|answer|locate|retrieve|compare)",
    r"does not (?:report|have|include|cover|exist)",
    r"(?:isn't|is not|aren't|are not|wasn't) (?:available|covered|one of)",
    r"has not (?:yet )?been (?:filed|released|published|reported)",
    r"comparison not possible",
    r"outside (?:the|our) (?:coverage|scope)",
    r"only (?:has|have|covers?) (?:data|filings)",
]
NO_CHANGE_PATTERNS = [
    r"no (?:material|significant|substantive|major|notable) (?:differences|changes)",
    r"(?:largely|substantially|essentially|mostly) (?:unchanged|the same|similar|consistent)",
    r"(?:few|minimal|minor|limited) (?:material )?(?:changes|differences)",
    r"remained (?:largely |substantially )?(?:unchanged|consistent|the same)",
]
PASSAGE_ID = re.compile(r"\b([a-z_]+)-(\d{4})-1A-(\d+)\b")
ITEM_CITE = re.compile(r"\bItem\s+\d{1,2}[A-C]?\b", re.IGNORECASE)


def _norm(text: str) -> str:
    return " " + " ".join(text.lower().replace("’", "'").split()) + " "


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def _truth(truth: dict, company: str, year: int, metric: str) -> dict:
    return truth[company]["years"][str(year)][metric]


@lru_cache(maxsize=64)
def _passage_ids(company: str, year: int) -> frozenset[str]:
    from agent_desk.rag.risk_section import load_risk_section

    try:
        return frozenset(p.id for p in load_risk_section(company, year))
    except (FileNotFoundError, ValueError):
        return frozenset()


# ---------------------------------------------------------------- individual checks


def check_facts(answer: str, facts: list[dict], truth: dict) -> dict:
    numbers = extract_numbers(answer)
    results = []
    for fact in facts:
        t = _truth(truth, fact["company"], fact["year"], fact["metric"])
        hit = find_value(numbers, t["accepted"], percent=t["unit"] == "percent")
        results.append({**fact, "expected": t["value"], "found": hit.raw if hit else None})
    found = sum(r["found"] is not None for r in results)
    return {"pass": found == len(results), "found": found, "total": len(results), "facts": results}


def check_derived(answer: str, derived: list[dict], truth: dict) -> dict:
    numbers = extract_numbers(answer)
    results = []
    for d in derived:
        a = _truth(truth, d["company"], d["from"], d["metric"])["accepted"]
        b = _truth(truth, d["company"], d["to"], d["metric"])["accepted"]
        growth = sorted({(y - x) / x * 100 for x in a for y in b if x})
        hit = find_value(numbers, growth, percent=True)
        results.append({**d, "expected": round(growth[0], 2), "found": hit.raw if hit else None})
    found = sum(r["found"] is not None for r in results)
    return {"pass": found == len(results), "found": found, "total": len(results), "derived": results}


def check_years(answer: str, facts: list[dict]) -> dict:
    text = _norm(answer)
    years = sorted({f["year"] for f in facts})
    missing = [
        y for y in years
        if str(y) not in text and f"fy{y % 100}" not in text and f"fy {y % 100}" not in text
    ]
    return {"pass": not missing, "missing_years": missing}


def check_must_include(answer: str, groups: list[list[str]]) -> dict:
    text = _norm(answer)
    missing = [g for g in groups if not any(_norm(option).strip() in text for option in g)]
    return {"pass": not missing, "missing": missing}


def check_evidence_retrieved(record: dict, evidence: dict | None) -> dict:
    """Did any tool output contain the evidence sentence? (None when the config has no tools.)"""
    if not evidence:
        return {"pass": None}
    calls = record.get("trajectory", {}).get("tool_calls", [])
    contexts = [c.get("output", "") for c in calls] + record.get("trajectory", {}).get("contexts", [])
    if not contexts:
        return {"pass": None, "note": "no tool outputs recorded"}
    needle = _norm(evidence["text"]).strip()
    return {"pass": any(needle in _norm(str(c)) for c in contexts)}


def check_risk_labels(answer: str, expected: dict) -> dict:
    text = _norm(answer)
    not_possible = "comparison not possible" in text
    if expected.get("no_material_change"):
        said_no_change = _any(NO_CHANGE_PATTERNS, text)
        return {"pass": said_no_change and not not_possible, "said_no_change": said_no_change}
    labels = []
    for label in expected["labels"]:
        hit = [k for k in label["keywords"] if k.lower() in text]
        labels.append({"label": label["label"], "kind": label["kind"], "covered": bool(hit)})
    covered = sum(l["covered"] for l in labels)
    coverage = covered / len(labels) if labels else 0.0
    return {
        "pass": coverage >= 0.5 and not not_possible,
        "coverage": round(coverage, 2),
        "covered": covered,
        "total": len(labels),
        "labels": labels,
    }


def check_passage_ids(answer: str) -> dict:
    """Every passage id the answer cites must exist in that company-year's Item 1A."""
    cited = sorted({m.group(0) for m in PASSAGE_ID.finditer(answer)})
    invalid = [
        pid for pid in cited
        if pid not in _passage_ids(PASSAGE_ID.match(pid).group(1), int(PASSAGE_ID.match(pid).group(2)))
    ]
    return {"pass": not invalid, "cited": len(cited), "invalid": invalid}


def check_refusal(answer: str) -> dict:
    return {"pass": _any(REFUSAL_PATTERNS, _norm(answer))}


def check_tools(record: dict, expected_tools: list[str], config_has_tools: bool) -> dict:
    if not config_has_tools:
        return {"pass": None, "note": "config has no tools"}
    called = {c["name"] for c in record.get("trajectory", {}).get("tool_calls", [])}
    missing = sorted(set(expected_tools) - called)
    return {"pass": not missing, "called": sorted(called), "missing": missing}


def check_run_health(record: dict) -> dict:
    traj = record.get("trajectory", {})
    worker_failures = sum("WORKER FAILED" in str(m) for m in traj.get("worker_reports", []))
    return {
        "pass": not record.get("error") and not record.get("timed_out"),
        "error": record.get("error"),
        "timed_out": bool(record.get("timed_out")),
        "replans": traj.get("replans", 0),
        "worker_failures": worker_failures,
    }


# ---------------------------------------------------------------- one case


def grade(case: dict, record: dict, truth: dict, config_has_tools: bool = True) -> dict:
    answer = record.get("answer") or ""
    expected = case.get("expected", {})
    ctype = case["type"]
    checks: dict[str, dict] = {"health": check_run_health(record)}

    if ctype in {"numeric", "comparison"}:
        checks["facts"] = check_facts(answer, expected["facts"], truth)
        checks["years"] = check_years(answer, expected["facts"])
        if expected.get("derived"):
            checks["derived"] = check_derived(answer, expected["derived"], truth)
    elif ctype == "narrative":
        checks["must_include"] = check_must_include(answer, expected["must_include"])
        checks["evidence_retrieved"] = check_evidence_retrieved(record, expected.get("evidence"))
    elif ctype == "risk_change":
        checks["risk_labels"] = check_risk_labels(answer, expected)
        checks["passage_ids"] = check_passage_ids(answer)
    elif ctype == "missing":
        checks["refusal"] = check_refusal(answer)
        if expected.get("facts"):
            checks["facts"] = check_facts(answer, expected["facts"], truth)

    if case.get("expected_tools"):
        checks["tools"] = check_tools(record, case["expected_tools"], config_has_tools)
    if ctype != "risk_change":
        checks["passage_ids"] = check_passage_ids(answer)
    checks["cites_item"] = {"pass": None, "present": bool(ITEM_CITE.search(answer))}

    # Informational checks (pass is None) never fail a case; evidence_retrieved and tools are
    # diagnostics of how the answer was produced, reported separately from task success.
    diagnostic = {"evidence_retrieved", "tools", "cites_item"}
    code_pass = all(
        c["pass"] for name, c in checks.items() if name not in diagnostic and c["pass"] is not None
    )
    return {"case_id": case["id"], "type": ctype, "checks": checks, "code_pass": code_pass}
