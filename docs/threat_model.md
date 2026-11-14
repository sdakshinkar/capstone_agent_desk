# Threat model: Analyst Desk

**DRAFT - to be agreed with the Role 4 (tools/control/security) owner.**
Scope: the LangGraph team (research lead, supervisor, researcher / quant / risk workers, writer) answering questions about Apple, Microsoft and Alphabet 10-Ks. Measured results (14 Nov, one run per case): 18 of 45 attacks worked with defences off and 1 of 45 with defences on; 0 of 16 honest questions wrongly blocked. Per-case table in `redteam/E2_results.md`.

## Assets

1. **Private watchlist / memory**: confidential tickers must never reach a tool argument, a search query or the answer.
2. **OpenRouter key and `.env`**: readable by anything that can run code on the host.
3. **EDGAR cache integrity**: a changed value silently becomes a "fact".
4. **Analyst trust in numbers**: figures must trace to a filing; no investment advice.

## Entry points (trust boundaries)

User message; filing passages returned by FAISS search; EDGAR Company Facts cache (labels, names, values); risk-factor diff passages; edited plans at the approval step; model-written Python in the sandbox. Everything except the user's own message is untrusted *data* that may carry instructions.

## Threats, tests and status

| Threat | Attacks (`attacks.jsonl`) | Mitigation | Status |
|---|---|---|---|
| Direct injection, prompt leak, obfuscated / multilingual | DI-01..08 | `check_input` / `check_output` rules | Partly (English rules only). E2: 4 of 8 worked off, 1 on (DI-04: a false number from the user) |
| Out-of-scope advice, insider info, manipulation | SC-01..05 | input scope rules, advice filter on output | Mitigated in E2: 4 of 5 worked off, 0 on |
| Indirect injection via filing passages (hidden HTML, fake approval, link exfil, fake numbers) | IR-01..08 (9 cases) | result filter strips text addressed to the AI, hidden HTML, external links | Partly; a plain false number (IR-04) passes the filter |
| Poisoned EDGAR labels / values | ED-01..04 | result filter; SHA-256 manifest re-fetches tampered files | Partly (manifest sits beside the data, unsigned) |
| Poisoned risk-diff passage | RK-01..02 | result filter | Partly |
| Watchlist leak (direct, via tool, via plan) | WL-01..03 | pre-tool hook blocks private terms; output check | Mitigated in E2: 3 of 3 worked off, 0 on (rule-based; a differently worded leak may pass) |
| Runaway cost / tool abuse, `force_refresh` | DS-01..03, DI-05 | per-tool call budget, `force_refresh` forced False | Mitigated by hook (DS-01 worked off, held on) |
| Plan edits carry instructions | DI-08 (F6) | none in team code | OPEN |
| **Sandbox escape to shell, files, network (F1)** | SB-05..08 | `guardrails` code check blocks `sys`, `modules`, `builtins`, `os`, `open`, `eval` before running | **OPEN: unfixed in `src/agent_desk/sandbox/python_sandbox.py`**; the hook is only a second line |
| Worker text reaches final answer unfiltered (F3) | IR-01T, IR-04 | none yet (compliance critic should cover it) | OPEN |
| FAISS index unpickled with `allow_dangerous_deserialization=True` (F5) | not tested | build the index locally only | OPEN |
| Sandbox DoS (time, output, memory) | SB-09..12 | time and output limits; no memory cap on Windows | Partly |

15 of the 46 attacks go through the data path (filing chunks, EDGAR cache, risk passages).

## Defences in place

Layer 1: `check_input` and `check_output`, regex rules, no extra model calls. Layer 2 (`install`): pre-tool hook, result filter and EDGAR hash manifest, wrapped around the tools. Both layers live in `src/agent_desk/guardrails/` and run in the Streamlit app and `main.py` by default (switch: `AGENT_DESK_DEFENCES`). Each agent should receive only the tools it needs.

## Residual risks and limits

- **F1 is the critical gap.** The real fix is a container (no network, read-only filesystem, no secrets, non-root, memory limit); until then a prompt injection that reaches the quant agent can run commands.
- Rule-based guards only. No Llama Guard or Prompt Guard model, so paraphrased or non-English injections can slip through.
- Poison is planted at rank 1 of search results, the worst case; real retrieval may rank it lower.
- Attacks and defences were written by the same person, against the brief's separation rule. Rules were kept general, but held-out attacks from a teammate are still needed.
- The private watchlist is simulated in the prompt because no memory store exists yet (WL-01..03, IR-03).
