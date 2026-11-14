# c2_team on dev

Model meta-llama/llama-3.3-70b-instruct | commit dd0444a | started 2026-11-14T15:43:49 | caches: llm, risk_extraction | search mode: hybrid

| Metric | c2_team |
|---|---|
| Task success | **15/21** |
|   code checks passed | 19/21 |
|   judged cases | 13 |
|   numeric | 8/8 |
|   comparison | 2/3 |
|   narrative | 3/4 |
|   risk_change | 1/4 |
|   missing | 1/2 |
| Errors (crash / budget) | 0 |
| Timeouts | 0 |
| Replans | 2 |
| Latency p50 (s) | 6.1 |
| Latency p95 (s) | 35.5 |
| LLM calls / case | 13.4 |
| Tokens / case | 21,944 |
| Tokens total | 460,831 |
| Cost / case (USD) | 0.0130 |
| Cost total (USD) | 0.2737 (21/21 known) |
| Expected tool called | 19/19 |
| Evidence retrieved | 3/4 |
| Figures verified vs XBRL | 26/26 (100%) |
| Calculations in sandbox | 1/4 |
| Critic: passed first draft | 12/21 |
| Critic: passed after revision | 1/21 |
| Critic: still failing (flagged) | 8/21 |
| Critic revisions / case | 0.81 |
| Critic open issues by type | claim 4, number 26 |
| Success per repeat | r1: 15 |

## Failed cases

- `c03` r1 (comparison): judge
- `t04` r1 (narrative): must_include, judge
- `k01` r1 (risk_change): judge
- `k03` r1 (risk_change): judge
- `k04` r1 (risk_change): judge
- `m02` r1 (missing): refusal

