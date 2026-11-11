"""Run the golden set against one system config, grade every case with code, save everything.

Run from the project root. Nothing calls OpenRouter unless --yes is given:

    python tests/evals/run_eval.py --config c2_team --split dev --limit 3          # plan only
    python tests/evals/run_eval.py --config c2_team --split dev --limit 3 --yes    # smoke run
    python tests/evals/run_eval.py --config c2_team --split dev --ids n01,t01 --yes
    python tests/evals/run_eval.py --config c2_team --split heldout --repeat 3 --yes
    python tests/evals/run_eval.py --resume tests/evals/runs/<run dir> --yes
    python tests/evals/run_eval.py --regrade tests/evals/runs/<run dir>   # free: re-check saved answers

Each run writes tests/evals/runs/<timestamp>_<config>_<split>/:
    run.json       config, split, case ids, model, git commit, cache settings
    results.jsonl  one line per case run: the answer, trajectory, tokens, cost, latency and the
                   code grade. Written after every case, so an interrupted run keeps its results
                   and --resume continues where it stopped.
    summary.md     the report (also: python tests/evals/report.py <run dir>)

The answers are saved so checkers, the judge and reports can be re-run later without calling
the agent again.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

import yaml  # noqa: E402

from evals.cases.loader import load_split, load_truth, validate  # noqa: E402
from evals.checkers.grade import grade  # noqa: E402
from evals.harness.recorder import BudgetExceeded, Recorder  # noqa: E402
from evals.harness.systems import SYSTEMS_WITH_TOOLS, run_system  # noqa: E402

CONFIG_DIR = EVALS_DIR / "configs"
RUNS_DIR = EVALS_DIR / "runs"
LLM_CACHE_FILE = PROJECT_ROOT / "data" / "eval_llm_cache.sqlite"


def load_config(name_or_path: str) -> dict:
    path = Path(name_or_path)
    if not path.suffix:
        path = CONFIG_DIR / f"{name_or_path}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def select_cases(cases: list[dict], ids: str | None, types: str | None, limit: int | None) -> list[dict]:
    if ids:
        wanted = [i.strip() for i in ids.split(",") if i.strip()]
        by_id = {c["id"]: c for c in cases}
        unknown = [i for i in wanted if i not in by_id]
        if unknown:
            raise SystemExit(f"Unknown case ids for this split: {unknown}")
        cases = [by_id[i] for i in wanted]
    if types:
        allowed = {t.strip() for t in types.split(",")}
        cases = [c for c in cases if c["type"] in allowed]
    return cases[:limit] if limit else cases


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def enable_caches(config: dict, repeat: int) -> dict:
    """Turn on the caches the config asks for; repeats always bypass the LLM cache."""
    cache = config.get("cache", {})
    use_llm_cache = bool(cache.get("llm")) and repeat == 1
    if use_llm_cache:
        from langchain_community.cache import SQLiteCache
        from langchain_core.globals import set_llm_cache

        LLM_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        set_llm_cache(SQLiteCache(database_path=str(LLM_CACHE_FILE)))
    if cache.get("risk_extraction"):
        os.environ["AGENT_DESK_RISK_CACHE"] = "1"
    return {"llm": use_llm_cache, "risk_extraction": bool(cache.get("risk_extraction"))}


def estimate_cost(recorder: Recorder, prices: dict) -> float | None:
    if recorder.cost_usd is not None:
        return recorder.cost_usd
    pin, pout = prices.get("input_per_mtok"), prices.get("output_per_mtok")
    if pin is None or pout is None:
        return None
    return (recorder.input_tokens * pin + recorder.output_tokens * pout) / 1_000_000


def run_case(case: dict, config: dict, truth: dict, repeat_index: int) -> dict:
    limits = config.get("limits", {})
    recorder = Recorder(
        max_tokens=limits.get("max_tokens_per_case"),
        max_llm_calls=limits.get("max_llm_calls_per_case"),
        timeout_s=limits.get("timeout_s"),
    )
    started = time.monotonic()
    output: dict = {}
    error = None
    timed_out = False
    try:
        output = run_system(config["system"], case["question"], callbacks=[recorder])
    except BudgetExceeded as exc:
        error = f"BudgetExceeded: {exc}"
        timed_out = str(exc).startswith("timeout")
    except Exception as exc:  # a crashed run is a result, not a harness failure
        error = f"{type(exc).__name__}: {str(exc)[:500]}"
    latency = time.monotonic() - started

    trace = recorder.summary()
    record = {
        "case_id": case["id"],
        "split": case["split"],
        "type": case["type"],
        "config": config["name"],
        "repeat": repeat_index,
        "question": case["question"],
        "answer": output.get("answer", ""),
        "error": error,
        "timed_out": timed_out,
        "latency_s": round(latency, 2),
        "llm_calls": trace["llm_calls"],
        "input_tokens": trace["input_tokens"],
        "output_tokens": trace["output_tokens"],
        "cost_usd": estimate_cost(recorder, config.get("prices", {})),
        "trajectory": {
            "nodes": trace["nodes"],
            "tool_calls": trace["tool_calls"],
            "contexts": output.get("contexts", []),
            "replans": output.get("replans", 0),
            "worker_reports": output.get("worker_reports", []),
            "plan": output.get("plan"),
        },
    }
    record["grade"] = grade(case, record, truth, config_has_tools=config["system"] in SYSTEMS_WITH_TOOLS)
    return record


ACCOUNT_ERRORS = ("Error code: 401", "Error code: 402", "Insufficient credits", "No auth credentials")


def is_account_error(error: str | None) -> bool:
    """True for errors about the OpenRouter account (bad key, no credits), not about the system."""
    return bool(error) and any(marker in error for marker in ACCOUNT_ERRORS)


def read_results(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def regrade(run_dir: Path) -> int:
    """Re-run the code checks on saved answers (after a checker or gold fix). No LLM calls."""
    from evals.report import summarize_run

    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in load_split(meta["split"])}
    has_tools = meta["config"]["system"] in SYSTEMS_WITH_TOOLS
    truth = load_truth()
    results_file = run_dir / "results.jsonl"
    records = read_results(results_file)
    for record in records:
        before = record["grade"]["code_pass"]
        record["grade"] = grade(by_id[record["case_id"]], record, truth, config_has_tools=has_tools)
        if record["grade"]["code_pass"] != before:
            after = "PASS" if record["grade"]["code_pass"] else "FAIL"
            print(f"  {record['case_id']} r{record['repeat']}: {'PASS' if before else 'FAIL'} -> {after}")
    results_file.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    summary = summarize_run(run_dir)
    (run_dir / "summary.md").write_text(summary, encoding="utf-8")
    print("\n" + summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="config name in tests/evals/configs or a path")
    parser.add_argument("--split", choices=["dev", "heldout"], default="dev")
    parser.add_argument("--ids", help="comma-separated case ids")
    parser.add_argument("--types", help="comma-separated case types, e.g. numeric,narrative")
    parser.add_argument("--limit", type=int, help="run only the first N selected cases")
    parser.add_argument("--repeat", type=int, default=1, help="run each case N times (LLM cache off)")
    parser.add_argument("--max-total-tokens", type=int, help="override the config's run budget")
    parser.add_argument("--resume", type=Path, help="continue an interrupted run directory")
    parser.add_argument("--yes", action="store_true", help="actually call the models (spends credits)")
    parser.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    parser.add_argument("--regrade", type=Path, help="re-run the code checks on a saved run (free)")
    args = parser.parse_args(argv)

    if args.regrade:
        problems = validate()
        if problems:
            print("The golden set is invalid; fix it first:\n  " + "\n  ".join(problems))
            return 2
        return regrade(args.regrade)

    if args.resume:
        meta = json.loads((args.resume / "run.json").read_text(encoding="utf-8"))
        config, split, repeat = meta["config"], meta["split"], meta["repeat"]
        case_ids = meta["case_ids"]
        run_dir = args.resume
    else:
        if not args.config:
            parser.error("--config is required (or --resume)")
        config, split, repeat = load_config(args.config), args.split, args.repeat
        case_ids = None
        run_dir = None

    problems = validate()
    if problems:
        print("The golden set is invalid; fix it first:\n  " + "\n  ".join(problems))
        return 2

    all_cases = load_split(split)
    if case_ids is not None:
        by_id = {c["id"]: c for c in all_cases}
        cases = [by_id[i] for i in case_ids]
    else:
        cases = select_cases(all_cases, args.ids, args.types, args.limit)
    if args.max_total_tokens:
        config.setdefault("limits", {})["max_total_tokens"] = args.max_total_tokens

    done = set()
    if run_dir:
        done = {(r["case_id"], r["repeat"]) for r in read_results(run_dir / "results.jsonl")}
    todo = [(c, r) for r in range(1, repeat + 1) for c in cases if (c["id"], r) not in done]

    print(f"Config {config['name']} | split {split} | {len(cases)} cases x {repeat} repeat(s) "
          f"| {len(todo)} runs to do")
    for case, r in todo[:50]:
        print(f"  {case['id']:4} {case['type']:12} r{r}  {case['question'][:80]}")
    if len(todo) > 50:
        print(f"  ... and {len(todo) - 50} more")
    if not todo:
        print("Nothing to run.")
        return 0
    if not args.yes:
        print("\nPlan only: nothing was sent to OpenRouter. Add --yes to run these cases.")
        return 0

    caches = enable_caches(config, repeat)
    truth = load_truth()
    if run_dir is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = args.runs_dir / f"{stamp}_{config['name']}_{split}"
        run_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "config": config, "split": split, "repeat": repeat,
            "case_ids": [c["id"] for c in cases], "caches": caches,
            "git_commit": git_commit(), "started": datetime.now().isoformat(timespec="seconds"),
        }
        (run_dir / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    results_file = run_dir / "results.jsonl"
    max_total = config.get("limits", {}).get("max_total_tokens")
    spent = sum(r["input_tokens"] + r["output_tokens"] for r in read_results(results_file))
    for n, (case, r) in enumerate(todo, start=1):
        if max_total and spent > max_total:
            print(f"\nRun budget reached ({spent} > {max_total} tokens); stopping. "
                  f"Use --resume {run_dir} with a higher --max-total-tokens to continue.")
            break
        record = run_case(case, config, truth, r)
        if is_account_error(record["error"]):
            # Not the system's fault and not worth repeating for every case: stop, and do not
            # save the run, so --resume retries this case once the account is fixed.
            print(f"\nStopped: OpenRouter refused the request ({record['error'][:160]}).\n"
                  f"Fix the API key or add credits, then: --resume {run_dir} --yes")
            break
        spent += record["input_tokens"] + record["output_tokens"]
        with results_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        status = "PASS" if record["grade"]["code_pass"] else ("ERROR" if record["error"] else "FAIL")
        cost = f"${record['cost_usd']:.4f}" if record["cost_usd"] is not None else "cost n/a"
        print(f"[{n}/{len(todo)}] {status:5} {case['id']:4} r{r} {record['latency_s']:6.1f}s "
              f"{record['llm_calls']:3} calls {record['input_tokens'] + record['output_tokens']:7} tok {cost}"
              + (f"  {record['error'][:80]}" if record["error"] else ""))

    from evals.report import summarize_run

    summary = summarize_run(run_dir)
    (run_dir / "summary.md").write_text(summary, encoding="utf-8")
    print("\n" + summary)
    print(f"Saved to {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
