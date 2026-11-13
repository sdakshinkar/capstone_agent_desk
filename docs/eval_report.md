# Agent Desk — Evaluation Report

*Status: draft, 2026-11-13. Development-split results are final for this draft; the held-out
comparison (three repeats per system) has not been run yet, and its tables are marked **TBD**.
Experiment E2 (defences and red team) is reported separately by the security owner. E3 and E4
depend on components that are not built yet (Section 7).*

All numbers below can be reproduced from `tests/evals/evidence/` (answers, trajectories, grades
and summaries of every cited run). The run-by-run history is in `docs/experiment_log.md`.

---

## 1. What we evaluate

Agent Desk answers an equity analyst's questions about the 10-K filings of ten US companies in two
sectors — technology (Microsoft, Apple, Alphabet, Amazon, Meta, NVIDIA) and finance (JPMorgan
Chase, Bank of America, Goldman Sachs, Mastercard) — for fiscal years 2023–2025 (2026 where
filed). It must return correct reported numbers, correct ratios, faithful text findings and
risk-factor changes, and it must say when data does not exist instead of inventing it.

The evaluation answers two questions from the brief:

- **Can the numbers be trusted?** (signature challenge A) — every figure checked against SEC
  XBRL data by code.
- **Does the agent team justify its cost?** (experiment E1) — the team compared with a
  single-prompt pipeline and a single agent on the same questions, model and budget.

### Systems compared (E1)

| Config | System | Decisions made by the model | Tools |
|---|---|---|---|
| **C0** `c0_single_prompt` | Fixed pipeline: code finds the companies named in the question, retrieves 6 passages per company, one LLM call answers | None (one answer call) | None |
| **C1** `c1_single_agent` | One ReAct agent | Which tools to call, when to stop | `search_filing`, `list_edgar_companies`, `list_company_facts`, `get_company_fact`, `compare_risk_factors`, and since 2026-11-13 `run_python` (the dev runs below predate it) |
| **C2** `c2_team` | Research lead (plan) → supervisor (routing, replan up to 2×) → researcher / quant / risk-diff workers → writer | Plan, routing, briefs, replans, each worker's tool use | Researcher: `search_filing`; quant: the four EDGAR tools + `run_python` sandbox; risk-diff: `compare_risk_factors` |

All three use `meta-llama/llama-3.3-70b-instruct` through OpenRouter (default provider routing)
and the same per-case budget: 300,000 tokens, 80 LLM calls, 900 s. Each configuration is one
YAML file in `tests/evals/configs/`; there are no experiment branches.

The C2 evaluated here is the team graph in `agents/workflow.py` run unattended (no plan-approval
pause). It does not yet have the brief's parallel fan-out, compliance critic or memory; results
describe the system as built.

## 2. Golden set

**62 cases**, written before the agent was run on them, in JSONL
(`tests/evals/cases/{dev,heldout}/golden.jsonl`).

| Type | Dev | Held-out | What a case specifies |
|---|---|---|---|
| numeric | 8 | 15 | the (company, year, metric) facts the answer must state |
| comparison | 3 | 7 | facts, plus a derived value (growth) or the company that should come out higher |
| narrative | 4 | 8 | phrases the answer must contain, and the exact 10-K sentence that supports them |
| risk_change | 4 | 6 | hand labels of what was added, removed or changed in Item 1A between two years |
| missing | 2 | 5 | data that does not exist (fiscal 2027, a 2026 filing not yet out, an uncovered company); the answer must say so |
| **Total** | **21** | **41** | |

**Split by company.** Dev covers Apple, Amazon, JPMorgan and Mastercard; held-out covers
Microsoft, Alphabet, Meta, NVIDIA, Bank of America, Goldman Sachs (plus Tesla as an uncovered
company). Related variants share a `group`, and a validator rejects any group that appears in both
splits. Held-out results therefore measure companies the system was never tuned on.

**Gold answers stay out of reach.** Cases name a fact rather than its value; values live in
`tests/evals/truth/xbrl_truth.json`. No agent tool reads `tests/`.

**Numeric truth from XBRL.** `truth/build_xbrl_truth.py` (built 2026-11-11) takes, for each
company, year and metric (revenue, operating income, net income, R&D, diluted EPS, total assets),
the full-year 10-K value from SEC Company Facts, with a fixed concept order (for example
`RevenueFromContractWithCustomerExcludingAssessedTax`, then `Revenues`, then
`RevenuesNetOfInterestExpense` for banks). Fiscal year means the year the period ends, so
Microsoft's FY2025 ends June 2025 and NVIDIA's ends January 2025. Margins are computed in code.
When a later 10-K restated a value, every reported version is accepted (Bank of America's 2024 net
income: $26.97B or $27.13B). Each value records its concept, period and accession number.

