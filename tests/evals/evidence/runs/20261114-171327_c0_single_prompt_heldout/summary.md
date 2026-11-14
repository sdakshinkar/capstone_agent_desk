# c0_single_prompt on heldout

Model meta-llama/llama-3.3-70b-instruct | commit 215131a | started 2026-11-14T17:13:27 | caches: llm, risk_extraction | search mode: hybrid

| Metric | c0_single_prompt |
|---|---|
| Task success | **12/41** |
|   code checks passed | 12/41 |
|   judged cases | 26 |
|   numeric | 2/15 |
|   comparison | 0/7 |
|   narrative | 5/8 |
|   risk_change | 0/6 |
|   missing | 5/5 |
| Errors (crash / budget) | 0 |
| Timeouts | 0 |
| Replans | 0 |
| Latency p50 (s) | 4.2 |
| Latency p95 (s) | 9.4 |
| LLM calls / case | 1.0 |
| Tokens / case | 1,627 |
| Tokens total | 66,717 |
| Cost / case (USD) | 0.0010 |
| Cost total (USD) | 0.0428 (41/41 known) |
| Expected tool called | n/a |
| Evidence retrieved | 5/8 |
| Figures verified vs XBRL | 15/28 (54%) |
| Calculations in sandbox | n/a |
| Critic: passed first draft | n/a |
| Critic: passed after revision | n/a |
| Critic: still failing (flagged) | n/a |
| Critic revisions / case | n/a |
| Critic open issues by type | n/a |
| Success per repeat | r1: 12 |

## Failed cases

- `n09` r1 (numeric): facts
- `n10` r1 (numeric): facts
- `n11` r1 (numeric): facts
- `n12` r1 (numeric): facts, years
- `n14` r1 (numeric): facts, years
- `n15` r1 (numeric): facts
- `n16` r1 (numeric): facts
- `n17` r1 (numeric): facts
- `n18` r1 (numeric): facts
- `n19` r1 (numeric): facts
- `n21` r1 (numeric): facts
- `n22` r1 (numeric): facts
- `n23` r1 (numeric): facts
- `c04` r1 (comparison): facts, years, judge
- `c05` r1 (comparison): facts, judge
- `c06` r1 (comparison): facts, years, derived, judge
- `c07` r1 (comparison): facts
- `c08` r1 (comparison): facts, judge
- `c09` r1 (comparison): facts, judge
- `c10` r1 (comparison): facts, derived
- `t07` r1 (narrative): must_include, judge
- `t09` r1 (narrative): must_include, judge
- `t11` r1 (narrative): must_include, judge
- `k05` r1 (risk_change): risk_labels, judge
- `k06` r1 (risk_change): risk_labels, judge
- `k07` r1 (risk_change): risk_labels, judge
- `k08` r1 (risk_change): risk_labels, judge
- `k09` r1 (risk_change): risk_labels, judge
- `k10` r1 (risk_change): risk_labels, judge

