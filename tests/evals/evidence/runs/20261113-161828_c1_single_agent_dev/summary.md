# c1_single_agent on dev

Model meta-llama/llama-3.3-70b-instruct | commit 1d90096 | started 2026-11-13T16:18:28 | caches: llm, risk_extraction | search mode: hybrid

| Metric | c1_single_agent |
|---|---|
| Task success | **9/21** |
|   code checks passed | 9/21 |
|   judged cases | 0 |
|   numeric | 3/8 |
|   comparison | 1/3 |
|   narrative | 1/4 |
|   risk_change | 3/4 |
|   missing | 1/2 |
| Errors (crash / budget) | 0 |
| Timeouts | 0 |
| Replans | 0 |
| Latency p50 (s) | 5.4 |
| Latency p95 (s) | 14.7 |
| LLM calls / case | 2.8 |
| Tokens / case | 6,614 |
| Tokens total | 138,884 |
| Cost / case (USD) | 0.0030 |
| Cost total (USD) | 0.0629 (21/21 known) |
| Expected tool called | 12/19 |
| Evidence retrieved | 1/2 |
| Figures verified vs XBRL | 7/7 (100%) |
| Calculations in sandbox | n/a |
| Success per repeat | r1: 9 |

## Failed cases

- `n02` r1 (numeric): facts, years
- `n03` r1 (numeric): facts, years
- `n05` r1 (numeric): facts
- `n07` r1 (numeric): facts
- `n08` r1 (numeric): facts, years
- `c01` r1 (comparison): facts, years
- `c03` r1 (comparison): facts, years, derived
- `t02` r1 (narrative): must_include
- `t03` r1 (narrative): must_include
- `t04` r1 (narrative): must_include
- `k03` r1 (risk_change): risk_labels
- `m02` r1 (missing): refusal
