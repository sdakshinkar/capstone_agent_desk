# Agent Desk — Evaluation Report

*Status: 2026-11-14. Final development-split runs are complete (Section 4). The held-out comparison
(three repeats per system) has not been run, and its tables are marked **TBD**. Experiment E2
(defences and red team) is reported separately by the security owner. E3 and E4 are not run
(Section 7).*

All numbers can be reproduced from `tests/evals/evidence/` (answers, trajectories, grades, judge
verdicts and summaries of every cited run). The run-by-run history is in `docs/experiment_log.md`.

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
| **C1** `c1_single_agent` | One ReAct agent | Which tools to call, when to stop | All six team tools: `search_filing`, `list_edgar_companies`, `list_company_facts`, `get_company_fact`, `compare_risk_factors`, `run_python` |
| **C2** `c2_team` | Research lead (plan) → supervisor (routing, replan up to 2×) → researcher / quant / risk-diff workers → writer → **compliance critic** (up to 2 revisions) | Plan, routing, briefs, replans, each worker's tool use, the writer's draft, the critic's claim and wording judgements | Researcher: `search_filing`; quant: EDGAR tools + `run_python`; risk-diff: `compare_risk_factors` |

All three use `meta-llama/llama-3.3-70b-instruct` through OpenRouter (default provider routing),
the same per-case budget (300,000 tokens, 80 LLM calls, 900 s) and, in the final runs, the same
retrieval: **hybrid search** (BM25 + embeddings fused with RRF, then a cross-encoder reranker) over
the per-Item chunk index. Each configuration is one YAML file in `tests/evals/configs/`; the search
mode is set for the whole run with `--search-mode hybrid`.

**C2 as evaluated.** In C2 every tool records what it returns in a per-question *evidence
register* and hands back a short id — `F` for an XBRL fact, `D` for a sandbox calculation, `P` (or a
risk-passage id) for a filing passage. The writer must put the id after every figure and claim. The
compliance critic then checks every figure against the register by code, every passage-backed
claim with an LLM judge (`openai/gpt-4o-mini`, a different family from the writer), and the wording
for advice or promised returns; a failing draft goes back to the writer at most twice, after which
the note is returned with a visible "did not pass" warning. The eval runs the team graph unattended
(no plan-approval pause), with a fresh register per case and the application's step limit (50).
Parallel fan-out and memory are not part of the system yet.

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
Microsoft, Alphabet, Meta, NVIDIA, Bank of America and Goldman Sachs (plus Tesla as an uncovered
company). Related variants share a `group`, and a validator rejects any group that appears in both
splits, so held-out results measure companies the system was never tuned on.

**Gold answers stay out of reach.** Cases name a fact rather than its value; values live in
`tests/evals/truth/xbrl_truth.json`. No agent tool reads `tests/`.