**Risk labels.** The ten risk-change cases (ten company-year pairs, as the brief asks) were drafted
with AI assistance from keyword counts in each Item 1A and then reviewed and confirmed by the team.
One label was corrected after review of the filings (k02, see Section 6).

## 3. How answers are graded

**Code first** (`tests/evals/checkers/`). Every answer is graded by code immediately after it is
produced:

| Check | Pass rule |
|---|---|
| facts | every expected value appears at the precision written ("$416.2 billion" matches $416,161M; "$4.5 billion" does not match $4.22B); percentages may be rounded or truncated at one or more decimals |
| derived | growth computed by code from the truth appears in the answer |
| years | every expected fiscal year is named |
| must_include | every required phrase group is present |
| risk_labels | at least half of the labelled changes are covered (by keywords), and the answer does not say the comparison was impossible |
| refusal | the answer states the data is unavailable (pattern list) |
| passage_ids | every cited risk passage id exists in that filing |
| health | no crash, no budget stop, no timeout (these count as failures) |

Diagnostics are reported but never fail a case: expected tool called, whether the gold evidence
sentence was among the passages retrieved, **share of figures verified against XBRL**, and
**whether margin and growth cases used the `run_python` sandbox**.

**LLM judge for what code cannot decide** (`tests/evals/judge/`). A model from a different family
than the agents — `google/gemini-3.1-flash-lite`, temperature 0 — grades narrative, comparison,
risk-change and missing cases against a rubric built from the gold labels: every claim supported by
the retrieved passages; the comparison's direction right; most labelled risk changes reported and
none invented; unavailable data declined without invented figures. Numeric cases are never judged.
The judge can only turn a code pass into a failure, never the reverse. Task success = code checks
passed and not failed by the judge.

### Judge calibration

The judge was checked against **26 outputs labelled by hand** (13 from C1, 13 from C2, dev split,
covering all four judged types). Labels were entered without seeing the judge's verdicts.

| | Judge pass | Judge fail |
|---|---|---|
| **Human pass** | 17 | 0 |
| **Human fail** | 0 | 9 |

Raw agreement 26/26; **Cohen's kappa = 1.00**.

The judge adds information the code checks miss: it failed four risk-change answers that passed
the keyword check (C2 k01, C2 k03, C1 k01, C1 k04), and the human labels agreed in all four.
Examples: C2's Apple answer stated that no new risks were added and missed the large rise in
tariff and trade-restriction language; C1's Mastercard answer reported a change in Brazilian
regulation that is not in the labels.

Caveats: 26 items and a single labeller leave wide uncertainty around a perfect score; the judged
cases are mostly clear-cut; calibration used dev outputs from two systems and has not been
repeated on held-out answers. The judge model was switched from `qwen/qwen-2.5-72b-instruct` to
Gemini on 2026-11-13, before any run had been judged, because the account's OpenRouter guardrail
blocked Qwen's only provider.

## 4. Results — development split (single run)

Dev results guided changes to the checkers and to the C1 prompt, so they are not an unbiased
estimate; the held-out run in Section 5 is.

### E1 on dev

| Metric | C0 single prompt | C1 single agent | C2 team |
|---|---|---|---|
| **Task success (code + judge)** | **3/21** | **12/21** | **18/21** |
| code checks passed | 3/21 | 14/21 | 20/21 |
| numeric | 1/8 | 6/8 | 8/8 |
| comparison | 0/3 | 2/3 | 3/3 |
| narrative | 0/4 | 1/4 | 3/4 |
| risk change | 0/4 | 1/4 | 2/4 |
| missing data | 2/2 | 2/2 | 2/2 |
| Errors / timeouts | 0 / 0 | 0 / 0 | 0 / 0 |
| Replans | — | — | 5 |
| Latency p50 / p95 (s) | 1.4 / 2.6 | 6.3 / 16.6 | 15.3 / 132.4 |
| LLM calls per case | 1.0 | 4.4 | 11.5 |
| Tokens per case | 833 | 14,202 | 26,209 |
| Cost per case (USD) | 0.0005 | 0.0099 | 0.0135 |
| Cost, 21 cases (USD) | 0.011 | 0.207 | 0.283 |
| Figures verified vs XBRL | 2/7 (29%) | 19/20 (95%) | 25/25 (100%) |
| Evidence sentence retrieved (narrative) | 0/4 | 1/4 | 3/4 |

