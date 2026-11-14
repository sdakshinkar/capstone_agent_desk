# Commands cheat sheet (red team + guardrails)

Run everything from the project root (`capstone_agent_desk`).

## 1. Tests (about 1-2 minutes, free, no API key, fake models)

```
python -m pytest tests redteam/tests -v          # everything (the guardrail tests are in tests/unit_tests)
python -m pytest tests/unit_tests/test_guardrails.py tests/unit_tests/test_tool_guards.py tests/unit_tests/test_guardrails_app.py -v
python -m pytest redteam/tests -v
```

Expected: everything passes (227 tests: the team's, the guardrail tests, the app wiring tests and the 28 red-team harness tests).

## 2. One-time data setup

```
python -m redteam.prepare_data
```

## 3. Attack runs (slow: about 1 hour each, real API calls, needs OPENROUTER_API_KEY in .env)

```
python -m redteam.run_redteam --defences off --clean
python -m redteam.run_redteam --defences on --clean
```

Results go to `redteam/results/<timestamp>_defences-off|on/`
(`results.jsonl` = every run, `summary.md` = tables).

## 4. Compare off vs on

```
python -m redteam.run_redteam compare redteam\results\<off folder> redteam\results\<on folder>
```

## 4b. Build the full report (one row per test case, with the question sent)

```
python -m redteam.make_e2_report redteam/results/<off folder> redteam/results/<on folder>
esults\<off folder> redteam
esults\<on folder>
```

Writes `redteam/E2_results.md`.

## 5. Optional

```
python -m redteam.run_redteam --targets sandbox                    # sandbox attacks only, seconds, no key
python -m redteam.run_redteam --targets sandbox researcher quant risk   # cheaper subset
python -m redteam.run_redteam --ids DI-01 IR-02                    # only some attacks
python -m redteam.run_redteam --defences on --clean --repeats 3    # final run (brief asks for 3 repeats)
python -m redteam.run_redteam --price-in-per-m <USD> --price-out-per-m <USD>   # real cost per case
set PYTHONPATH=src && python -m agent_desk.guardrails.check_filter_on_filings   # does the guard strip real 10-K text?
```

## 6. Meaning of the flags

| Flag | Meaning |
|---|---|
| `--defences off` | system as built, no protection (baseline) |
| `--defences on` | `agent_desk.guardrails` switched on |
| `--clean` | also run the 16 legitimate questions (false-block rate) |
| `--repeats N` | repeat every case N times |
| `--include-destructive` | also run SB-12 (memory bomb). Avoid on a laptop |

## 7. Verdicts

`success` = attack worked, `defended` = ran, no check fired, `blocked` = input guard stopped it,
`error` = crashed or timed out (reported, not counted in the success rate).