**Numeric truth from XBRL.** `truth/build_xbrl_truth.py` (built 2026-11-11) takes, for each
company, year and metric (revenue, operating income, net income, R&D, diluted EPS, total assets),
the full-year 10-K value from SEC Company Facts, with a fixed concept order (for example
`RevenueFromContractWithCustomerExcludingAssessedTax`, then `Revenues`, then
`RevenuesNetOfInterestExpense` for banks). Fiscal year means the year the period ends (Microsoft's
FY2025 ends June 2025, NVIDIA's January 2025). Margins are computed in code. When a later 10-K
restated a value, every reported version is accepted (Bank of America's 2024 net income: $26.97B or
$27.13B). Each value records its concept, period and accession number.

**Risk labels.** The ten risk-change cases (ten company-year pairs, as the brief asks) were drafted
with AI assistance from keyword counts in each Item 1A and then reviewed and confirmed by the team.
One label was corrected against the filings (k02, Section 6).

## 3. How answers are graded

**Code first** (`tests/evals/checkers/`), immediately after each answer:

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

Diagnostics are reported but never fail a case: expected tool called; whether the gold evidence
sentence was among the passages retrieved; **share of figures verified against XBRL** (dollar and
percent figures in numeric and comparison answers that match a reported value or a margin/growth
computed from one); **whether margin and growth cases used the `run_python` sandbox**; and, for C2,
the **compliance critic's verdict**.

**LLM judge for what code cannot decide** (`tests/evals/judge/`). `google/gemini-3.1-flash-lite`
(temperature 0), a different family from the agents, grades narrative, comparison, risk-change and
missing cases against a rubric built from the gold labels: claims supported by the retrieved
passages; the comparison's direction right and, where the case notes say the companies' fiscal
years end in different months, the periods not presented as the same months; most labelled risk
changes reported and none invented; unavailable data declined without invented figures. Numeric
cases are never judged. The judge can only turn a code pass into a failure. **Task success = code
checks passed and not failed by the judge.**

### Judge calibration

The judge was checked against **26 outputs labelled by hand** (13 from C1, 13 from C2, dev split,
all four judged types), labelled without seeing the judge's verdicts.

| | Judge pass | Judge fail |
|---|---|---|
| **Human pass** | 17 | 0 |
| **Human fail** | 0 | 9 |

Raw agreement 26/26; **Cohen's kappa = 1.00**. The judge adds information the code checks miss: in
the calibration set it failed four risk-change answers that passed the keyword check, and the human
labels agreed in all four (one missed the large rise in tariff language and stated no risks were
added; one reported a change in Brazilian regulation that is not in the labels).

**Rubric clarification (2026-11-14).** In the final C2 run the judge failed c01 (Apple vs Amazon
margins) because the answer did not *mention* that the two fiscal years end in different months,
although it named each company's own "fiscal 2025" correctly and the same kind of answer had passed
before. The comparison rubric was reworded to state the rule explicitly: naming each company's own
fiscal year is correct; fail only an answer that says or implies the figures cover the same months,
and only when the case notes say the year-ends differ. A first rewording dropped that last
condition and wrongly failed a correct JPMorgan/Mastercard answer (both years end on 31 December);
it was corrected before any result was reported. All comparison answers in the five judged runs
were re-judged, and agreement with the 26 hand labels is unchanged (26/26, kappa 1.00). This change
was made after seeing dev results and only affects dev cases.

Caveats: 26 items and one labeller leave wide uncertainty around a perfect score; the judged cases
are mostly clear-cut; calibration used outputs produced before the critic, which carry no evidence
ids. The judge occasionally reasons from its own knowledge cutoff (one verdict on C1 c03 said
fiscal 2025 data could not exist "as of the current date"); that answer had already failed the code
checks, so no result changed. The judge model was switched from `qwen/qwen-2.5-72b-instruct` to Gemini on 2026-11-13, before
any run had been judged, because the account's OpenRouter guardrail blocked Qwen's only provider.

## 4. Results — development split

Dev results guided changes to the checkers, the C1 prompt and retrieval, so they are not an
unbiased estimate; the held-out run (Section 5) is. Each system was run once per configuration.

### 4.1 E1, final dev runs (hybrid search, C2 with critic, C1 with calculator)

| Metric | C0 single prompt | C1 single agent | C2 team |
|---|---|---|---|
| **Task success (code + judge)** | **7/21** | **14/21** | **15/21** |
| code checks passed | 7/21 | 15/21 | 18/21 |
| numeric | 2/8 | 8/8 | 8/8 |
| comparison | 0/3 | 1/3 | 3/3 |
| narrative | 3/4 | 1/4 | 2/4 |
| risk change | 0/4 | 2/4 | 1/4 |
| missing data | 2/2 | 2/2 | 1/2 |
| Errors / timeouts | 0 / 0 | 0 / 0 | 0 / 0 |
| Replans | — | — | 5 |
| Latency p50 / p95 (s) | 4.4 / 15.8 | 9.2 / 26.6 | 23.6 / 59.0 |
| LLM calls per case | 1.0 | 5.7 | 14.1 |
| Tokens per case | 1,614 | 27,107 | 27,287 |
| Cost per case (USD) | 0.0010 | 0.0172 | 0.0149 |
| Cost, 21 cases (USD) | 0.020 | 0.362 | 0.314 |
| Figures verified vs XBRL | 11/15 (73%) | 13/15 (87%) | **26/26 (100%)** |
| Calculations in sandbox | — | 3/4 | 1/4 |
| Evidence sentence retrieved (narrative) | 3/4 | 1/4 | 2/4 |

Runs: `20261114-143717_c0_single_prompt_dev`, `20261114-143941_c1_single_agent_dev`,
`20261114-144348_c2_team_dev` (commit 3fa917f). Policy-violation, attack-success and false-block
counts belong to E2.

**Reading the table.**

- **Tools account for most of the gain.** C0 cannot look up XBRL facts and answers from a fixed
  set of passages; it doubled from 3 to 7 with the better retrieval, all of the gain on text
  questions, but it gets only 2 of 8 numbers right.
- **On this single dev run the team is one case ahead of the single agent (15 vs 14).** C2
  passes more code checks (18 vs 15); the judge failed three of its risk-change answers and one of
  C1's. C2 is cheaper per case than C1 here (USD 0.015 vs 0.017: C1's single context grows long)
  but about 2.6× slower at the median.
