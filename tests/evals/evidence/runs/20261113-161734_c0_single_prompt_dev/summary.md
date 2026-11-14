# c0_single_prompt on dev

Model meta-llama/llama-3.3-70b-instruct | commit 1d90096 | started 2026-11-13T16:17:34 | caches: llm, risk_extraction | search mode: hybrid

| Metric | c0_single_prompt |
|---|---|
| Task success | **4/21** |
|   code checks passed | 4/21 |
|   judged cases | 0 |
|   numeric | 0/8 |
|   comparison | 0/3 |
|   narrative | 2/4 |
|   risk_change | 0/4 |
|   missing | 2/2 |
| Errors (crash / budget) | 0 |
| Timeouts | 0 |
| Replans | 0 |
| Latency p50 (s) | 1.8 |
| Latency p95 (s) | 6.2 |
| LLM calls / case | 1.0 |
| Tokens / case | 810 |
| Tokens total | 17,010 |
| Cost / case (USD) | 0.0004 |
| Cost total (USD) | 0.0086 (21/21 known) |
| Expected tool called | n/a |
| Evidence retrieved | 2/4 |
| Figures verified vs XBRL | 1/4 (25%) |
| Calculations in sandbox | n/a |
| Success per repeat | r1: 4 |

## Failed cases

- `n01` r1 (numeric): facts, years
- `n02` r1 (numeric): facts, years
- `n03` r1 (numeric): facts, years
- `n04` r1 (numeric): facts
- `n05` r1 (numeric): facts, years
- `n06` r1 (numeric): facts
- `n07` r1 (numeric): facts, years
- `n08` r1 (numeric): facts
- `c01` r1 (comparison): facts, years
- `c02` r1 (comparison): facts
- `c03` r1 (comparison): facts, years, derived
- `t01` r1 (narrative): must_include
- `t03` r1 (narrative): must_include
- `k01` r1 (risk_change): risk_labels
- `k02` r1 (risk_change): risk_labels
- `k03` r1 (risk_change): risk_labels
- `k04` r1 (risk_change): risk_labels
