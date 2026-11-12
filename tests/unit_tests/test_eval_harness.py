"""Tests for the eval harness with fake models (no OpenRouter calls, no credits)."""

import json
from typing import Any

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent_desk.agents import single_agent, single_prompt_baseline
from agent_desk.rag import risk_extract
from agent_desk.rag.risk_section import RiskPassage
from agent_desk.tools import rag_tools
from evals import report, run_eval
from evals.harness import systems
from evals.harness.recorder import BudgetExceeded, Recorder

USAGE = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}


class ToolFakeChat(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any):
        return self


def _doc(text):
    return Document(page_content=text, metadata={"company": "apple", "year": "2025", "item": "Item 1"})


def _fake_c1(monkeypatch, answer="Apple had about 166,000 employees (fiscal 2025, Item 1)."):
    monkeypatch.setattr(rag_tools, "search_chunks", lambda q, k, company=None, year=None: [
        _doc("the Company had approximately 166,000 full-time equivalent employees")])
    call = AIMessage(content="", usage_metadata=USAGE, tool_calls=[
        {"name": "search_filing", "args": {"query": "employees", "company": "apple", "year": 2025}, "id": "c1"}])
    final = AIMessage(content=answer, usage_metadata=USAGE)
    monkeypatch.setattr(single_agent, "get_tool_llm", lambda: ToolFakeChat(messages=iter([call, final])))


def test_recorder_sees_nested_tool_and_model_calls(monkeypatch):
    _fake_c1(monkeypatch)
    rec = Recorder()
    out = systems.run_system("c1_single_agent", "How many employees does Apple have?", [rec])
    assert "166,000" in out["answer"]
    assert [c["name"] for c in rec.tool_calls] == ["search_filing"]
    assert "166,000" in rec.tool_calls[0]["output"]
    assert rec.llm_calls == 2
    assert rec.input_tokens == 200 and rec.output_tokens == 40


def test_budget_stops_before_the_next_model_call(monkeypatch):
    _fake_c1(monkeypatch)
    with pytest.raises(BudgetExceeded):
        systems.run_system("c1_single_agent", "q", [Recorder(max_llm_calls=1)])


def test_c0_records_its_passages(monkeypatch):
    seen = []
    monkeypatch.setattr(single_prompt_baseline, "search_chunks",
                        lambda q, k, company=None, year=None: seen.append(company) or [_doc(f"text for {company}")])
    monkeypatch.setattr(single_prompt_baseline, "get_tool_llm",
                        lambda: GenericFakeChatModel(messages=iter([AIMessage(content="answer")])))
    out = systems.run_system("c0_single_prompt", "Compare Microsoft and Google margins", [Recorder()])
    assert seen == ["microsoft", "alphabet"]
    assert out["contexts"] == ["text for microsoft", "text for alphabet"]


def test_company_detection():
    assert single_prompt_baseline.companies_in("Goldman Sachs vs Bank of America") == ["goldman_sachs", "bank_of_america"]
    assert single_prompt_baseline.companies_in("What is metadata?") == []


def test_risk_extraction_cache(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(risk_extract, "RISK_CACHE_DIR", tmp_path)
    monkeypatch.setattr(risk_extract, "get_tool_llm", lambda: object())
    monkeypatch.setattr(risk_extract, "_extract_risks", lambda p, llm: calls.append(1) or [{"title": "t"}])
    passages = [RiskPassage("apple-2025-1A-1", "Supply chain risk.")]
    monkeypatch.setenv("AGENT_DESK_RISK_CACHE", "1")
    assert risk_extract.extract_risks(passages) == [{"title": "t"}]
    assert risk_extract.extract_risks(passages) == [{"title": "t"}]
    assert len(calls) == 1  # second call came from disk
    monkeypatch.setenv("AGENT_DESK_RISK_CACHE", "0")
    risk_extract.extract_risks(passages)
    assert len(calls) == 2  # cache off: extracts again


def test_plan_only_without_yes(tmp_path, capsys):
    code = run_eval.main(["--config", "c2_team", "--split", "dev", "--limit", "2", "--runs-dir", str(tmp_path)])
    assert code == 0
    assert "Plan only" in capsys.readouterr().out
    assert not any(tmp_path.iterdir())  # nothing was run or written


def test_out_of_credits_stops_the_run_without_saving(monkeypatch, tmp_path, capsys):
    calls = []

    def broke(question):
        calls.append(question)
        raise RuntimeError("Error code: 402 - Insufficient credits. Add more using https://openrouter.ai")

    monkeypatch.setitem(systems.SYSTEMS, "c2_team", broke)
    monkeypatch.setattr(run_eval, "enable_caches", lambda config, repeat: {"llm": False})
    run_eval.main(["--config", "c2_team", "--split", "dev", "--limit", "3", "--yes", "--runs-dir", str(tmp_path)])
    assert len(calls) == 1  # stopped after the first refusal
    run_dir = next(tmp_path.iterdir())
    assert not (run_dir / "results.jsonl").exists()  # nothing saved, so --resume retries it
    assert "Stopped: OpenRouter refused" in capsys.readouterr().out


def test_end_to_end_run_with_fake_system(monkeypatch, tmp_path):
    answers = {"n01": "Apple's fiscal 2025 revenue was $416.16 billion.",
               "n02": "Apple's fiscal 2024 operating margin was 25.0%."}  # n02 is wrong on purpose

    def fake_system(question):
        case_id = "n01" if "revenue" in question else "n02"
        return {"answer": answers[case_id], "contexts": [], "replans": 0, "worker_reports": []}

    monkeypatch.setitem(systems.SYSTEMS, "c2_team", fake_system)
    monkeypatch.setattr(run_eval, "enable_caches", lambda config, repeat: {"llm": False})
    code = run_eval.main(["--config", "c2_team", "--split", "dev", "--ids", "n01,n02",
                          "--yes", "--runs-dir", str(tmp_path)])
    assert code == 0
    run_dir = next(tmp_path.iterdir())
    results = [json.loads(l) for l in (run_dir / "results.jsonl").read_text().splitlines()]
    assert [r["grade"]["code_pass"] for r in results] == [True, False]
    summary = (run_dir / "summary.md").read_text()
    assert "**1/2**" in summary and "`n02`" in summary

    # Regrade re-checks saved answers with no system calls; a stale grade gets fixed.
    stale = [dict(r, grade={"code_pass": not r["grade"]["code_pass"]}) for r in results]
    (run_dir / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in stale))
    monkeypatch.setitem(systems.SYSTEMS, "c2_team", lambda q: pytest.fail("regrade must not run the system"))
    assert run_eval.main(["--regrade", str(run_dir)]) == 0
    regraded = [json.loads(l) for l in (run_dir / "results.jsonl").read_text().splitlines()]
    assert [r["grade"]["code_pass"] for r in regraded] == [True, False]

    # Resume finds nothing left to do; a judge verdict then lowers the score.
    assert run_eval.main(["--resume", str(run_dir), "--yes"]) == 0
    (run_dir / "judgments.jsonl").write_text(json.dumps({"case_id": "n01", "repeat": 1, "pass": False}) + "\n")
    assert "**0/2**" in report.summarize_run(run_dir)