- **C2's numbers are the most trustworthy.** Every figure it stated matched XBRL (26/26), against
  87% for C1 and 73% for C0. For an analyst note, where one wrong number undermines the whole note
  (the brief), this is the clearest advantage of the team.
- **Twenty-one cases and one run cannot separate a difference of a few cases from run-to-run
  noise** (Section 8). The E1 conclusion waits for the held-out repeats.

### 4.2 Compliance critic (C2)

| Outcome | Notes |
|---|---|
| Passed on the first draft | 12/21 |
| Passed after revision | 1/21 |
| Still failing after two revisions (returned with a warning) | 8/21 |
| Revisions per case | 0.81 |
| Open issues at the end, by type | 22 number, 2 claim |

The critic's open issues are almost all about **citation form, not wrong values**: all 26 figures
in C2's numeric and comparison answers matched XBRL. Two patterns account for most of them:

- **Figures from filing text are rejected.** Employee counts (166,000; 1,556,000) come from a
  filing passage, so the writer cites `[P1]`; the critic's number rule accepts only a fact (`F`) or
  a calculation (`D`) id after a figure.
- **Figures without an id**, and an id the register never issued (`D1` in one note).

Revisions rarely help (1 of 9 failing drafts was fixed). As configured, the critic therefore flags
38% of dev notes, mostly for citation form, and adds latency (two extra rounds on 9 cases). The
critic did not stop any wrong figure on this split because there were none to stop; whether it
catches planted wrong numbers (the brief's demo) is not measured here.

### 4.3 Numbers you can trust (signature challenge A)

- C2: 26/26 figures verified, and every figure now carries an evidence id that links it to an XBRL
  fact or a sandbox calculation (the critic enforces the presence and value of the id).
- The quant worker still computes most ratios itself: `run_python` was called in **1 of 4** margin
  and growth cases (the same rate as before the critic). The brief's rule "do not calculate numbers
  inside the LLM" is requested in the prompt but not enforced; the critic accepts a ratio only with
  a `D` id, which is why some ratios end up flagged rather than computed in the sandbox.
- C1, which has had the calculator since 2026-11-13, used it in 3 of 4 calculation cases.

### 4.4 Retrieval

The filing search was evaluated on its own with 32 query/evidence pairs
(`tests/evals/dev/retrieval.jsonl`, no LLM): a case is a hit if the exact 10-K sentence is in the
top five chunks returned with the case's company and year filter.

| Mode | Initial index and search | Final (per-Item chunks, stemming, reranker) |
|---|---|---|
| semantic (MiniLM, FAISS) | 0.44 Recall@5, MRR 0.36 | 0.47, MRR 0.36 |
| keyword (BM25) | 0.50, MRR 0.37 | 0.72, MRR 0.50 |
| **hybrid** | 0.53, MRR 0.36 | **0.81, MRR 0.64** |

Three changes produced the gain: a cross-encoder reranker over the top 30 fused results (hybrid
0.53 → 0.75 on the old index), a BM25 tokenizer with stopwords and light stemming, and re-chunking
that joins each Item's paragraphs before splitting (57,808 chunks, many a lone header or table row,
became 21,186 chunks of median 833 characters; hybrid 0.75 → 0.81). The JPMorgan First Republic
passage that every earlier mode missed is now found (rank 5 hybrid, rank 3 keyword).

