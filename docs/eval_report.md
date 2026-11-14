# Agent Desk — Evaluation Report

*2026-11-14. Development-split runs (Section 4) and one held-out run per system (Section 5).*

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
| **Human pass** | 16 | 0 |
| **Human fail** | 1 | 9 |

Raw agreement 25/26; **Cohen's kappa = 0.92** (almost perfect agreement). The labeller first
marked all 26 the same way as the judge (kappa 1.00) and on review relabelled one answer, C2's
Mastercard risk comparison (k04), as a fail; the judge had passed it for reporting the new
trade-policy and tariff risk. That is the only disagreement. The judge adds information the code checks miss: in
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
were re-judged; no comparison verdict on the 26 hand-labelled outputs changed. This change
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

### 4.1 E1, final dev runs (hybrid search, C2 with critic, C1 with calculator, company-name fix)

| Metric | C0 single prompt | C1 single agent | C2 team |
|---|---|---|---|
| **Task success (code + judge)** | **7/21** | **14/21** | **15/21** |
| code checks passed | 7/21 | 16/21 | 19/21 |
| numeric | 2/8 | 7/8 | 8/8 |
| comparison | 0/3 | 1/3 | 2/3 |
| narrative | 3/4 | 2/4 | 3/4 |
| risk change | 0/4 | 2/4 | 1/4 |
| missing data | 2/2 | 2/2 | 1/2 |
| Errors / timeouts | 0 / 0 | 0 / 0 | 0 / 0 |
| Figures verified vs XBRL | 11/15 (73%) | 12/12 (100%) | **26/26 (100%)** |
| Calculations in sandbox | — | 4/4 | 1/4 |
| Evidence sentence retrieved (narrative) | 3/4 | 1/4 | 3/4 |
| *Latency p50 / p95 (s)* ¹ | 4.4 / 15.8 | 9.2 / 26.6 | 23.6 / 59.0 |
| *LLM calls per case* ¹ | 1.0 | 5.7 | 14.1 |
| *Tokens per case* ¹ | 1,614 | 27,107 | 27,287 |
| *Cost per case (USD)* ¹ | 0.0010 | 0.0172 | 0.0149 |

Quality rows: `20261114-154010_c0_single_prompt_dev`, `20261114-154057_c1_single_agent_dev`,
`20261114-154349_c2_team_dev` (commit dd0444a, after the company-name fix).
¹ Latency, calls, tokens and cost come from the previous full runs of the same configurations
(`20261114-143717_c0_single_prompt_dev`, `20261114-143941_c1_single_agent_dev`,
`20261114-144348_c2_team_dev`, commit 3fa917f), whose model calls were almost all fresh. The final
runs replayed most calls from the LLM cache (unchanged prompts give identical calls), so their
timings are not real and their reported cost (USD 0.62) overstates the USD 0.43 actually spent.

**Reading the table.**

- **Tools account for most of the gain.** C0 cannot look up XBRL facts and answers from a fixed
  set of passages; it doubled from 3 to 7 with the better retrieval, all of the gain on text
  questions, but it gets only 2 of 8 numbers right.
