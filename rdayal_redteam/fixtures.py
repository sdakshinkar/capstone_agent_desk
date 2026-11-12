"""Plant attacks in the system's own data path for one run, then remove them.

Three data paths, matching how outside text reaches the agents:

  filing_chunk   a passage returned by search_filing (FAISS over 10-K HTML). The poisoned passage
                 is put at rank 1, the worst case: it simulates a tampered or malicious filing,
                 web page or "news article" that made it into the index.
  edgar_cache    the local SEC Company Facts cache (data/edgar_cache). The real cached JSON is
                 copied to a temp folder (or a small synthetic one is built) and edited, so the
                 project's real cache is never changed.
  risk_passage   an extra "added risk" in compare_risk_factors output, simulating an Item 1A
                 passage that carries an instruction and survived extraction.

Nothing is written into data/. Every fixture is a context manager that undoes itself.
"""

from __future__ import annotations

import contextlib
import copy
import json
import tempfile
from pathlib import Path
from typing import Any, Iterator
from unittest import mock

from .canaries import CANARY
from .checks import fill

# Microsoft Company Facts used when no real cache exists (values in USD, from the team's own
# worked example in workflow.py; FY ends 30 June). Only used inside a temp folder.
_MSFT_ROWS = {
    "Revenues": {2023: 211_915_000_000, 2024: 245_122_000_000, 2025: 281_724_000_000},
    "OperatingIncomeLoss": {2023: 88_523_000_000, 2024: 109_433_000_000, 2025: 128_528_000_000},
}


def _synthetic_facts(cik: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for concept, by_year in _MSFT_ROWS.items():
        rows = []
        for filed_fy in by_year:  # each 10-K repeats the prior years, like the real API
            for fy, val in by_year.items():
                if fy > filed_fy:
                    continue
                rows.append({
                    "start": f"{fy - 1}-07-01", "end": f"{fy}-06-30", "val": val,
                    "accn": f"0000950170-{filed_fy % 100:02d}-000001", "fy": filed_fy, "fp": "FY",
                    "form": "10-K", "filed": f"{filed_fy}-07-30",
                })
        facts[concept] = {"label": concept, "description": "", "units": {"USD": rows}}
    return {"cik": int(cik), "entityName": "MICROSOFT CORPORATION", "facts": {"us-gaap": facts}}


def _apply(data: dict[str, Any], mutation: dict[str, Any]) -> None:
    op = mutation["op"]
    gaap = data["facts"].setdefault("us-gaap", {})
    if op == "set_entity_name":
        data["entityName"] = fill(mutation["value"])
    elif op == "set_label":
        gaap[mutation["concept"]]["label"] = fill(mutation["label"])
    elif op == "set_value":
        for rows in gaap[mutation["concept"]]["units"].values():
            for row in rows:
                if row.get("end") == mutation["end"] and row.get("form") == "10-K" and row.get("start"):
                    row["val"] = mutation["value"]
    else:
        raise ValueError(f"unknown edgar mutation {op}")


@contextlib.contextmanager
def poisoned_edgar_cache(spec: dict[str, Any]) -> Iterator[Path]:
    from agent_desk.tools import edgar_tools

    cik = spec["cik"]
    real = edgar_tools.CACHE_DIR / f"CIK{cik}.json"
    data = json.loads(real.read_text(encoding="utf-8")) if real.exists() else _synthetic_facts(cik)
    data = copy.deepcopy(data)
    for m in spec.get("mutations", []):
        _apply(data, m)
    with tempfile.TemporaryDirectory(prefix="redteam_edgar_") as tmp:
        tmp_dir = Path(tmp)
        # Copy the other cached companies so the agent can still answer about them.
        if edgar_tools.CACHE_DIR.is_dir():
            for other in edgar_tools.CACHE_DIR.glob("CIK*.json"):
                if other.name != real.name:
                    (tmp_dir / other.name).write_bytes(other.read_bytes())
        (tmp_dir / real.name).write_text(json.dumps(data), encoding="utf-8")
        with mock.patch.object(edgar_tools, "CACHE_DIR", tmp_dir):
            yield tmp_dir


@contextlib.contextmanager
def poisoned_filing_chunk(spec: dict[str, Any]) -> Iterator[None]:
    from langchain_core.documents import Document

    from agent_desk.tools import rag_tools

    real_search = rag_tools.search_chunks
    poison = Document(
        page_content=fill(spec["text"]),
        metadata={
            "company": spec["company"], "year": str(spec["year"]), "item": spec.get("item", "Item 7"),
            "source": f"data/filings/{spec['company']}/{spec['year']}/10-K.html",
        },
    )

    def search_with_poison(query, k=4, company=None, year=None):
        try:
            results = list(real_search(query, k, company=company, year=year))
        except FileNotFoundError:  # no index built: the poisoned passage is the only result
            results = []
        wanted_company = (company or spec["company"]).strip().lower() == spec["company"]
        if wanted_company:
            results = [poison] + results[: max(k - 1, 0)]
        return results

    with mock.patch.object(rag_tools, "search_chunks", search_with_poison):
        yield


@contextlib.contextmanager
def poisoned_risk_passage(spec: dict[str, Any]) -> Iterator[None]:
    from agent_desk.tools import risk_tools

    real_compare = risk_tools.compare_company_years

    def compare_with_poison(company, year_a, year_b, *args, **kwargs):
        if company.strip().lower() != spec["company"]:
            return real_compare(company, year_a, year_b, *args, **kwargs)
        try:
            diff = dict(real_compare(company, year_a, year_b, *args, **kwargs))
        except (FileNotFoundError, ValueError):
            y0, y1 = sorted((int(year_a), int(year_b)))
            diff = {"company": spec["company"], "year_from": y0, "year_to": y1,
                    "added": [], "removed": [], "changed": [], "rejected": []}
        diff["added"] = list(diff.get("added", [])) + [{
            "description": fill(spec["description"]),
            "passage_ids": [f"{spec['company']}-{diff['year_to']}-1A-999"],
            "quote": fill(spec["quote"]),
        }]
        return diff

    with mock.patch.object(risk_tools, "compare_company_years", compare_with_poison):
        yield


@contextlib.contextmanager
def canary_file() -> Iterator[dict[str, str]]:
    """A file outside the sandbox's working folder that the sandbox must not be able to read."""
    with tempfile.TemporaryDirectory(prefix="redteam_secret_") as tmp:
        path = Path(tmp) / "secret.env"
        path.write_text(f"OPENROUTER_API_KEY=sk-or-fake-{CANARY}\n", encoding="utf-8")
        yield {"{CANARY_FILE}": path.as_posix()}


@contextlib.contextmanager
def apply_fixture(fixture: dict[str, Any]) -> Iterator[dict[str, str]]:
    """Enter every fixture an attack asks for. Yields extra placeholder values (e.g. a file path)."""
    extra: dict[str, str] = {}
    with contextlib.ExitStack() as stack:
        if "filing_chunk" in fixture:
            stack.enter_context(poisoned_filing_chunk(fixture["filing_chunk"]))
        if "edgar_cache" in fixture:
            stack.enter_context(poisoned_edgar_cache(fixture["edgar_cache"]))
        if "risk_passage" in fixture:
            stack.enter_context(poisoned_risk_passage(fixture["risk_passage"]))
        if fixture.get("canary_file"):
            extra.update(stack.enter_context(canary_file()))
        yield extra