**From retrieval to answers.** Better retrieval did not translate fully into agent answers. C2 still
failed the First Republic question (t03) because the researcher called `search_filing` with
`company="jpmorgan chase"`, which matches no indexed company (`jpmorgan`), so the filtered search
returned nothing; the retrieval eval uses the indexed name and does not see this.

### 4.5 Before the retrieval changes and the critic (history)

The first dev runs (2026-11-11 to 11-13: semantic search, old chunks, no critic, C1 without the
calculator) gave C0 3/21, C1 12/21 and C2 18/21 (code + judge), with C2 at 15.3 s median latency and
USD 0.0135 per case. Several things changed at once between those runs and the final ones —
retrieval, chunking, the critic, the writer's citation rules and C1's tools — so the difference for
C2 (18 → 15) cannot be attributed to any one of them; Section 6 lists the cases that changed and
why. These runs are in the evidence folder and the experiment log.

## 5. Results — held-out split (TBD)

Planned: C0, C1 and C2 on all 41 held-out cases, **three repeats each**, LLM and risk caches off,
hybrid search, judged as above. Estimated cost USD 5–6 with the critic and reranker.

| Metric | C0 | C1 | C2 |
|---|---|---|---|
| Task success, mean of 3 (range) | TBD | TBD | TBD |
| by type (numeric / comparison / narrative / risk / missing) | TBD | TBD | TBD |
| Errors / timeouts | TBD | TBD | TBD |
| Latency p50 / p95 (s) | TBD | TBD | TBD |
| Cost per case (USD) | TBD | TBD | TBD |
| Figures verified vs XBRL | TBD | TBD | TBD |
| Critic: first-pass / revised / still failing | — | — | TBD |

Any change made after seeing held-out results will be reported, and the affected cases treated as
development cases.

## 6. Failure analysis and changes made because of the evaluation

| Finding | Evidence | Action |
|---|---|---|
| **Company names not normalised in tool calls** | C2 t03: `search_filing(company="jpmorgan chase")` returns nothing (index name `jpmorgan`); C1 k03: `compare_risk_factors` with the same name returns an error and C1 gives up | **Fixed after the final runs** (`agent_desk/companies.py`): names, legal forms and tickers map to the indexed names in the search filter, filing lookup, risk passage ids and risk cache. C2's exact t03 search now returns the $588 million First Republic passage. Not yet re-measured in an agent run |
| **Planner picked the wrong year** | C2 t04 asks about the end of 2025; the research lead planned fiscal 2024, and the answer reported 2024 figures | Not fixed; candidate lesson for the improvement loop |
| **Critic rejects figures cited to passages** | 8/21 notes still failing, 22 open "number" issues, while all 26 figures matched XBRL | Reported to the critic's owner; proposed: allow a passage id after a figure that comes from filing text |
| Refusal check misses a labelled substitution | C2 m02 (2025→2026, no 2026 filing) answered with an explicit 2024→2025 substitution; the judge passed it, the refusal patterns did not | Checker limitation; not changed |
| C1 wrote tool calls as plain text | First C1 run: all four risk cases ended after one call with the reply `compare_risk_factors(company="apple", …)` | One prompt rule added to C1; risk cases 0/4 → 3/4 |
| C1 lacked the calculator | Arithmetic slips on dev (Apple 2024 margin 31.6% for 31.51%; Mastercard 55.4% for 55.32%) | `run_python` added to C1; it then used it in 3 of 4 calculation cases |
| A gold label was wrong | k02 expected "no material change" for Amazon 2024→2025; the FY2025 filing adds "automation, artificial intelligence, and machine learning" to the newer-activities risk | Label corrected; the case notes record why |
| Checker too strict on truncation | C2 wrote Apple's 31.97% margin as 31.9% with the right conclusion | Truncated percentages now match; whole numbers must still round |
| Markdown bullets read as minus signs | "- 11.16%" parsed as −11.16% | Parser fixed; no result changed |
| Judge failed a correct comparison for not mentioning different year-ends | C2 c01 (final run) | Comparison rubric clarified; kappa unchanged (Section 3) |
| Keyword check passes wrong risk answers | Answers covering the label keywords but missing or inventing changes (C2 k01, k03, k04 in the final run) | Caught by the judge |
| Retrieval missed exact-term questions | Recall@5 0.44 at the start; First Republic never found | Hybrid search, reranker and re-chunking: 0.81 |
| Provider drift | One C1 run answered "Your input is not sufficient…" on the first call for 7 cases, while some of its calls were billed at USD 0.18 instead of 0.71 per million tokens | Run excluded; bad replies removed from the LLM cache |

