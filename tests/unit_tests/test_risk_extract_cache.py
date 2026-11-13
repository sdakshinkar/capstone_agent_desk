import json

import pytest

from agent_desk.rag import risk_extract as re
from agent_desk.rag.risk_section import RiskPassage

PASSAGES = [RiskPassage("co-2025-1A-1", "Cyber text."), RiskPassage("co-2025-1A-2", "Tax text.")]
RISKS = [
    re.Risk(title="Cyber", summary="s", passage_ids=["co-2025-1A-1"], quote="Cyber text."),
    re.Risk(title="Tax", summary="s", passage_ids=["co-2025-1A-2"], quote="Tax text."),
]


@pytest.fixture
def cache(monkeypatch, tmp_path):
    """Point the cache at a temp folder and count real extractions."""
    monkeypatch.setattr(re, "CACHE_DIR", tmp_path / "risk_cache")
    calls = []

    def fake_extract(passages, llm=None):
        calls.append(llm)
        return RISKS

    monkeypatch.setattr(re, "extract_risks", fake_extract)
    return calls


def test_second_call_is_served_from_the_cache(cache):
    first = re.extract_risks_cached("Co", 2025, PASSAGES)
    second = re.extract_risks_cached("co", "2025", PASSAGES)  # name case and year type do not matter

    assert first == second == RISKS
    assert len(cache) == 1
    saved = json.loads((re.CACHE_DIR / "co-2025.json").read_text(encoding="utf-8"))
    assert saved["risks"] == RISKS and saved["fingerprint"] == re._fingerprint(PASSAGES)


def test_changed_passages_or_prompt_invalidate_the_cache(cache, monkeypatch):
    re.extract_risks_cached("co", 2025, PASSAGES)
    edited = [RiskPassage("co-2025-1A-1", "Cyber text, edited."), PASSAGES[1]]

    re.extract_risks_cached("co", 2025, edited)
    assert len(cache) == 2  # the filing text changed

    monkeypatch.setattr(re, "SYSTEM_PROMPT", re.SYSTEM_PROMPT + " New rule.")
    re.extract_risks_cached("co", 2025, edited)
    assert len(cache) == 3  # the prompt changed


def test_each_company_and_year_has_its_own_file(cache):
    re.extract_risks_cached("co", 2024, PASSAGES)
    re.extract_risks_cached("co", 2025, PASSAGES)
    re.extract_risks_cached("other", 2025, PASSAGES)

    assert len(cache) == 3
    assert sorted(p.name for p in re.CACHE_DIR.iterdir()) == ["co-2024.json", "co-2025.json", "other-2025.json"]


def test_an_injected_model_bypasses_the_cache_both_ways(cache):
    fake_llm = object()

    re.extract_risks_cached("co", 2025, PASSAGES, fake_llm)
    assert cache == [fake_llm] and not re.CACHE_DIR.exists()  # nothing written

    re.extract_risks_cached("co", 2025, PASSAGES)  # default model: fills the cache
    re.extract_risks_cached("co", 2025, PASSAGES, fake_llm)  # ...but the fake model ignores it
    assert cache == [fake_llm, None, fake_llm]


def test_corrupt_or_wrong_shape_cache_files_are_replaced(cache):
    re.CACHE_DIR.mkdir(parents=True)
    path = re.CACHE_DIR / "co-2025.json"

    path.write_text("{not json", encoding="utf-8")
    assert re.extract_risks_cached("co", 2025, PASSAGES) == RISKS

    path.write_text(json.dumps({"fingerprint": re._fingerprint(PASSAGES), "risks": "oops"}), encoding="utf-8")
    assert re.extract_risks_cached("co", 2025, PASSAGES) == RISKS

    assert len(cache) == 2
    assert json.loads(path.read_text(encoding="utf-8"))["risks"] == RISKS


def test_empty_results_are_not_cached(cache, monkeypatch):
    monkeypatch.setattr(re, "extract_risks", lambda passages, llm=None: [])

    assert re.extract_risks_cached("co", 2025, PASSAGES) == []
    assert not re.CACHE_DIR.exists()


def test_an_unwritable_cache_folder_does_not_break_extraction(cache, monkeypatch, tmp_path):
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(re, "CACHE_DIR", blocker)  # mkdir on a file raises OSError

    assert re.extract_risks_cached("co", 2025, PASSAGES) == RISKS


def test_company_year_wrapper_uses_the_cache(cache, monkeypatch):
    monkeypatch.setattr(re, "load_risk_section", lambda company, year: PASSAGES)

    re.extract_company_year_risks("co", 2025)
    re.extract_company_year_risks("co", 2025)

    assert len(cache) == 1