Runs: `20261113-134923_c0_single_prompt_dev`, `20261113-144116_c1_single_agent_dev`,
`20261111-185914_c2_team_dev`. Policy-violation, attack-success and false-block counts belong to
E2 and are not in this table.

**Reading the table.** Tools account for most of the gain: C0, which cannot look up XBRL facts or
search beyond six fixed passages per company, mostly (and correctly) answered that the information
was not in its passages. The team then adds six more correct answers than C1 for 36% more cost per
case and about 2.4× the median latency; its p95 latency is dominated by risk comparisons (one took
441 s). On this split the team's extra cost looks justified for accuracy-critical notes, but a
single run of 21 cases cannot separate a six-case gap from run-to-run noise with confidence; see
Section 6.

### Numbers you can trust (signature challenge A)

- **Every figure C2 stated in numeric and comparison answers matched an XBRL value or a margin
  or growth computed from them (25/25).** C1 stated one wrong figure (Mastercard's 2024 operating
  margin as 55.4%; the value is 55.32%), an arithmetic slip without a calculator.
- **The quant worker rarely used its sandbox.** After `run_python` was added to the quant worker,
  it was called in only **1 of 4** margin and growth cases (run `20261112-183020_c2_team_dev`);
  the other three margins were computed by the model and happened to be right. The brief's rule
  "do not calculate numbers inside the LLM" is therefore not yet enforced by the system — only
  requested in the prompt.
- After the merge, C2 still passed all 11 numeric and comparison dev cases.

### Retrieval

The filing search was evaluated on its own with 32 query/evidence pairs
(`tests/evals/dev/retrieval.jsonl`, no LLM): a case is a hit if the exact 10-K sentence is in the
top five chunks.

| Mode | Recall@5 | MRR@5 |
|---|---|---|
| semantic (MiniLM embeddings, FAISS) | 14/32 = 0.44 | 0.36 |
| keyword (BM25) | 16/32 = 0.50 | 0.37 |
| **hybrid** (RRF of both) | **17/32 = 0.53** | 0.36 |

Semantic Recall@50 is 0.78, so many misses are ranking failures rather than absent passages; a
reranker (not yet built) targets exactly that. Hybrid search recovered five cases (segment
questions, NVIDIA export controls and customer concentration) and lost one; MRR did not improve.
The passage for JPMorgan's $588 million First Republic gain is missed by all three modes, and it is
the cause of C2's only narrative failure (t03).

**Hybrid search inside the agents (dev).** With hybrid search forced for every system, C0 rose
from 3 to 4 (two employee-count questions now answered, one lost), and C2 stayed at 18/21 on code
checks. C2's two narrative changes were not retrieval failures: in both, the search returned the
right passage and the answer was still wrong (an invented employee figure; a plan that searched
fiscal 2024 instead of 2025). The C1 hybrid run is excluded: seven of its cases received an
unrelated reply on the very first model call ("Your input is not sufficient…"), before any search,
and some of its cases were billed at about USD 0.18 per million tokens instead of the USD 0.71 of
every earlier run, which points to OpenRouter routing those requests to a different provider.

## 5. Results — held-out split (TBD)

Planned: C0, C1 and C2 on all 41 held-out cases, **three repeats each** with the LLM cache off,
judged as above. Estimated cost USD 3.50–4.50.

| Metric | C0 | C1 | C2 |
|---|---|---|---|
| Task success, mean of 3 (range) | TBD | TBD | TBD |
| by type (numeric / comparison / narrative / risk / missing) | TBD | TBD | TBD |
| Errors / timeouts | TBD | TBD | TBD |
| Latency p50 / p95 (s) | TBD | TBD | TBD |
| Cost per case (USD) | TBD | TBD | TBD |
| Figures verified vs XBRL | TBD | TBD | TBD |
| Calculations in sandbox | — | — | TBD |

Before this run: fix the search mode (semantic or hybrid) for all three systems, disable the
risk-extraction cache, and make no further prompt changes. C1 has had the `run_python` tool since
2026-11-13, so all held-out runs use the same tools. Any change made after seeing
held-out results will be reported, and the affected cases treated as development cases.

## 6. Failure analysis and changes made because of the evaluation

