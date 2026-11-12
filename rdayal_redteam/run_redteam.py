"""Red-team runner for Agent Desk (Role 5, L15; experiment E2).

Run from the project root:

  # sandbox attacks only: no API key, takes seconds
  python -m rdayal_redteam.run_redteam --targets sandbox

  # full suite, defences off then on, plus clean cases for the false-block rate
  python -m rdayal_redteam.run_redteam --defences off --clean
  python -m rdayal_redteam.run_redteam --defences on  --clean
  python -m rdayal_redteam.run_redteam compare results/<off-run> results/<on-run>

Each run writes results/<timestamp>_<defences>/ with:
  results.jsonl   one line per attack (and clean case) per repeat: verdict, evidence, tool calls,
                  tokens, latency, error
  summary.json    the numbers for E2
  summary.md      the same as a table for the evaluation report
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from .checks import evaluate, fill, is_refusal  # noqa: E402
from .fixtures import apply_fixture  # noqa: E402
from .targets import load_guardrails, run_target  # noqa: E402


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _short_calls(rec) -> list[dict[str, Any]]:
    out = []
    for c in rec.tool_calls:
        row: dict[str, Any] = {"tool": c.name, "args": {k: (str(v)[:300]) for k, v in c.args.items()}}
        if c.blocked:
            row["blocked_by_hook"] = c.block_reason  # the model tried; the pre-tool hook stopped it
        if c.overrides:
            row["changed_by_hook"] = c.overrides
        out.append(row)
    return out


def run_attack(attack: dict[str, Any], defences: bool, guard: Any) -> dict[str, Any]:
    with apply_fixture(attack.get("fixture", {})) as extra:
        question = fill(attack["question"], extra)
        rec, seconds = run_target(attack["target"], question, defences, guard)
        evidence = evaluate(attack["success_if"], rec, extra)
    if rec.blocked_by.startswith("input_guard"):
        verdict = "blocked"
    elif evidence:
        verdict = "success"  # the ATTACK succeeded: bad for the system
    elif rec.error:
        verdict = "error"
    else:
        verdict = "defended"
    return {
        "kind": "attack", "id": attack["id"], "category": attack["category"], "owasp": attack["owasp"],
        "target": attack["target"], "vector": attack["vector"], "verdict": verdict, "evidence": evidence,
        "blocked_by": rec.blocked_by, "error": rec.error, "seconds": round(seconds, 2),
        "llm_calls": rec.llm_calls, "input_tokens": rec.input_tokens, "output_tokens": rec.output_tokens,
        "tool_calls": _short_calls(rec), "answer": rec.answer[:3000],
    }


def run_clean(case: dict[str, Any], defences: bool, guard: Any) -> dict[str, Any]:
    rec, seconds = run_target(case["target"], case["question"], defences, guard)
    refused = bool(rec.answer) and is_refusal(rec.answer)
    false_block = bool(rec.blocked_by) or refused
    on_topic = any(e.lower() in rec.answer.lower() for e in case.get("expect_any", []))
    return {
        "kind": "clean", "id": case["id"], "target": case["target"],
        "verdict": "false_block" if false_block else ("error" if rec.error else "answered"),
        "on_topic": on_topic, "blocked_by": rec.blocked_by, "refused": refused, "error": rec.error,
        "seconds": round(seconds, 2), "llm_calls": rec.llm_calls,
        "input_tokens": rec.input_tokens, "output_tokens": rec.output_tokens,
        "tool_calls": _short_calls(rec), "answer": rec.answer[:3000],
    }


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def summarise(rows: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    attacks = [r for r in rows if r["kind"] == "attack"]
    clean = [r for r in rows if r["kind"] == "clean"]
    scored = [r for r in attacks if r["verdict"] != "error"]  # errors reported separately
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in attacks:
        by_cat[r["category"]][r["verdict"]] += 1
    llm_rows = [r for r in rows if r["target"] != "sandbox"]
    secs = sorted(r["seconds"] for r in llm_rows) or [0.0]
    p95 = secs[min(len(secs) - 1, int(round(0.95 * (len(secs) - 1))))]
    price_in, price_out = meta.get("price_in_per_m", 0.0), meta.get("price_out_per_m", 0.0)
    tok_in = sum(r["input_tokens"] for r in rows)
    tok_out = sum(r["output_tokens"] for r in rows)
    return {
        **meta,
        "attacks_run": len(attacks),
        "attack_success": sum(r["verdict"] == "success" for r in attacks),
        "attack_success_rate": (sum(r["verdict"] == "success" for r in scored) / len(scored)) if scored else None,
        "blocked_at_input": sum(r["verdict"] == "blocked" for r in attacks),
        "defended": sum(r["verdict"] == "defended" for r in attacks),
        "errors": sum(r["verdict"] == "error" for r in attacks),
        "successful_ids": sorted({r["id"] for r in attacks if r["verdict"] == "success"}),
        "by_category": {k: dict(v) for k, v in sorted(by_cat.items())},
        "clean_run": len(clean),
        "false_blocks": sum(r["verdict"] == "false_block" for r in clean),
        "false_block_rate": (sum(r["verdict"] == "false_block" for r in clean) / len(clean)) if clean else None,
        "clean_errors": sum(r["verdict"] == "error" for r in clean),
        "median_seconds": statistics.median(secs),
        "p95_seconds": p95,
        "input_tokens": tok_in,
        "output_tokens": tok_out,
        "est_cost_usd": round(tok_in / 1e6 * price_in + tok_out / 1e6 * price_out, 4),
    }


def summary_markdown(s: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# Red-team run: defences {s['defences']}  ({s['started']})",
        "",
        f"- Targets: {', '.join(s['targets'])}; repeats: {s['repeats']}; model IDs: see src/agent_desk/llm/llm.py",
        f"- **Attack success: {_pct(s['attack_success'], s['attacks_run'] - s['errors'])}** "
        f"(errors excluded and listed: {s['errors']}; blocked at input: {s['blocked_at_input']})",
        f"- **False blocks on clean cases: {_pct(s['false_blocks'], s['clean_run'])}** (clean errors: {s['clean_errors']})",
        f"- Latency (LLM targets): median {s['median_seconds']:.1f}s, p95 {s['p95_seconds']:.1f}s",
        f"- Tokens: {s['input_tokens']:,} in / {s['output_tokens']:,} out; est. cost ${s['est_cost_usd']}",
        "",
        "| Category | success | defended | blocked | error |",
        "|---|---|---|---|---|",
    ]
    for cat, v in s["by_category"].items():
        lines.append(f"| {cat} | {v.get('success', 0)} | {v.get('defended', 0)} | {v.get('blocked', 0)} | {v.get('error', 0)} |")
    lines += ["", "## Attack results", "", "| ID | target | vector | verdict | evidence / error |", "|---|---|---|---|---|"]
    for r in rows:
        if r["kind"] != "attack":
            continue
        why = "; ".join(r["evidence"]) or r["blocked_by"] or r["error"]
        lines.append(f"| {r['id']} | {r['target']} | {r['vector']} | {r['verdict']} | {why[:160].replace('|', '/')} |")
    clean = [r for r in rows if r["kind"] == "clean"]
    if clean:
        lines += ["", "## Clean cases", "", "| ID | verdict | on topic | note |", "|---|---|---|---|"]
        for r in clean:
            lines.append(f"| {r['id']} | {r['verdict']} | {r['on_topic']} | {(r['blocked_by'] or r['error'])[:120]} |")
    return "\n".join(lines) + "\n"


def compare(off_dir: Path, on_dir: Path) -> str:
    off = json.loads((off_dir / "summary.json").read_text(encoding="utf-8"))
    on = json.loads((on_dir / "summary.json").read_text(encoding="utf-8"))

    def rate(x):
        return "n/a" if x is None else f"{100 * x:.0f}%"

    cats = sorted(set(off["by_category"]) | set(on["by_category"]))
    lines = [
        "# E2: do the defences work?",
        "",
        "| Metric | Defences off | Defences on |",
        "|---|---|---|",
        f"| Attack success rate | {rate(off['attack_success_rate'])} ({off['attack_success']}) | {rate(on['attack_success_rate'])} ({on['attack_success']}) |",
        f"| Blocked at input | {off['blocked_at_input']} | {on['blocked_at_input']} |",
        f"| Errors / timeouts | {off['errors']} | {on['errors']} |",
        f"| False-block rate (clean) | {rate(off['false_block_rate'])} | {rate(on['false_block_rate'])} |",
        f"| Median / p95 latency (s) | {off['median_seconds']:.1f} / {off['p95_seconds']:.1f} | {on['median_seconds']:.1f} / {on['p95_seconds']:.1f} |",
        f"| Tokens in / out | {off['input_tokens']:,} / {off['output_tokens']:,} | {on['input_tokens']:,} / {on['output_tokens']:,} |",
        f"| Est. cost (USD) | {off['est_cost_usd']} | {on['est_cost_usd']} |",
        "",
        "| Category | successes off | successes on |",
        "|---|---|---|",
    ]
    for c in cats:
        lines.append(f"| {c} | {off['by_category'].get(c, {}).get('success', 0)} | {on['by_category'].get(c, {}).get('success', 0)} |")
    fixed = sorted(set(off["successful_ids"]) - set(on["successful_ids"]))
    still = sorted(set(on["successful_ids"]))
    lines += ["", f"Fixed by defences: {', '.join(fixed) or 'none'}", "", f"Still succeeding with defences on: {', '.join(still) or 'none'}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "compare":
        text = compare(Path(argv[1]), Path(argv[2]))
        out = Path(argv[2]).parent / "E2_comparison.md"
        out.write_text(text, encoding="utf-8")
        print(text)
        print(f"Saved {out}")
        return 0

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--defences", choices=["off", "on"], default="off")
    p.add_argument("--targets", nargs="*", default=None, help="limit to these targets (team researcher quant risk sandbox)")
    p.add_argument("--ids", nargs="*", default=None, help="run only these attack IDs")
    p.add_argument("--clean", action="store_true", help="also run clean cases (false-block rate)")
    p.add_argument("--repeats", type=int, default=1, help="brief asks for 3 on the final comparison")
    p.add_argument("--include-destructive", action="store_true", help="run attacks marked destructive (memory bomb)")
    p.add_argument("--guardrails-module", default="rdayal_guardrails")
    p.add_argument("--price-in-per-m", type=float, default=0.0, help="USD per 1M input tokens (check OpenRouter)")
    p.add_argument("--price-out-per-m", type=float, default=0.0, help="USD per 1M output tokens")
    p.add_argument("--out", type=Path, default=HERE / "results")
    args = p.parse_args(argv)

    attacks = load_jsonl(HERE / "attacks.jsonl")
    attacks = [a for a in attacks if args.include_destructive or not a.get("destructive")]
    if args.targets:
        attacks = [a for a in attacks if a["target"] in args.targets]
    if args.ids:
        attacks = [a for a in attacks if a["id"] in args.ids]
    clean = load_jsonl(HERE / "clean_cases.jsonl") if args.clean else []
    if args.targets:
        clean = [c for c in clean if c["target"] in args.targets]

    defences = args.defences == "on"
    guard = load_guardrails(args.guardrails_module) if defences else None
    if defences and guard is None:
        print(f"NOTE: no module {args.guardrails_module}; only AGENT_DESK_DEFENCES=on is set. "
              "If the team's code ignores it, 'on' will equal 'off'.")

    started = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.out / f"{started}_defences-{args.defences}"
    run_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    total = (len(attacks) + len(clean)) * args.repeats
    with (run_dir / "results.jsonl").open("w", encoding="utf-8") as f:
        for rep in range(args.repeats):
            for item, fn in [(a, run_attack) for a in attacks] + [(c, run_clean) for c in clean]:
                t0 = time.perf_counter()
                row = {**fn(item, defences, guard), "repeat": rep, "defences": args.defences}
                rows.append(row)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                print(f"[{len(rows)}/{total}] {row['id']:7s} {row['verdict']:12s} {time.perf_counter() - t0:6.1f}s "
                      f"{('; '.join(row.get('evidence', [])) or row['error'])[:100]}")

    meta = {"defences": args.defences, "started": started, "repeats": args.repeats,
            "targets": sorted({r["target"] for r in rows}),
            "price_in_per_m": args.price_in_per_m, "price_out_per_m": args.price_out_per_m}
    summary = summarise(rows, meta)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "summary.md").write_text(summary_markdown(summary, rows), encoding="utf-8")
    print(f"\nAttack success: {summary['attack_success']}/{summary['attacks_run'] - summary['errors']} "
          f"| false blocks: {summary['false_blocks']}/{summary['clean_run']} | saved to {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
