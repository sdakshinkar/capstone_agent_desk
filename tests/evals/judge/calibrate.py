"""Calibrate the judge against human labels with Cohen's kappa (no LLM).

1. Export the judged outputs of a run to a sheet for hand labelling:
       python tests/evals/judge/calibrate.py export <run dir>
   This writes <run dir>/human_labels.csv with one row per judged case. Read the question,
   the rubric and the answer, and fill the human_pass column with 1 (pass) or 0 (fail)
   WITHOUT looking at the judge's verdict (it is deliberately not in the sheet).
   The brief asks for 20+ labelled outputs; judge with --all first so failures are included.

2. Score agreement:
       python tests/evals/judge/calibrate.py score <run dir>
   Prints raw agreement, Cohen's kappa and the confusion matrix, and lists the disagreements
   to read. Kappa corrects agreement for chance: about 0.6+ is usually taken as substantial,
   0.4-0.6 as moderate; below that, fix the rubric or the judge prompt before trusting it.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from evals.cases.loader import load_split  # noqa: E402
from evals.judge.judge import rubric  # noqa: E402

LABELS_FILE = "human_labels.csv"


def cohen_kappa(a: list[int], b: list[int]) -> float:
    """Cohen's kappa for two raters giving 0/1 labels to the same items."""
    if len(a) != len(b) or not a:
        raise ValueError("need two equal-length, non-empty label lists")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    if expected == 1:
        return 1.0  # both raters gave one constant label and agree everywhere
    return (observed - expected) / (1 - expected)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def export(run_dir: Path) -> int:
    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in load_split(meta["split"])}
    results = {(r["case_id"], r["repeat"]): r for r in _read_jsonl(run_dir / "results.jsonl")}
    judged = [j for j in _read_jsonl(run_dir / "judgments.jsonl") if j.get("pass") is not None]
    out = run_dir / LABELS_FILE
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["case_id", "repeat", "type", "question", "rubric", "answer", "human_pass", "notes"])
        for j in judged:
            r = results[(j["case_id"], j["repeat"])]
            case = cases[j["case_id"]]
            writer.writerow([j["case_id"], j["repeat"], case["type"], case["question"],
                             rubric(case), r["answer"], "", ""])
    print(f"Wrote {len(judged)} rows to {out}. Fill human_pass with 1 or 0.")
    return 0


def score(run_dir: Path) -> int:
    judged = {(j["case_id"], j["repeat"]): j for j in _read_jsonl(run_dir / "judgments.jsonl")
              if j.get("pass") is not None}
    human, machine, rows = [], [], []
    with (run_dir / LABELS_FILE).open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            label = row["human_pass"].strip()
            key = (row["case_id"], int(row["repeat"]))
            if label not in {"0", "1"} or key not in judged:
                continue
            human.append(int(label))
            machine.append(int(judged[key]["pass"]))
            rows.append((key, int(label), judged[key]))
    if not human:
        print("No labelled rows yet.")
        return 1
    n = len(human)
    agree = sum(h == m for h, m in zip(human, machine))
    tp = sum(h == 1 and m == 1 for h, m in zip(human, machine))
    tn = sum(h == 0 and m == 0 for h, m in zip(human, machine))
    fp = sum(h == 0 and m == 1 for h, m in zip(human, machine))
    fn = sum(h == 1 and m == 0 for h, m in zip(human, machine))
    print(f"Labelled outputs: {n}" + ("  (brief asks for 20+)" if n < 20 else ""))
    print(f"Raw agreement:    {agree}/{n} = {agree / n:.2f}")
    print(f"Cohen's kappa:    {cohen_kappa(human, machine):.2f}")
    print("Confusion (rows human, columns judge):")
    print(f"             judge pass  judge fail\n  human pass  {tp:10}  {fn:10}\n  human fail  {fp:10}  {tn:10}")
    disagreements = [(k, h, j) for k, h, j in rows if h != int(j["pass"])]
    if disagreements:
        print("\nDisagreements:")
        for (cid, rep), h, j in disagreements:
            print(f"  {cid} r{rep}: human {'pass' if h else 'fail'}, judge {'pass' if j['pass'] else 'fail'} - {j['reason'][:120]}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in {"export", "score"}:
        print(__doc__)
        return 1
    run_dir = Path(argv[1])
    return export(run_dir) if argv[0] == "export" else score(run_dir)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