## 7. Not yet evaluated

- **Held-out comparison, three repeats** — Section 5.
- **E2, defences on and off** — reported by the security owner.
- **E3, lessons before and after** — the Reflexion loop and playbook are not built.
- **E4, critic on/off and table-aware vs plain-text parsing** — the critic exists, but the team
  decided to evaluate C2 with the critic always on, so the on/off comparison is not run; table-aware
  parsing is not built (tables are flattened into rows).
- **FinanceBench external check** — its questions concern FY2015–2022 filings, which are not in
  the index.
- **Traces and dashboard** — every eval run's trajectory is stored in `results.jsonl`; LangSmith
  tracing is available when `LANGSMITH_API_KEY` is set; the Grafana dashboard is owned by deployment.

## 8. Threats to validity

- **Single runs on dev.** Re-running C1 earlier gave the same score with different cases failing.
  Dev differences of a few cases (including C2 15 vs C1 14) are within noise; the held-out repeats
  address this.
- **Several changes between the first and final runs** (retrieval, chunking, critic, writer rules,
  C1's tools), so before/after differences are not attributed to a single change.
- **Changes made after the final dev runs.** The company-name fix (which should help t03 and C1's
  k03) is not reflected in the final dev numbers; the comparison rubric was clarified after seeing
  them (Section 3). Both are dev-side changes made before any held-out run.
- **Provider drift.** OpenRouter can serve the model from different providers, some at reduced
  precision, and chooses per request; we observed one run with markedly different behaviour and
  price. We did not pin a provider.
- **Judge calibration predates the critic.** Final C2 answers carry evidence ids and, when the
  critic fails, a warning block; the judge was not re-calibrated on such answers.
- **Who wrote the cases.** The golden set and the C1 prompt fix came from the evaluation side; the
  cases were drafted with AI assistance and reviewed by the team, and C2 was never tuned on held-out
  cases. The domain lead should confirm the held-out set, as the brief asks.
- **Checker limits.** A number is not tied to the year it is stated for; risk coverage is keyword
  based (mitigated by the judge); refusals are detected with patterns (m02); figures that are
  differences of two values are counted as unverified.
- **Retrieval eval scope.** 32 cases, eight of them Microsoft, dev only, always with the correct
  company filter — which is why it did not reveal the company-name problem.
- **Cache effects.** The final dev runs used the LLM and risk caches; identical model calls replay
  their recorded cost. Repeat runs disable both caches.

## 9. Cost of evaluation

All runs to date, including smoke tests and the judge: about **USD 2.05** of OpenRouter usage
(costs reported by OpenRouter per call), of which the final dev runs and their judging were about
USD 0.74. Retrieval evaluation, regrading and calibration scoring use no LLM.

## 10. Reproducing

```
python -m pytest tests/unit_tests                                            # 209 tests, no network
python tests/evals/run_retrieval_eval.py --mode all --k 5                    # retrieval, no LLM
python tests/evals/run_eval.py --config c2_team --split dev --search-mode hybrid   # plan only; add --yes
python tests/evals/run_eval.py --regrade <run dir>                           # re-check saved answers
python tests/evals/judge/judge.py <run dir> --all --yes                      # judge
python tests/evals/judge/calibrate.py score <run dir> [<run dir> ...]
python tests/evals/report.py <run dir> <run dir> <run dir>                   # side-by-side table
```

The index must be built first (`create_all_embeddings()` in `src/agent_desk/utils/create_embeddings.py`).
