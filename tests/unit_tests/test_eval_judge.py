"""Tests for the judge and its calibration, with a fake judge model (no credits)."""

import csv
import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from evals.cases.loader import load_split
from evals.judge import calibrate, judge

CASES = {c["id"]: c for c in load_split("dev")}


def test_kappa_known_values():
    assert calibrate.cohen_kappa([1, 1, 0, 0], [1, 1, 0, 0]) == 1.0
    assert calibrate.cohen_kappa([1, 0, 1, 0], [0, 1, 0, 1]) == -1.0
    # 8/10 agreement with balanced labels: (0.8 - 0.5) / 0.5 = 0.6
    a = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
    b = [1, 1, 1, 1, 0, 0, 0, 0, 0, 1]
    assert calibrate.cohen_kappa(a, b) == pytest.approx(0.6)


@pytest.mark.parametrize("reply, expected", [
    ('{"pass": true, "reason": "ok"}', True),
    ('Here you go:\n```json\n{"pass": false, "reason": "missing"}\n```', False),
    ('{"pass": "yes", "reason": "ok"}', True),
    ("I think it passes.", None),
])
def test_parse_verdict(reply, expected):
    assert judge.parse_verdict(reply)["pass"] is expected


def test_rubrics_carry_the_gold_outcome():
    assert "apple has the higher value" in judge.rubric(CASES["c01"])
    assert "age verification" in judge.rubric(CASES["k01"])
    assert "automation, AI and machine learning" in judge.rubric(CASES["k02"])
    no_change = {"type": "risk_change", "expected": {"labels": [], "no_material_change": True}}
    assert "nearly identical" in judge.rubric(no_change)
    assert "Tesla" in judge.rubric(load_split("heldout")[[c["id"] for c in load_split("heldout")].index("m01")])


def test_narrative_prompt_includes_retrieved_passages():
    record = {"case_id": "t01", "answer": "About 166,000.", "trajectory": {
        "tool_calls": [{"name": "search_filing", "output": "approximately 166,000 full-time equivalent employees"}]}}
    user = judge.build_messages(CASES["t01"], record)[1][1]
    assert "166,000 full-time equivalent" in user and "Retrieved passages" in user


def _run_dir(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.json").write_text(json.dumps({"split": "dev", "config": {"name": "c2_team"}}))
    rows = [
        {"case_id": "t01", "repeat": 1, "type": "narrative", "answer": "About 166,000 employees.",
         "grade": {"code_pass": True}, "trajectory": {}},
        {"case_id": "c01", "repeat": 1, "type": "comparison", "answer": "Apple's margin was higher.",
         "grade": {"code_pass": False}, "trajectory": {}},
        {"case_id": "n01", "repeat": 1, "type": "numeric", "answer": "$416.2 billion",
         "grade": {"code_pass": True}, "trajectory": {}},
    ]
    (run / "results.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return run


def test_selection_skips_numeric_and_failed_cases(tmp_path):
    run = _run_dir(tmp_path)
    assert [c["id"] for c, _ in judge.to_judge(run, judge_all=False)] == ["t01"]
    assert [c["id"] for c, _ in judge.to_judge(run, judge_all=True)] == ["t01", "c01"]


def test_judge_and_calibrate_round_trip(tmp_path, monkeypatch, capsys):
    run = _run_dir(tmp_path)
    replies = iter([AIMessage(content='{"pass": true, "reason": "supported"}'),
                    AIMessage(content='{"pass": false, "reason": "wrong direction"}')])
    monkeypatch.setattr(judge, "get_judge_llm", lambda config: GenericFakeChatModel(messages=replies))
    monkeypatch.setattr(judge, "load_judge_config", lambda: {"model": "fake/judge", "llm_cache": False})

    assert judge.main([str(run), "--all"]) == 0  # plan only
    assert not (run / "judgments.jsonl").exists()
    assert judge.main([str(run), "--all", "--yes"]) == 0
    verdicts = [json.loads(l) for l in (run / "judgments.jsonl").read_text().splitlines()]
    assert [(v["case_id"], v["pass"]) for v in verdicts] == [("t01", True), ("c01", False)]

    calibrate.export(run)
    with (run / "human_labels.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert "judge" not in ",".join(rows[0].keys())  # the sheet hides the judge's verdict
    rows[0]["human_pass"], rows[1]["human_pass"] = "1", "1"  # human disagrees on c01
    with (run / "human_labels.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    capsys.readouterr()
    calibrate.score(run)
    out = capsys.readouterr().out
    assert "Raw agreement:    1/2" in out and "c01 r1: human pass, judge fail" in out
