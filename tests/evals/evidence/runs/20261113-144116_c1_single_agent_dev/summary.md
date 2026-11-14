# c1_single_agent on dev

Model meta-llama/llama-3.3-70b-instruct | commit 2d4f0f0 | started 2026-11-13T14:41:16 | caches: llm, risk_extraction | search mode: default

| Metric | c1_single_agent |
|---|---|
| Task success | **12/21** |
|   code checks passed | 14/21 |
|   judged cases | 13 |
|   numeric | 6/8 |
|   comparison | 2/3 |
|   narrative | 1/4 |
|   risk_change | 1/4 |
|   missing | 2/2 |
| Errors (crash / budget) | 0 |
| Timeouts | 0 |
| Replans | 0 |
| Latency p50 (s) | 6.3 |
| Latency p95 (s) | 16.6 |
| LLM calls / case | 4.4 |
| Tokens / case | 14,202 |
| Tokens total | 298,251 |
| Cost / case (USD) | 0.0099 |
| Cost total (USD) | 0.2074 (21/21 known) |
| Expected tool called | 17/19 |
| Evidence retrieved | 1/4 |
| Figures verified vs XBRL | 19/20 (95%) |
| Calculations in sandbox | n/a |
| Critic: passed first draft | n/a |
| Critic: passed after revision | n/a |
| Critic: still failing (flagged) | n/a |
| Critic revisions / case | n/a |
| Critic open issues by type | n/a |
| Success per repeat | r1: 12 |

## Failed cases

- `n07` r1 (numeric): facts
- `n08` r1 (numeric): facts
- `c01` r1 (comparison): facts, judge
- `t02` r1 (narrative): must_include, judge
- `t03` r1 (narrative): must_include, judge
- `t04` r1 (narrative): must_include
- `k01` r1 (risk_change): judge
- `k03` r1 (risk_change): risk_labels, judge
- `k04` r1 (risk_change): judge