- **On this single dev run the team is one case ahead of the single agent (15 vs 14).** C2 passes
  more code checks (19 vs 16); the judge failed four of C2's answers (three risk changes, and one
  growth answer that cited a calculation id that did not exist) and two of C1's (both risk
  changes). C2 is cheaper per case than C1 (USD 0.015 vs 0.017: C1's single context grows long)
  but about 2.6× slower at the median.
- **Both tool-using systems now state only verified figures** (C1 12/12, C2 26/26; C0 73%). C1
  gives fewer figures per answer, and with the calculator it computed all four of its ratios in the
  sandbox, while C2's quant worker did so in one of four.
- **Twenty-one cases and one run cannot separate a difference of a few cases from run-to-run
  noise** (Section 7): between the two final runs C1 lost a numeric case (n07) and gained the
  company-name cases. Section 5 gives the held-out result.

**Fresh repeats of C2 (no caches).** C2 was run twice more on dev with the LLM cache and the
risk-extraction cache off, so every model call and every risk extraction was fresh
(`20261114-160508_c2_team_dev`, commit 555205b):

| | Repeat 1 | Repeat 2 |
|---|---|---|
| **Task success (code + judge)** | **15/21** | **16/21** |
| numeric / comparison / missing | 8/8, 3/3, 2/2 | 8/8, 3/3, 2/2 |
| narrative | 2/4 | 3/4 |
| **risk change** | **0/4** | **0/4** |

Across both repeats: latency p50 21.4 s, p95 196.4 s; 17.5 LLM calls and USD 0.0205 per case (all
fresh calls); figures verified 54/54; sandbox used in 2 of 8 calculation cases; critic 25 first-pass,
3 after revision, 14 still failing. Outside risk change, C2 answered 15/17 and 16/17.

No risk-change case passed: most risk comparisons ended with a provider error ("400 – Provider
returned error") from OpenRouter, so these results reflect tool errors rather than the risk worker's
answers. Cached runs reused earlier successful risk extractions.

### 4.2 Compliance critic (C2)

| Outcome | Notes |
|---|---|
| Passed on the first draft | 12/21 |
| Passed after revision | 1/21 |
| Still failing after two revisions (returned with a warning) | 8/21 |
| Revisions per case | 0.81 |
| Open issues at the end, by type | 26 number, 4 claim |

The critic's open issues are almost all about **citation form, not wrong values**: all 26 figures
in C2's numeric and comparison answers matched XBRL. Two patterns account for most of them:

- **Figures from filing text are rejected.** Employee counts (166,000; 1,556,000) come from a
  filing passage, so the writer cites `[P1]`; the critic's number rule accepts only a fact (`F`) or
  a calculation (`D`) id after a figure.
- **Figures without an id**, and ids the register never issued. In c03 the note cited `D1` for a
  growth rate that the quant worker had computed itself, without the sandbox; the judge failed that
  answer for citing a source that does not exist.

Revisions rarely help (1 of 9 failing drafts was fixed). As configured, the critic flags 38% of dev
notes, mostly for citation form, and adds latency (two extra rounds on 9 cases). There was no wrong figure
on this split for it to stop.

### 4.3 Numbers you can trust (signature challenge A)

- C2: 26/26 figures verified, and every figure carries an evidence id that links it to an XBRL fact
  or a sandbox calculation (the critic enforces the presence and value of the id).
- The quant worker still computes most ratios itself: `run_python` was called in **1 of 4** margin
  and growth cases. The brief's rule "do not calculate numbers inside the LLM" is requested in the
  prompt but not enforced; the critic accepts a ratio only with a `D` id, which is why such ratios
  end up flagged, or cited to a `D` id that does not exist, instead of being computed in the
  sandbox.
- C1, with the same calculator and the same instruction, used it in 4 of 4 calculation cases.

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

**From retrieval to answers.** The retrieval eval always passes the indexed company name, so it did
not reveal that agents call the tools with other names: in the first final runs the researcher
searched with `company="jpmorgan chase"`, which matched no indexed company (`jpmorgan`), and the
First Republic question (t03) failed in both C1 and C2. After the company-name fix (Section 6) t03
passes in both, and C1's JPMorgan risk comparison (k03) runs instead of reporting that JPMorgan has
no filings.

### 4.5 Before the retrieval changes and the critic (history)

The first dev runs (2026-11-11 to 11-13: semantic search, old chunks, no critic, C1 without the
calculator) gave C0 3/21, C1 12/21 and C2 18/21 (code + judge), with C2 at 15.3 s median latency and
USD 0.0135 per case. Several things changed at once between those runs and the final ones —
retrieval, chunking, the critic, the writer's citation rules and C1's tools — so the difference for
C2 (18 → 15) cannot be attributed to any one of them; Section 6 lists the cases that changed and
why. These runs are in the evidence folder and the experiment log.

## 5. Results — held-out split

All three systems were run **once** on the 41 held-out cases (Microsoft, Alphabet, Meta, NVIDIA,
Bank of America, Goldman Sachs, plus an uncovered company), with the final configuration: hybrid
search, C2 with the compliance critic, C1 with all six tools, judged as in Section 3. Each system was
run once, so differences of a few cases are within run-to-run noise (Section 7). No change was made to the system or the
checkers after seeing these results.

| Metric | C0 single prompt | C1 single agent | C2 team |
|---|---|---|---|
| **Task success (code + judge)** | **12/41** | **25/41** | **25/41** |
| code checks passed | 12/41 | 27/41 | 29/41 |
| numeric | 2/15 | 14/15 | 13/15 |
| comparison | 0/7 | 3/7 | 4/7 |
| narrative | 5/8 | 3/8 | 4/8 |
| risk change | 0/6 | 1/6 | 1/6 |
| missing data | 5/5 | 4/5 | 3/5 |
| Errors / timeouts | 0 / 0 | 3 / 0 | 0 / 0 |
| Replans | — | — | 11 |
| Latency p50 / p95 (s) | 4.2 / 9.4 | 6.5 / 79.2 | 25.8 / 96.9 |
| LLM calls per case | 1.0 | 5.0 | 15.6 |
| Tokens per case | 1,627 | 22,127 | 34,184 |
| Cost per case (USD) | 0.0010 | 0.0143 | 0.0220 |
| Figures verified vs XBRL | 15/28 (54%) | 31/33 (94%) | 56/58 (97%) |
| Calculations in sandbox | — | 6/7 | 1/7 |
| Critic: first pass / after revision / still failing | — | — | 25 / 8 / 8 |

Runs: `20261114-171327_c0_single_prompt_heldout`, `20261114-171719_c1_single_agent_heldout`,
`20261114-175641_c2_team_heldout` (commit 215131a). The held-out questions had never been run, so
model calls were fresh. A network outage between the test machine and OpenRouter during the run
made 9 C1 cases and 19 C2 cases fail on their first model call with "Connection error" before any
work was done; those records were removed and the same cases re-run with `--resume`. C1's three
errors are risk comparisons that ended with "400 – Provider returned error" from OpenRouter; they
are counted as failures.

**What the held-out run shows.**

- **Tools account for most of the gain, as on dev.** C0 answers text and "not available"
  questions from its fixed passages but gets 2 of 15 numbers right; C1 and C2 get 14 and 13.
- **The team is not more successful than the single agent on held-out (25 vs 25),** at about 1.5×
  the cost per case and 4× the median latency. C2 passes two more code checks (29 vs 27), and the
  judge then fails four of its code-passing answers (three risk changes and one comparison) against
  two of C1's.
- **Both tool-using systems state almost only verified figures** (C2 97%, C1 94%; C0 54%). Every C2
  figure also carries an evidence id linking it to an XBRL fact or a calculation; the critic
  revised 8 of 41 notes successfully and left 8 flagged, all for number citations.
- **Risk-change questions remain the weakest type** (1 of 6 for both). Where a comparison ran, the
  answers missed most of the labelled changes (for example the January 2025 AI Diffusion rule for
  NVIDIA, or Goldman Sachs reducing its climate-risk discussion).
- **Narrative questions on employee counts and specific figures** (Microsoft 223,000 employees,
  Meta 78,865, Alphabet's USD 72.22 billion) failed in both agents: the answers gave another
  figure or said the information could not be found.
- **Missing-data handling is weaker in C2 (3/5):** for Tesla (not covered) C2 did not say the
  company is outside the coverage, and for a partly answerable question it returned an internal
  error message instead of the available Meta revenue.

**E1 answer, on this evidence.** Giving the model tools is clearly worth its cost (12 → 25 of 41).
The team of agents, in its current form, does not improve task success over a single agent with the
same tools; what it adds is traceability (an evidence id on every figure, checked by the critic)
at a higher cost and latency.

## 6. Failure analysis and changes made because of the evaluation

| Finding | Evidence | Action |
|---|---|---|
| **Company names not normalised in tool calls** | C2 t03: `search_filing(company="jpmorgan chase")` returned nothing (index name `jpmorgan`); C1 k03: `compare_risk_factors` with the same name returned an error and C1 gave up | **Fixed** (`agent_desk/companies.py`): names, legal forms and tickers map to the indexed names in the search filter, filing lookup, risk passage ids and risk cache. Re-measured in the final runs: t03 now passes in C1 and C2 (both still call the tools with "jpmorgan chase"); C1's k03 now runs but is failed by the judge on content |
| **Planner picked the wrong year** | C2 t04 asks about the end of 2025; the research lead planned fiscal 2024, and the answer reported 2024 figures | Reported to the agents owner |
| **Critic rejects figures cited to passages** | 8/21 notes still failing, 22 open "number" issues, while all 26 figures matched XBRL | Reported to the critic's owner |
| Calculation cited but never made | C2 c03: the note cited `[D1]` for revenue growth the quant worker computed itself; no calculation was recorded | Failed by the judge |
| Refusal check misses a labelled substitution | C2 m02 (2025→2026, no 2026 filing) answered with an explicit 2024→2025 substitution; the judge passed it, the refusal patterns did not | Counted as a code-check failure; the judge passed it |
| C1 wrote tool calls as plain text | First C1 run: all four risk cases ended after one call with the reply `compare_risk_factors(company="apple", …)` | One prompt rule added to C1; risk cases 0/4 → 3/4 |
| C1 lacked the calculator | Arithmetic slips on dev (Apple 2024 margin 31.6% for 31.51%; Mastercard 55.4% for 55.32%) | `run_python` added to C1; it then used it in 3 of 4 calculation cases |
| A gold label was wrong | k02 expected "no material change" for Amazon 2024→2025; the FY2025 filing adds "automation, artificial intelligence, and machine learning" to the newer-activities risk | Label corrected; the case notes record why |
| Checker too strict on truncation | C2 wrote Apple's 31.97% margin as 31.9% with the right conclusion | Truncated percentages now match; whole numbers must still round |
| Markdown bullets read as minus signs | "- 11.16%" parsed as −11.16% | Parser fixed; no result changed |
| Judge failed a correct comparison for not mentioning different year-ends | C2 c01 (final run) | Comparison rubric clarified; no hand-labelled verdict changed (Section 3) |
| Keyword check passes wrong risk answers | Answers covering the label keywords but missing or inventing changes (C2 k01, k03, k04 in the final run) | Caught by the judge |
| Retrieval missed exact-term questions | Recall@5 0.44 at the start; First Republic never found | Hybrid search, reranker and re-chunking: 0.81 |
| Provider drift | One C1 run answered "Your input is not sufficient…" on the first call for 7 cases, while some of its calls were billed at USD 0.18 instead of 0.71 per million tokens | Run excluded; bad replies removed from the LLM cache |

## 7. Threats to validity

- **Single runs.** Re-running C1 on dev gave the same score with different cases failing, and two
  fresh C2 repeats gave 15 and 16. Differences of a few cases, on dev (C2 15 vs C1 14) and on
  held-out (25 vs 25), are within that noise; held-out was run once per system.
- **Network outage during the held-out run.** 28 cases (9 C1, 19 C2) failed on their first call
  with a connection error and were re-run; the re-runs are ordinary single runs of the same cases.
- **Several changes between the first and final runs** (retrieval, chunking, critic, writer rules,
  C1's tools), so before/after differences are not attributed to a single change.
- **Changes made after seeing dev results.** The company-name fix and the comparison-rubric
  clarification (Section 3) were both made after dev runs, and the final dev runs were repeated
  with the fix. Both are dev-side changes made before any held-out run.
- **Risk results and the cache.** Cached runs reuse earlier risk extractions; in fresh runs most
  risk comparisons ended with provider errors (Section 4.1).
- **Cached re-runs.** The final dev runs replayed most model calls from the LLM cache; their
  quality numbers are valid single runs, but latency and cost are taken from the previous, fresh
  runs (Section 4.1).
- **Provider drift.** OpenRouter can serve the model from different providers, some at reduced
  precision, and chooses per request; we observed one run with markedly different behaviour and
  price. Runs used OpenRouter's default routing.
- **Judge calibration predates the critic.** Final C2 answers carry evidence ids and, when the
  critic fails, a warning block; the 26 calibration outputs had neither.
- **Who wrote the cases.** The golden set and the C1 prompt fix came from the evaluation side; the
  cases were drafted with AI assistance and reviewed by the team, and C2 was never tuned on held-out
  cases.
- **Checker limits.** A number is not tied to the year it is stated for; risk coverage is keyword
  based (mitigated by the judge); refusals are detected with patterns (m02); figures that are
  differences of two values are counted as unverified.
- **Retrieval eval scope.** 32 cases, eight of them Microsoft, dev only, always with the correct
  company filter — which is why it did not reveal the company-name problem.
- **Cache effects.** The final dev runs used the LLM and risk caches; identical model calls replay
  their recorded cost. Repeat runs disable both caches.

## 8. Cost of evaluation

All runs to date, including smoke tests and the judge: about **USD 4.95** of OpenRouter usage
(account usage, not the per-run reported costs, which count cached calls again). The two rounds of
final dev runs with their judging cost about USD 0.74 and USD 0.45, and the two fresh C2 repeats
with judging about USD 0.87, and the held-out run of the three systems with judging about
USD 1.55. Retrieval evaluation, regrading and calibration scoring use no LLM.

## 9. Reproducing

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
