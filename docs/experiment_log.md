# Experiment log — evaluation

One row per eval run, in order. Results are task success after the code checks, then after the
judge where the run was judged ("code / final"). Costs are those reported by OpenRouter per call.
Runs marked *evidence* are copied to `tests/evals/evidence/runs/`. Model for every agent run:
`meta-llama/llama-3.3-70b-instruct` (OpenRouter default routing).

| # | Date | Run | Commit | Search | Cases | Result | Cost | Notes and what changed afterwards |
|---|---|---|---|---|---|---|---|---|
| 0 | 11-11 | smoke attempt | — | semantic | 3 dev | — | 0.000 | Stopped at the first call: OpenRouter 402, insufficient credits. Nothing saved. |
| 1 | 11-11 | `184735_c2_team_dev` | ad60d2e | semantic | n01–n03 | 3/3 | 0.022 | Smoke test after adding credits. |
| 2 | 11-11 | `184837_c2_team_dev` | ad60d2e | semantic | k01 | 1/1 | 0.015 | Cost check for a risk comparison (47k tokens, 102 s). |
| 3 | 11-11 | `185914_c2_team_dev` *evidence* | ad60d2e | semantic | dev 21 | 18 → 20 / 18 | 0.283 | First full dev run: 18/21. Failures c01 and k02 traced to the checker and a wrong gold label; after the fixes (truncated percentages accepted; k02 relabelled from the filing) regraded to 20/21. Judged on 11-13: k01 and k03 failed by the judge → 18/21. Judge calibration set 2. |
| 4 | 11-12 | `183020_c2_team_dev` *evidence* | 4ea25b4 | semantic | numeric + comparison (11) | 11/11 | 0.145 | Re-check after merging develop (quant worker gains `run_python`). `run_python` called in 1 of 4 calculation cases. |
| 5 | 11-13 | `134923_c0_single_prompt_dev` *evidence* | 2d4f0f0 | semantic | dev 21 | 3 / 3 | 0.011 | First C0 run. Low token count checked: C0 works as designed; short retrieved chunks lead it to answer "not available". |
| 6 | 11-13 | `135034_c1_single_agent_dev` | 2d4f0f0 | semantic | dev 21 | 10 | 0.192 | First C1 run. All risk cases and m02 ended after one call with a tool call written as text. → C1 prompt rule added (committed as 90406a1). |
| 7 | 11-13 | `143905_c1_single_agent_dev` | 2d4f0f0 + C1 fix | semantic | k01–k04, m02 | 4/5 | 0.021 | Verifies the C1 fix. k03 fails genuinely (wrong company name, no retry). |
| 8 | 11-13 | `144116_c1_single_agent_dev` *evidence* | 2d4f0f0 + C1 fix | semantic | dev 21 | 14 / 12 | 0.207 | Full C1 run with one prompt for all cases (same 14 as run 6 + 7 combined, different cases failing). Judge failed k01 and k04. Judge calibration set 1. |
| 9 | 11-13 | retrieval eval | 1d90096 | all three | 32 | 0.44 / 0.50 / 0.53 | 0.000 | Recall@5 semantic / keyword / hybrid after merging Arun's hybrid search. No LLM. |
| 10 | 11-13 | `161734_c0_single_prompt_dev` *evidence* | 1d90096 + search override | hybrid | dev 21 | 4 | 0.009 | Hybrid helps C0 on two narrative cases (t02, t04), loses n05. |
| 11 | 11-13 | `161828_c1_single_agent_dev` *evidence* | 1d90096 + search override | hybrid | dev 21 | 9 | 0.063 | Not used for comparison: 7 cases got "Your input is not sufficient…" on the first call, before any search; some cases billed at USD 0.18 per million tokens instead of 0.71, suggesting a different provider. Bad replies removed from the LLM cache. |
| 12 | 11-13 | `162059_c2_team_dev` *evidence* | 1d90096 + search override | hybrid | dev 21 | 18 | 0.281 | t02 and t04 fail although the right passage was retrieved (answer errors, a wrong-year plan). |
| 13 | 11-13 | `163232_c1_single_agent_dev` | 1d90096 + search override | hybrid | n02, c01 ×2, cache off | 0/4 | 0.018 | Checks run 11's glitch: tool calls now made, but numeric answers still wrong (e.g. Apple's income divided by Amazon's revenue). |
| 14 | 11-13 | judge, runs 3 and 8 | — | — | 26 outputs | — | ~0.03 | First attempt with Qwen returned 404 "blocked by guardrail" for every case (no charge) → judge switched to `google/gemini-3.1-flash-lite`. |
| 15 | 11-13 | calibration | dd98eba | — | 26 hand labels | κ = 1.00 | 0.000 | 26/26 agreement; the judge failed four risk answers that passed the keyword check, and the human labels agreed. |
| 16 | 11-13 | judge, run 5 | dd98eba | — | 13 | — | ~0.01 | C0 judged; task success unchanged at 3/21. |
| 17 | 11-13 | regrade, all runs | 35c1c12 | — | — | — | 0.000 | Added the verified-figures and sandbox-use diagnostics; fixed "- 11.16%" being read as negative. No pass/fail result changed. |

| 18 | 11-13 | — | (this commit) | — | — | — | 0.000 | C1 given the `run_python` calculator, so C1 and C2 have the same six tools. All C1 rows above ran without it. Runs now record `has_sandbox` in `run.json`. |

## Next

- Choose the search mode for all systems; disable the risk cache for the repeats.
- Held-out: C0, C1, C2 × 3 repeats, then judge (about USD 3.50–4.50).
