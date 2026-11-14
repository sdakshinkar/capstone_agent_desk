# c2_team on heldout

Model meta-llama/llama-3.3-70b-instruct | commit 215131a | started 2026-11-14T17:56:41 | caches: llm, risk_extraction | search mode: hybrid

| Metric | c2_team |
|---|---|
| Task success | **25/41** |
|   code checks passed | 29/41 |
|   judged cases | 26 |
|   numeric | 13/15 |
|   comparison | 4/7 |
|   narrative | 4/8 |
|   risk_change | 1/6 |
|   missing | 3/5 |
| Errors (crash / budget) | 0 |
| Timeouts | 0 |
| Replans | 11 |
| Latency p50 (s) | 25.8 |
| Latency p95 (s) | 96.9 |
| LLM calls / case | 15.6 |
| Tokens / case | 34,184 |
| Tokens total | 1,401,544 |
| Cost / case (USD) | 0.0220 |
| Cost total (USD) | 0.9040 (41/41 known) |
| Expected tool called | 32/36 |
| Evidence retrieved | 3/8 |
| Figures verified vs XBRL | 56/58 (97%) |
| Calculations in sandbox | 1/7 |
| Critic: passed first draft | 25/41 |
| Critic: passed after revision | 8/41 |
| Critic: still failing (flagged) | 8/41 |
| Critic revisions / case | 0.61 |
| Critic open issues by type | number 31 |
| Success per repeat | r1: 25 |

## Failed cases

- `t05` r1 (narrative): must_include, judge
- `t07` r1 (narrative): must_include, judge
- `t08` r1 (narrative): must_include, judge
- `t12` r1 (narrative): must_include, judge
- `k05` r1 (risk_change): risk_labels, judge
- `k06` r1 (risk_change): risk_labels, judge
- `k07` r1 (risk_change): judge
- `k08` r1 (risk_change): judge
- `k10` r1 (risk_change): risk_labels, judge
- `m04` r1 (missing): refusal, facts, judge
- `m01` r1 (missing): judge
- `n14` r1 (numeric): facts
- `n18` r1 (numeric): facts
- `c04` r1 (comparison): judge
- `c06` r1 (comparison): derived
- `c07` r1 (comparison): facts

