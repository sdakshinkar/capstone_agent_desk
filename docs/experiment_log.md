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
| 18 | 11-13 | — | 1829337 | — | — | — | 0.000 | C1 given the `run_python` calculator, so C1 and C2 have the same six tools. All C1 rows above ran without it. Runs now record `has_sandbox` in `run.json`. |
| 19 | 11-14 | retrieval eval | 6aead1e | all three | 32 | 0.44 / 0.59 / 0.75 | 0.000 | After merging Arun_finetuning_RAG (cross-encoder reranker, BM25 stopwords and stemming), still on the old index. |
| 20 | 11-14 | index rebuild | 6aead1e | — | 31 filings | 21,186 chunks | 0.000 | Per-Item chunking: 57,808 → 21,186 chunks, median 833 characters. The background job was stopped for low memory just after it finished; the saved index was checked complete (vectors = chunks = ids). Old index kept as `data/faiss_index_backup_20261114`. |
| 21 | 11-14 | critic model check | — | — | 1 call | ok | 0.000 | `openai/gpt-4o-mini` (the critic's judge) reachable through the account's guardrail. |
| 22 | 11-14 | merge PR #9 (critic) | 4dc7497 | — | — | — | 0.000 | Compliance critic, evidence register, tracing. Fixed while merging: `search_filing` P-ids restored next to Arun's `mode`; duplicate Apple FY2025 10-K (browser-saved `.html` + `_files/`) and `README copy.md` removed. |
| 23 | 11-14 | eval harness for the critic | 3fa917f | — | — | — | 0.000 | C2 runs with a fresh evidence register (otherwise the critic skips itself) and step limit 50; critic verdicts recorded and summarised; repeats turn off the risk cache. No critic on/off switch (team decision). |
| 24 | 11-14 | retrieval eval | 3fa917f | all three | 32 | 0.47 / 0.72 / 0.81 | 0.000 | On the rebuilt index. Hybrid MRR 0.64. First Republic (r021) found for the first time. |
| 25 | 11-14 | `143717_c0_single_prompt_dev` *evidence* | 3fa917f | hybrid | dev 21 | 7 / 7 | 0.020 | Final C0. Better chunks lift text questions (3/4); numbers still 2/8. |
| 26 | 11-14 | `143941_c1_single_agent_dev` *evidence* | 3fa917f | hybrid | dev 21 | 15 / 14 | 0.362 | Final C1 with the calculator (used in 3/4 calculation cases); numeric 8/8. |
| 27 | 11-14 | `144348_c2_team_dev` *evidence* | 3fa917f | hybrid | dev 21 | 18 / 15 | 0.314 | Final C2 with the critic. All 26 figures match XBRL. Critic: 12 first-pass, 1 after revision, 8 still failing (citation form: passage ids after figures, missing ids). Failures: t03 (`company="jpmorgan chase"` matches no index name), t04 (planner chose fiscal 2024), m02 (labelled substitution not matched by refusal patterns; judge passed it), judge fails k01, k03, k04 (and c01 before the rubric clarification, row 30). |
| 28 | 11-14 | judge, runs 25–27 | 3fa917f | — | 39 | — | ~0.04 | Gemini judge, `--all`. |
| 29 | 11-14 | company-name fix | e4fbc32 | — | — | — | 0.000 | `agent_desk/companies.py`: names, legal forms and tickers ("jpmorgan chase", "JPMorgan Chase & Co.", "JPM") map to index names in the search filter, filing lookup, risk passage ids and risk cache. C2's exact t03 search now returns the First Republic passage. Not yet re-run with the agents. |
| 30 | 11-14 | judge rubric clarification | dd0444a | — | 15 comparison verdicts ×2 | C0 7, C1 14, C2 15 | ~0.02 | Comparison rubric: naming each company's own fiscal year is correct; fail only if the answer says the figures cover the same months, and only when the case notes say year-ends differ. A first wording without that condition wrongly failed C1 c02 (both years end 31 December) and was corrected. Five runs re-judged; kappa on the 26 hand labels still 1.00. C2 c01 now passes (14 → 15). |
| 31 | 11-14 | targeted re-run t03, k03 | dd0444a | hybrid | C1 and C2, 2 cases each | t03 pass in both; k03 judge-fail in both | ~0.06 | Checks the company-name fix end to end: all four runs still call the tools with "jpmorgan chase" and now get JPMorgan's data. t03 (First Republic) passes in C1 and C2; k03 now runs but both miss the labelled change (content, not name). |
| 32 | 11-14 | `154010_c0_single_prompt_dev` *evidence* | dd0444a | hybrid | dev 21 | 7 / 7 | (cached) | Final C0 after the fix; identical to run 25 (C0 does not pass company names to tools). |
| 33 | 11-14 | `154057_c1_single_agent_dev` *evidence* | dd0444a | hybrid | dev 21 | 16 / 14 | (partly cached) | Final C1: t03 now passes; k03 runs (judge fail, as k01); n07 lost (run-to-run variation). Calculator used in 4/4 calculation cases; figures 12/12 verified. |
| 34 | 11-14 | `154349_c2_team_dev` *evidence* | dd0444a | hybrid | dev 21 | 19 / 15 | (partly cached) | Final C2: t03 now passes. Judge fails k01, k03, k04 (risk content) and c03 (cited `D1` for a growth rate computed without the sandbox). Critic 12 / 1 / 8 (first pass / after revision / still failing). Rows 32–34 together cost USD 0.43 of account usage (reported 0.62; cached calls replayed). Latency and cost in the report come from runs 25–27. |
| 35 | 11-14 | calibration re-score | 555205b | — | 26 hand labels | κ = 0.92 | 0.000 | The labeller relabelled C2 k04 (calibration set) from pass to fail on review; 25/26 agreement, the judge passed that answer. |
| 36 | 11-14 | `160508_c2_team_dev` ×2 repeats *evidence* | 555205b | hybrid | dev 21 ×2, caches off | 15 and 16 | 0.87 (account, incl. judge) | Fresh C2 repeats. Numeric, comparison and missing all pass in both; narrative 2/4 and 3/4; risk change 0/4 and 0/4 because 13 of 21 risk comparisons failed with "400 Provider returned error" (strict structured output not supported by every provider OpenRouter routes to) and 2 hit the length limit. Earlier risk results relied on cached risk lists. p50 21.4 s, p95 196.4 s, USD 0.0205 per case. |

## Next

- Held-out: C0, C1, C2 × 3 repeats with hybrid search, caches off, then judge (about USD 5–6).
- For the team: let the critic
  accept a passage id after figures taken from filing text; ask the domain lead to review the
  held-out cases.
