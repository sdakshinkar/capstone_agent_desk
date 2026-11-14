# c2_team on dev

Model meta-llama/llama-3.3-70b-instruct | commit 1d90096 | started 2026-11-13T16:20:59 | caches: llm, risk_extraction | search mode: hybrid

| Metric | c2_team |
|---|---|
| Task success | **18/21** |
|   code checks passed | 18/21 |
|   judged cases | 0 |
|   numeric | 8/8 |
|   comparison | 3/3 |
|   narrative | 1/4 |
|   risk_change | 4/4 |
|   missing | 2/2 |
| Errors (crash / budget) | 0 |
| Timeouts | 0 |
| Replans | 8 |
| Latency p50 (s) | 13.8 |
| Latency p95 (s) | 146.4 |
| LLM calls / case | 14.5 |
| Tokens / case | 27,567 |
| Tokens total | 578,913 |
| Cost / case (USD) | 0.0134 |
| Cost total (USD) | 0.2807 (21/21 known) |
| Expected tool called | 19/19 |
| Evidence retrieved | 2/4 |
| Figures verified vs XBRL | 25/25 (100%) |
| Calculations in sandbox | 1/4 |
| Success per repeat | r1: 18 |

## Failed cases

- `t02` r1 (narrative): must_include
- `t03` r1 (narrative): must_include
- `t04` r1 (narrative): must_include
