# c0_single_prompt on dev

Model meta-llama/llama-3.3-70b-instruct | commit dd0444a | started 2026-11-14T15:40:10 | caches: llm, risk_extraction | search mode: hybrid

| Metric | c0_single_prompt |
|---|---|
| Task success | **7/21** |
|   code checks passed | 7/21 |
|   judged cases | 13 |
|   numeric | 2/8 |
|   comparison | 0/3 |
|   narrative | 3/4 |
|   risk_change | 0/4 |
|   missing | 2/2 |
| Errors (crash / budget) | 0 |
| Timeouts | 0 |
| Replans | 0 |
| Latency p50 (s) | 1.3 |
| Latency p95 (s) | 3.1 |
| LLM calls / case | 1.0 |
| Tokens / case | 1,614 |
| Tokens total | 33,901 |
| Cost / case (USD) | 0.0010 |
| Cost total (USD) | 0.0203 (21/21 known) |
| Expected tool called | n/a |
| Evidence retrieved | 3/4 |
| Figures verified vs XBRL | 11/15 (73%) |
| Calculations in sandbox | n/a |
| Critic: passed first draft | n/a |
| Critic: passed after revision | n/a |
| Critic: still failing (flagged) | n/a |
| Critic revisions / case | n/a |
| Critic open issues by type | n/a |
| Success per repeat | r1: 7 |

## Failed cases

- `n01` r1 (numeric): facts
- `n02` r1 (numeric): facts, years
- `n03` r1 (numeric): facts
- `n06` r1 (numeric): facts
- `n07` r1 (numeric): facts
- `n08` r1 (numeric): facts
- `c01` r1 (comparison): facts, judge
- `c02` r1 (comparison): facts, judge
- `c03` r1 (comparison): facts, judge
- `t03` r1 (narrative): must_include, judge
- `k01` r1 (risk_change): risk_labels, judge
- `k02` r1 (risk_change): risk_labels, judge
- `k03` r1 (risk_change): risk_labels, judge
- `k04` r1 (risk_change): risk_labels, judge

