# c2_team on dev

Model meta-llama/llama-3.3-70b-instruct | commit 3fa917f | started 2026-11-14T14:43:48 | caches: llm, risk_extraction | search mode: hybrid

| Metric | c2_team |
|---|---|
| Task success | **15/21** |
|   code checks passed | 18/21 |
|   judged cases | 13 |
|   numeric | 8/8 |
|   comparison | 3/3 |
|   narrative | 2/4 |
|   risk_change | 1/4 |
|   missing | 1/2 |
| Errors (crash / budget) | 0 |
| Timeouts | 0 |
| Replans | 5 |
| Latency p50 (s) | 23.6 |
| Latency p95 (s) | 59.0 |
| LLM calls / case | 14.1 |
| Tokens / case | 27,287 |
| Tokens total | 573,022 |
| Cost / case (USD) | 0.0149 |
| Cost total (USD) | 0.3138 (21/21 known) |
| Expected tool called | 19/19 |
| Evidence retrieved | 2/4 |
| Figures verified vs XBRL | 26/26 (100%) |
| Calculations in sandbox | 1/4 |
| Critic: passed first draft | 12/21 |
| Critic: passed after revision | 1/21 |
| Critic: still failing (flagged) | 8/21 |
| Critic revisions / case | 0.81 |
| Critic open issues by type | claim 2, number 22 |
| Success per repeat | r1: 15 |

## Failed cases

- `t03` r1 (narrative): must_include, judge
- `t04` r1 (narrative): must_include, judge
- `k01` r1 (risk_change): judge
- `k03` r1 (risk_change): judge
- `k04` r1 (risk_change): judge
- `m02` r1 (missing): refusal

