# c1_single_agent on heldout

Model meta-llama/llama-3.3-70b-instruct | commit 215131a | started 2026-11-14T17:17:19 | caches: llm, risk_extraction | search mode: hybrid

| Metric | c1_single_agent |
|---|---|
| Task success | **25/41** |
|   code checks passed | 27/41 |
|   judged cases | 26 |
|   numeric | 14/15 |
|   comparison | 3/7 |
|   narrative | 3/8 |
|   risk_change | 1/6 |
|   missing | 4/5 |
| Errors (crash / budget) | 3 |
| Timeouts | 0 |
| Replans | 0 |
| Latency p50 (s) | 6.5 |
| Latency p95 (s) | 79.2 |
| LLM calls / case | 5.0 |
| Tokens / case | 22,127 |
| Tokens total | 907,190 |
| Cost / case (USD) | 0.0143 |
| Cost total (USD) | 0.5860 (41/41 known) |
| Expected tool called | 31/36 |
| Evidence retrieved | 2/8 |
| Figures verified vs XBRL | 31/33 (94%) |
| Calculations in sandbox | 6/7 |
| Critic: passed first draft | n/a |
| Critic: passed after revision | n/a |
| Critic: still failing (flagged) | n/a |
| Critic revisions / case | n/a |
| Critic open issues by type | n/a |
| Success per repeat | r1: 25 |

## Failed cases

- `n22` r1 (numeric): facts
- `c04` r1 (comparison): years, judge
- `c06` r1 (comparison): facts, derived, judge
- `c08` r1 (comparison): facts, judge
- `c10` r1 (comparison): facts, judge
- `t05` r1 (narrative): must_include, judge
- `t07` r1 (narrative): must_include, judge
- `t08` r1 (narrative): must_include, judge
- `t09` r1 (narrative): must_include, judge
- `t12` r1 (narrative): must_include
- `k05` r1 (risk_change): OpenAIInvalidRequestError: Error code: 400 - Provider returned error
- `k06` r1 (risk_change): OpenAIInvalidRequestError: Error code: 400 - Provider returned error
- `k07` r1 (risk_change): judge
- `k08` r1 (risk_change): judge
- `k10` r1 (risk_change): OpenAIInvalidRequestError: Error code: 400 - Provider returned error
- `m05` r1 (missing): refusal, judge

