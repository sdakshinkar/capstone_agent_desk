# c2_team on dev

Model meta-llama/llama-3.3-70b-instruct | commit 555205b | started 2026-11-14T16:05:08 | caches: none | search mode: hybrid

| Metric | c2_team |
|---|---|
| Task success | **31/42** |
|   code checks passed | 31/42 |
|   judged cases | 26 |
|   numeric | 16/16 |
|   comparison | 6/6 |
|   narrative | 5/8 |
|   risk_change | 0/8 |
|   missing | 4/4 |
| Errors (crash / budget) | 0 |
| Timeouts | 0 |
| Replans | 20 |
| Latency p50 (s) | 21.4 |
| Latency p95 (s) | 196.4 |
| LLM calls / case | 17.5 |
| Tokens / case | 35,866 |
| Tokens total | 1,506,358 |
| Cost / case (USD) | 0.0205 |
| Cost total (USD) | 0.8594 (42/42 known) |
| Expected tool called | 36/38 |
| Evidence retrieved | 5/8 |
| Figures verified vs XBRL | 54/54 (100%) |
| Calculations in sandbox | 2/8 |
| Critic: passed first draft | 25/42 |
| Critic: passed after revision | 3/42 |
| Critic: still failing (flagged) | 14/42 |
| Critic revisions / case | 0.76 |
| Critic open issues by type | claim 2, number 31 |
| Success per repeat | r1: 15, r2: 16 |

## Failed cases

- `t02` r1 (narrative): must_include, judge
- `t04` r1 (narrative): must_include, judge
- `k01` r1 (risk_change): risk_labels, judge
- `k02` r1 (risk_change): risk_labels, judge
- `k03` r1 (risk_change): risk_labels, judge
- `k04` r1 (risk_change): risk_labels, judge
- `t04` r2 (narrative): must_include, judge
- `k01` r2 (risk_change): risk_labels, judge
- `k02` r2 (risk_change): risk_labels, judge
- `k03` r2 (risk_change): risk_labels, judge
- `k04` r2 (risk_change): risk_labels, judge

