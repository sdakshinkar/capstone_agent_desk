# Eval evidence

Copies of the eval runs cited in the evaluation report (`tests/evals/runs/` itself is not in git).
Each folder holds `run.json` (config, commit, split, caches, search mode), `results.jsonl` (every
answer with its trajectory, cost, latency and code grade) and `summary.md`. Where present,
`judgments.jsonl` holds the judge's verdicts and `human_labels.csv` the hand labels used to
calibrate the judge.

| Run | What it is |
|---|---|
| `20261113-134923_c0_single_prompt_dev` | E1 dev, C0 single prompt (semantic search) |
| `20261113-144116_c1_single_agent_dev` | E1 dev, C1 single agent (semantic), after the tool-call prompt fix; judge calibration set 1 |
| `20261111-185914_c2_team_dev` | E1 dev, C2 team (semantic), before develop's run_python merge; judge calibration set 2 |
| `20261112-183020_c2_team_dev` | C2 numeric and comparison cases after merging develop (quant worker with run_python) |
| `20261113-161734_c0_single_prompt_dev` | C0 with hybrid search forced (`--search-mode hybrid`) |
| `20261113-161828_c1_single_agent_dev` | C1 with hybrid search; 7 cases hit a provider glitch (no tool call), so not used for comparison |
| `20261113-162059_c2_team_dev` | C2 with hybrid search |

Judge calibration: 26 hand-labelled outputs (13 per calibration set), judge
`google/gemini-3.1-flash-lite`, raw agreement 26/26, Cohen's kappa 1.00:

    python tests/evals/judge/calibrate.py score tests/evals/evidence/runs/20261111-185914_c2_team_dev tests/evals/evidence/runs/20261113-144116_c1_single_agent_dev
