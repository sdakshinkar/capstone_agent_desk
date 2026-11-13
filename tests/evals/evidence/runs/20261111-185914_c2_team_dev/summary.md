# c2_team on dev

Model meta-llama/llama-3.3-70b-instruct | commit ad60d2e | started 2026-11-11T18:59:14 | caches: llm, risk_extraction | search mode: default

| Metric | c2_team |
|---|---|
| Task success | **18/21** |
|   code checks passed | 20/21 |
|   judged cases | 13 |
|   numeric | 8/8 |
|   comparison | 3/3 |
|   narrative | 3/4 |
|   risk_change | 2/4 |
|   missing | 2/2 |
| Errors (crash / budget) | 0 |
| Timeouts | 0 |
| Replans | 5 |
| Latency p50 (s) | 15.3 |
| Latency p95 (s) | 132.4 |
| LLM calls / case | 11.5 |
| Tokens / case | 26,209 |
| Tokens total | 550,390 |
| Cost / case (USD) | 0.0135 |
| Cost total (USD) | 0.2833 (21/21 known) |
| Expected tool called | 19/19 |
| Evidence retrieved | 3/4 |
| Figures verified vs XBRL | 25/25 (100%) |
| Calculations in sandbox | 0/4 |
| Success per repeat | r1: 18 |

## Failed cases

- `t03` r1 (narrative): must_include, judge
- `k01` r1 (risk_change): judge
- `k03` r1 (risk_change): judge
