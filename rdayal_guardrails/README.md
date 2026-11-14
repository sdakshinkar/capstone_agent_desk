# rdayal_guardrails: defences for Agent Desk

Two layers, rule-based, with no extra model calls. They plug in from outside, so no team file has
to change. `with install(question): ...` wraps the team's tools for one request.

## Layer 1: question and answer (`__init__.py`)

| Check | Stops |
|---|---|
| `check_input(question)` | prompt injection (override instructions, change role, reveal prompt, encoded instructions); personal investment advice; insider-information, price-manipulation and phishing requests |
| `check_output(answer, question)` | buy/sell calls and price targets; system-prompt text; anything from a block the user marked CONFIDENTIAL; external links and images (sec.gov kept) |

## Layer 2: tool boundary (`tool_guards.py`)

| Check | Stops |
|---|---|
| pre-tool hook | private-context terms in tool arguments (watchlist leak); `force_refresh` (forced to False); a per-request call budget per tool; sandbox code that uses interpreter internals (`sys`, `modules`, `builtins`, `os`, `open`, `eval`...) |
| tool-result filter | sentences in filing text, EDGAR labels or risk quotes that address the AI or give it instructions; hidden HTML; external links. Numbers and normal prose pass through |
| EDGAR integrity | SHA-256 recorded in `data/edgar_manifest.json` when a Company Facts file is downloaded; a cached file that does not match is ignored and fetched again from SEC |

## Measured so far (12 Nov)

* Layer 1 on the laptop: agent attacks getting through went from 5/13 to 3/13, with 0 false blocks
  (0/5 completed normal questions; 0/16 on the input check).
* Layer 2 offline: the filter removes the instruction from 13 of 14 poisoned data texts. It misses
  IR-04, a plain false number with no instruction; the defence there is "numbers only from XBRL".
  Hook on: sandbox attacks drop from 4/11 to 0/11.
* Normal 10-K language checked by hand passes untouched. **Run
  `python -m rdayal_guardrails.check_filter_on_filings` after building the index** to measure the
  filter's false-positive rate on all real filing text.

## Honesty note (for E2)

The same person built these defences and saw the red-team suite. Rules were written as general
categories (text addressed to an AI, tool-call syntax inside data, investment-advice language),
and patterns that matched attack wording or normal 10-K language were removed. Pratik should add
5–10 held-out attacks the defender has not seen.

## Known gaps

* English-only patterns; paraphrased injections can slip through. Next step: a classifier model
  (for example Llama Prompt Guard 2).
* The code check is a second line. The real sandbox fix (container, no network, no secrets) belongs
  in `python_sandbox.py` (FINDINGS F1).
* The EDGAR manifest lives next to the data. For production, sign it with a secret key.
* A false number written as plain text (IR-04) needs the compliance critic to check numbers against facts.

## Run

```bat
python -m pytest rdayal_guardrails/tests -q
python -m rdayal_guardrails.check_filter_on_filings
python -m rdayal_redteam.run_redteam --defences on --targets researcher quant risk
```
