# c0_single_prompt on dev

Model meta-llama/llama-3.3-70b-instruct | commit 2d4f0f0 | started 2026-11-13T13:49:23 | caches: llm, risk_extraction | search mode: default

| Metric | c0_single_prompt |
|---|---|
| Task success | **3/21** |
|   code checks passed | 3/21 |
|   judged cases | 13 |
|   numeric | 1/8 |
|   comparison | 0/3 |
|   narrative | 0/4 |
|   risk_change | 0/4 |
|   missing | 2/2 |
| Errors (crash / budget) | 0 |
| Timeouts | 0 |
| Replans | 0 |
| Latency p50 (s) | 1.4 |
| Latency p95 (s) | 2.6 |
| LLM calls / case | 1.0 |
| Tokens / case | 833 |
| Tokens total | 17,488 |
| Cost / case (USD) | 0.0005 |
| Cost total (USD) | 0.0111 (21/21 known) |
| Expected tool called | n/a |
| Evidence retrieved | 0/4 |
| Figures verified vs XBRL | 2/7 (29%) |
| Calculations in sandbox | n/a |
| Success per repeat | r1: 3 |

## Failed cases

- `n01` r1 (numeric): facts, years
- `n02` r1 (numeric): facts, years
- `n03` r1 (numeric): facts, years
- `n04` r1 (numeric): facts
- `n06` r1 (numeric): facts
- `n07` r1 (numeric): facts, years
- `n08` r1 (numeric): facts, years
- `c01` r1 (comparison): facts, judge
- `c02` r1 (comparison): facts, judge
- `c03` r1 (comparison): facts, years, derived
- `t01` r1 (narrative): must_include, judge
- `t02` r1 (narrative): must_include
- `t03` r1 (narrative): must_include, judge
- `t04` r1 (narrative): must_include
- `k01` r1 (risk_change): risk_labels, judge
- `k02` r1 (risk_change): risk_labels, judge
- `k03` r1 (risk_change): risk_labels, judge
- `k04` r1 (risk_change): risk_labels, judge
