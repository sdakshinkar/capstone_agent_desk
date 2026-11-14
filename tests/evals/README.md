# Agent Desk evals

Evaluation harness for the capstone's L13 requirements: a golden set split into dev and
held-out cases, code checks first, an LLM judge from a different model family calibrated with
Cohen's kappa, and experiment E1 (C0 single prompt vs C1 single agent vs C2 team).

**Credits:** only commands marked 💳 call OpenRouter, and they do nothing without `--yes`.
Everything else is free.

## Layout

| Path | What it is |
|---|---|
| `truth/build_xbrl_truth.py` → `truth/xbrl_truth.json` | Expected numbers computed by code from SEC Company Facts (10 companies, FY2023–2026). Restated values are all accepted. |
| `cases/dev/golden.jsonl` | 21 dev cases: tune prompts against these only. |
| `cases/heldout/golden.jsonl` | 41 held-out cases: run once for the final comparison. |
| `cases/loader.py` | Loads and validates the golden set (ids, truth exists, no group in both splits). |
| `checkers/` | Code checks: numbers at written precision, fiscal years, must-include facts, evidence retrieved, risk-label coverage, passage ids exist, refusals, tool use. |
| `harness/` | Recorder (tool calls, tokens, cost, budget stop) and the three systems. |
| `configs/` | One YAML per experiment: system, limits, caches, prices. |
| `run_eval.py` | 💳 Runs a split against a config and saves answers, trajectories and grades. |
| `report.py` | Summary or side-by-side comparison of saved runs. |
| `judge/` | 💳 `judge.py` (Qwen 2.5 72B) and `calibrate.py` (kappa against your labels). |
| `run_retrieval_eval.py` | Recall@k and MRR of the FAISS index on 32 questions (no LLM). |
| `runs/` | Saved runs (git-ignored; copy the ones you report into the write-up). |

## Golden set (62 cases)

| Type | Dev | Held-out | Checked by |
|---|---|---|---|
| numeric | 8 | 15 | code against XBRL |
| comparison | 3 | 7 | code (numbers, growth) + judge (direction, fiscal-year alignment) |
| narrative | 4 | 8 | code (must-include facts) + judge (claims supported by retrieved passages) |
| risk_change | 4 | 6 | code (label coverage, passage ids) + judge |
| missing | 2 | 5 | code (refusal, partial facts) + judge (no invented figures) |

Cases are grouped (`group`) so variants of one scenario stay in one split. Expected numbers are
never written in the cases: a case names company, year and metric, and the checker looks the
value up in the truth file. The risk-change labels were drafted from a diff of each pair's Item
1A passages and confirmed with keyword counts in each year. **A person should review them**
(the brief says "labelled by hand").

## Cost controls

- Plan-only by default: every command lists what it would run until you add `--yes`.
- Per-case limits in the config (tokens, LLM calls, time) stop a run *before* the next model
  call; a run-wide token budget stops before the next case.
- The LLM cache (`data/eval_llm_cache.sqlite`) makes re-running an unchanged case free; it is
  switched off for `--repeat` runs, which must measure real variation.
- Risk extraction is cached per company-year (`data/risk_cache/`) by default;
  the config's `risk_extraction` setting enables or disables it for an eval run.
- Answers are saved, so checkers, reports and the judge re-run without calling the agent.
- The judge skips numeric cases and, by default, cases that already failed code checks.

## Recommended order

```bat
:: free
python tests\evals\truth\build_xbrl_truth.py
python tests\evals\run_retrieval_eval.py
python -m pytest

:: 💳 1. smoke: 3 cases, measure real cost per case
python tests\evals\run_eval.py --config c2_team --split dev --limit 3 --yes
:: 💳 2. one risk case (the most expensive type)
python tests\evals\run_eval.py --config c2_team --split dev --ids k04 --yes
:: 💳 3. the rest of dev
python tests\evals\run_eval.py --config c2_team --split dev --yes
:: 💳 4. judge every dev case (including failures) and label 20+ by hand
python tests\evals\judge\judge.py tests\evals\runs\<dev run> --all --yes
python tests\evals\judge\calibrate.py export tests\evals\runs\<dev run>
python tests\evals\judge\calibrate.py score tests\evals\runs\<dev run>
:: 💳 5. final: held-out, 3 repeats, all three systems (E1)
python tests\evals\run_eval.py --config c2_team --split heldout --repeat 3 --yes
python tests\evals\run_eval.py --config c1_single_agent --split heldout --repeat 3 --yes
python tests\evals\run_eval.py --config c0_single_prompt --split heldout --repeat 3 --yes
python tests\evals\judge\judge.py tests\evals\runs\<each held-out run> --yes
python tests\evals\report.py tests\evals\runs\<c0> tests\evals\runs\<c1> tests\evals\runs\<c2>
```

If you change anything after looking at held-out results, those cases count as dev from then
on; say so in the report.

## Not covered yet

E2 (defences), E3 (Reflexion lessons) and E4 (critic loop and table-aware parsing) need
guardrails, the improvement loop and the compliance critic. Policy violations, attack success
and false blocks are reported once E2 exists. FinanceBench's open sample is an optional
external retrieval check that can reuse `run_retrieval_eval.py`.