| Finding | Evidence | Action |
|---|---|---|
| C1 wrote tool calls as plain text | First C1 run: all four risk cases ended after one call with the reply `compare_risk_factors(company="apple", …)`; the ReAct loop treats text as the final answer | One prompt rule added to C1; risk cases went from 0/4 to 3/4. Only the baseline changed |
| A gold label was wrong | k02 expected "no material change" for Amazon 2024→2025; the agent reported a change, and the FY2025 filing indeed adds "automation, artificial intelligence, and machine learning" to the risk about newer activities | Label corrected; the case notes record why |
| Checker too strict on truncation | C2 wrote Apple's 31.97% margin as 31.9% with the right conclusion | Percentages truncated at one or more decimals now match; whole numbers must still round |
| Markdown bullets read as minus signs | "- 11.16%" parsed as −11.16% | Parser fixed; no pass/fail result changed |
| Keyword check passes wrong risk answers | Four answers covered the label keywords but missed or invented changes | The judge catches these (Section 3) |
| Model arithmetic | C1: Apple 2024 margin given as 31.6% (true 31.51%), Mastercard as 55.4% (55.32%) | Supports routing calculations to the sandbox; C2's quant worker uses it only 1 time in 4. C1 did not have the sandbox on dev and has been given it for held-out |
| Giving up after one failed lookup | C1 looked for a `Revenue` concept for Mastercard, did not find it, and answered "not available"; asked for "jpmorgan chase", it received the valid names in the error and did not retry | Recorded; not fixed (baseline) |
| Retrieval miss | t03 / r021: the First Republic passage is never in the top results | Hybrid search did not fix it; reranking is the next step |

## 7. Not yet evaluated

- **Held-out comparison, three repeats** — Section 5.
- **E2, defences on and off** — reported by the security owner.
- **E3, lessons before and after** — the Reflexion loop and playbook are not built.
- **E4, critic on/off and table-aware vs plain-text parsing** — neither the compliance critic nor
  table-aware parsing exists; the filings are parsed as text with tables flattened into rows.
- **FinanceBench external check** — its questions concern FY2015–2022 filings, which are not in
  our index; using it requires indexing those filings separately.
- **Traces and dashboard** — every run's trajectory is stored in `results.jsonl`; LangSmith or
  Langfuse traces and the Grafana dashboard are owned by deployment.

## 8. Threats to validity

- **Provider drift.** OpenRouter can serve the same model ID from different providers, some at
  reduced precision, and chooses per request. We observed a run whose price per token and
  behaviour changed markedly. Runs on different days may not be comparable; we did not pin a
  provider.
- **Single runs on dev.** Re-running C1 gave the same score (14/21 on code) with different cases
  failing. Dev differences of a few cases are within noise; the held-out repeats address this.
- **C1 lacked the calculator on dev.** `run_python` was added to C2's quant worker after C1 was
  built, so the C1 dev runs had five of the team's six tools, which favours C2 on calculation
  cases (C1's two arithmetic slips in Section 6 happened without it). C1 has had all six tools
  since 2026-11-13; the held-out comparison uses the same tools for C1 and C2.
- **Who wrote the cases.** The golden set and the C1 prompt fix came from the evaluation side, and
  the cases were drafted with AI assistance and reviewed by the team. The C2 team was never tuned on
  held-out cases. The brief's separation (the person tuning the agent does not write held-out
  cases) should be confirmed by the domain lead's review of the held-out set.
- **Checker limits.** A number is not tied to the year it is stated for; risk coverage is keyword
  based (mitigated by the judge); refusals are detected with patterns; figures that are differences
  of two values (for example a gap between two margins) are counted as unverified.
- **Small retrieval set.** 32 cases, eight of them Microsoft, dev only.
- **Cache effects.** Cached model calls replay their recorded cost, so cached re-runs overstate
  spend; the risk-extraction cache makes repeated risk comparisons more alike than fresh ones.
  Repeat runs disable the LLM cache; the risk cache should be disabled for the held-out repeats.
- **Eval step limit.** The harness runs C2 with a graph recursion limit of 30; the application
  uses 40. No dev case reached the limit.

## 9. Cost of evaluation

All runs to date, including smoke tests and the judge: about **USD 1.30** of OpenRouter usage
(costs reported by OpenRouter per call). Retrieval evaluation, regrading and calibration scoring
use no LLM.

## 10. Reproducing

```
python -m pytest tests/unit_tests                                    # 167 tests, no network
python tests/evals/run_retrieval_eval.py --mode all --k 5            # retrieval, no LLM
python tests/evals/run_eval.py --config c2_team --split dev          # plan only; add --yes to run
python tests/evals/run_eval.py --regrade <run dir>                   # re-check saved answers, no LLM
python tests/evals/judge/judge.py <run dir> --all --yes              # judge
python tests/evals/judge/calibrate.py score <run dir> [<run dir> ...]
python tests/evals/report.py <run dir> <run dir> <run dir>           # side-by-side table
```
