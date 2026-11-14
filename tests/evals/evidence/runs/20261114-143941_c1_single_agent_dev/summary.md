# c1_single_agent on dev

Model meta-llama/llama-3.3-70b-instruct | commit 3fa917f | started 2026-11-14T14:39:41 | caches: llm, risk_extraction | search mode: hybrid

| Metric | c1_single_agent |
|---|---|
| Task success | **14/21** |
|   code checks passed | 15/21 |
|   judged cases | 13 |
|   numeric | 8/8 |
|   comparison | 1/3 |
|   narrative | 1/4 |
|   risk_change | 2/4 |
|   missing | 2/2 |
| Errors (crash / budget) | 0 |
| Timeouts | 0 |
| Replans | 0 |
| Latency p50 (s) | 9.2 |
| Latency p95 (s) | 26.6 |
| LLM calls / case | 5.7 |
| Tokens / case | 27,107 |
| Tokens total | 569,257 |
| Cost / case (USD) | 0.0172 |
| Cost total (USD) | 0.3622 (21/21 known) |
| Expected tool called | 17/19 |
| Evidence retrieved | 1/4 |
| Figures verified vs XBRL | 13/15 (87%) |
| Calculations in sandbox | 3/4 |
| Critic: passed first draft | n/a |
| Critic: passed after revision | n/a |
| Critic: still failing (flagged) | n/a |
| Critic revisions / case | n/a |
| Critic open issues by type | n/a |
| Success per repeat | r1: 14 |

## Failed cases

- `c01` r1 (comparison): facts
- `c03` r1 (comparison): facts, judge
- `t02` r1 (narrative): must_include, judge
- `t03` r1 (narrative): must_include, judge
- `t04` r1 (narrative): must_include
- `k01` r1 (risk_change): judge
- `k03` r1 (risk_change): risk_labels, judge

