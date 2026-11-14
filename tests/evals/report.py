"""Summarize eval runs from their saved results (no LLM).

    python tests/evals/report.py <run dir>                  # one run
    python tests/evals/report.py <run dir> <run dir> ...    # side by side (e.g. C0 / C1 / C2)

Reports what the brief asks for in every configuration: task-success counts (by case type),
errors and timeouts (failed runs are counted, never dropped), cost per case, median and 95th
percentile latency, plus LLM calls and tokens. With --repeat runs, success is given per repeat
with its spread. If judgments.jsonl exists in the run (from judge/judge.py), a case passes only
when both the code checks and the judge pass.

Policy violations, attack success and false blocks need the guardrails and red-team suite
(experiment E2), which are not built yet, so they are not reported here.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

TYPES = ["numeric", "comparison", "narrative", "risk_change", "missing"]


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def load_run(run_dir: Path) -> tuple[dict, list[dict]]:
    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    results = _read_jsonl(run_dir / "results.jsonl")
    judgments = {(j["case_id"], j.get("repeat", 1)): j for j in _read_jsonl(run_dir / "judgments.jsonl")}
    for r in results:
        j = judgments.get((r["case_id"], r["repeat"]))
        r["judge_pass"] = j["pass"] if j else None
        r["final_pass"] = r["grade"]["code_pass"] and (j["pass"] if j else True)
    return meta, results


def metrics(results: list[dict]) -> dict:
    n = len(results)
    latencies = [r["latency_s"] for r in results]
    costs = [r["cost_usd"] for r in results if r.get("cost_usd") is not None]
    tokens = [r["input_tokens"] + r["output_tokens"] for r in results]
    by_type: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in results:
        by_type[r["type"]][0] += bool(r["final_pass"])
        by_type[r["type"]][1] += 1
    tools_checked = [r["grade"]["checks"]["tools"]["pass"] for r in results
                     if r["grade"]["checks"].get("tools", {}).get("pass") is not None]
    evidence = [r["grade"]["checks"]["evidence_retrieved"]["pass"] for r in results
                if r["grade"]["checks"].get("evidence_retrieved", {}).get("pass") is not None]
    verified = [r["grade"]["checks"]["numbers_verified"] for r in results
                if "numbers_verified" in r["grade"]["checks"]]
    sandbox = [r["grade"]["checks"]["calc_in_sandbox"]["used"] for r in results
               if r["grade"]["checks"].get("calc_in_sandbox", {}).get("applies")]
    critic = [r["trajectory"]["critic"] for r in results
              if (r["trajectory"].get("critic") or {}).get("passed") is not None]
    open_issues: dict[str, int] = defaultdict(int)
    for c in critic:
        if c["passed"] is False:
            for issue in c.get("issues", []):
                open_issues[issue.get("type") or "?"] += 1
    repeats: dict[int, list[bool]] = defaultdict(list)
    for r in results:
        repeats[r["repeat"]].append(bool(r["final_pass"]))
    per_repeat = {k: sum(v) for k, v in sorted(repeats.items())}
    return {
        "cases": n,
        "passed": sum(bool(r["final_pass"]) for r in results),
        "code_passed": sum(bool(r["grade"]["code_pass"]) for r in results),
        "judged": sum(r["judge_pass"] is not None for r in results),
        "errors": sum(bool(r["error"]) and not r["timed_out"] for r in results),
        "timeouts": sum(bool(r["timed_out"]) for r in results),
        "replans": sum(r["trajectory"].get("replans", 0) for r in results),
        "by_type": dict(by_type),
        "latency_p50": _percentile(latencies, 0.5),
        "latency_p95": _percentile(latencies, 0.95),
        "llm_calls_mean": statistics.mean(r["llm_calls"] for r in results) if n else 0,
        "tokens_mean": statistics.mean(tokens) if tokens else 0,
        "tokens_total": sum(tokens),
        "cost_per_case": statistics.mean(costs) if costs else None,
        "cost_total": sum(costs) if costs else None,
        "cost_known": len(costs),
        "tool_use_rate": (sum(tools_checked), len(tools_checked)),
        "evidence_rate": (sum(evidence), len(evidence)),
        "numbers_verified": (sum(v["verified"] for v in verified), sum(v["total"] for v in verified)),
        "sandbox_rate": (sum(sandbox), len(sandbox)),
        # Compliance critic (C2): first-draft passes, passes after revision, notes still failing.
        "critic_runs": len(critic),
        "critic_first_pass": sum(c["passed"] and c.get("revisions", 0) == 0 for c in critic),
        "critic_revised_pass": sum(c["passed"] and c.get("revisions", 0) > 0 for c in critic),
        "critic_failed": sum(c["passed"] is False for c in critic),
        "critic_revisions_mean": statistics.mean(c.get("revisions", 0) for c in critic) if critic else None,
        "critic_open_issues": dict(open_issues),
        "per_repeat": per_repeat,
    }


def _fmt(value, spec: str = ".1f", none: str = "n/a") -> str:
    return none if value is None else format(value, spec)


def _rate(pair: tuple[int, int]) -> str:
    hit, total = pair
    return f"{hit}/{total}" if total else "n/a"


def _share(pair: tuple[int, int]) -> str:
    hit, total = pair
    return f"{hit}/{total} ({hit / total:.0%})" if total else "n/a"


def _table(columns: list[tuple[str, dict]]) -> str:
    header = "| Metric | " + " | ".join(name for name, _ in columns) + " |"
    sep = "|---|" + "---|" * len(columns)
    rows = []

    def row(label, fn):
        rows.append(f"| {label} | " + " | ".join(fn(m) for _, m in columns) + " |")

    row("Task success", lambda m: f"**{m['passed']}/{m['cases']}**")
    row("  code checks passed", lambda m: f"{m['code_passed']}/{m['cases']}")
    row("  judged cases", lambda m: str(m["judged"]))
    for t in TYPES:
        row(f"  {t}", lambda m, t=t: _rate(tuple(m["by_type"].get(t, (0, 0)))))
    row("Errors (crash / budget)", lambda m: str(m["errors"]))
    row("Timeouts", lambda m: str(m["timeouts"]))
    row("Replans", lambda m: str(m["replans"]))
    row("Latency p50 (s)", lambda m: _fmt(m["latency_p50"]))
    row("Latency p95 (s)", lambda m: _fmt(m["latency_p95"]))
    row("LLM calls / case", lambda m: _fmt(m["llm_calls_mean"]))
    row("Tokens / case", lambda m: _fmt(m["tokens_mean"], ",.0f"))
    row("Tokens total", lambda m: f"{m['tokens_total']:,}")
    row("Cost / case (USD)", lambda m: _fmt(m["cost_per_case"], ".4f"))
    row("Cost total (USD)", lambda m: _fmt(m["cost_total"], ".4f")
        + (f" ({m['cost_known']}/{m['cases']} known)" if m["cost_total"] is not None else ""))
    row("Expected tool called", lambda m: _rate(m["tool_use_rate"]))
    row("Evidence retrieved", lambda m: _rate(m["evidence_rate"]))
    row("Figures verified vs XBRL", lambda m: _share(m["numbers_verified"]))
    row("Calculations in sandbox", lambda m: _rate(m["sandbox_rate"]))
    row("Critic: passed first draft", lambda m: _rate((m["critic_first_pass"], m["critic_runs"])))
    row("Critic: passed after revision", lambda m: _rate((m["critic_revised_pass"], m["critic_runs"])))
    row("Critic: still failing (flagged)", lambda m: _rate((m["critic_failed"], m["critic_runs"])))
    row("Critic revisions / case", lambda m: _fmt(m["critic_revisions_mean"], ".2f"))
    row("Critic open issues by type", lambda m: ", ".join(
        f"{k} {v}" for k, v in sorted(m["critic_open_issues"].items())) or ("none" if m["critic_runs"] else "n/a"))
    row("Success per repeat", lambda m: ", ".join(f"r{k}: {v}" for k, v in m["per_repeat"].items()))
    return "\n".join([header, sep, *rows])


def _failures(results: list[dict]) -> str:
    lines = []
    for r in results:
        if r["final_pass"]:
            continue
        reasons = [name for name, c in r["grade"]["checks"].items() if c.get("pass") is False
                   and name not in {"tools", "evidence_retrieved"}]
        if r["judge_pass"] is False:
            reasons.append("judge")
        why = r["error"] or ", ".join(reasons) or "?"
        lines.append(f"- `{r['case_id']}` r{r['repeat']} ({r['type']}): {why[:150]}")
    return "\n".join(lines) or "None."


def summarize_run(run_dir: Path) -> str:
    meta, results = load_run(Path(run_dir))
    name = meta["config"]["name"]
    if not results:
        return f"# {name} ({meta['split']})\n\nNo results yet.\n"
    m = metrics(results)
    caches = ", ".join(k for k, v in meta.get("caches", {}).items() if v) or "none"
    return (
        f"# {name} on {meta['split']}\n\n"
        f"Model {meta['config'].get('model')} | commit {meta.get('git_commit')} | "
        f"started {meta.get('started')} | caches: {caches} | "
        f"search mode: {meta['config'].get('search_mode') or 'default'}\n\n"
        f"{_table([(name, m)])}\n\n## Failed cases\n\n{_failures(results)}\n"
    )


def compare_runs(run_dirs: list[Path]) -> str:
    columns = []
    for d in run_dirs:
        meta, results = load_run(Path(d))
        columns.append((f"{meta['config']['name']} ({meta['split']})", metrics(results)))
    return "# Comparison\n\n" + _table(columns) + "\n"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    dirs = [Path(a) for a in argv]
    print(summarize_run(dirs[0]) if len(dirs) == 1 else compare_runs(dirs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
