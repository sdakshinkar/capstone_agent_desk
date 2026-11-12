# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Agent Desk: a 10-K filings research assistant (capstone project). A LangGraph multi-agent team answers questions about companies' filings using a local FAISS index of 10-K HTML, the SEC XBRL Company Facts API, an LLM-verified risk-factor diff, and a restricted Python calculator. The capstone notebooks/brief in `documents/` are reference only; project code must be original, not copied from them.

## Working agreement (from README)

- Before choosing among reasonable implementation options, explain the alternatives and ask for approval.
- Before each step that creates or changes files, describe the intended files and contents and wait for approval.

## Commands

Run from the project root (Windows; `pytest.ini` sets `pythonpath = src`, `testpaths = tests`):

```bat
python -m pip install -r requirements.txt
python -m pytest                                              :: unit tests in tests/
python -m pytest tests/unit_tests/test_supervisor_retry.py    :: one file
python -m pytest tests/unit_tests/test_risk_compare.py -k name :: one test
python src\agent_desk\__main__.py                             :: run team workflow on QUESTION* in main.py
streamlit run src/agent_desk/ui/app.py                        :: UI with plan approval
```

Unit tests use fakes/monkeypatching (e.g. replacing `get_tool_llm`) and need no API key. `streamlit` and `langsmith` are imported but not listed in `requirements.txt`.

`.env` (copy `.env.example`) needs `OPENROUTER_API_KEY` and `SEC_USER_AGENT` (SEC-compliant, with contact address). Optional `LANGSMITH_API_KEY` / `LANGCHAIN_PROJECT` enable tracing in `main.py`.

Data setup (outputs under gitignored `data/`):
1. `src/agent_desk/utils/filling_download.py` — edit `SPECS` in `main()`; saves 10-K HTML to `data/filings/<company>/<year>/`.
2. `src/agent_desk/utils/create_embeddings.py` — uncomment one call in `main()`; builds a single FAISS index in `data/faiss_index/` (all-MiniLM-L6-v2, 1000/150 chunks, metadata `company`/`year`/`item`/`source`). Search never builds the index; it errors if missing.

## Architecture

**Team graph** (`agents/workflow.py`, state in `agents/team_state.py`):
`research_lead -> [approve_plan] -> supervisor <-> {researcher_worker, quant_worker, risk_worker} -> writer -> END`

- `research_lead_agent.py` returns a JSON plan `{goal, sub_questions, outline}`. Its prompt is rebuilt each call with the locally available filings (`rag/risk_section.available_filings()`), so "latest year" means newest stored filing, never the current date.
- `approve_plan` only exists when the graph is compiled with a checkpointer; it uses `interrupt()` and resumes with `{"action": "approve"}` or `{"action": "edit", "plan": {...}}`. Node must stay side-effect-free before `interrupt()` (it re-runs on resume). `configurable.auto_approve` skips it. `run_team_workflow` builds without a checkpointer (no approval); the Streamlit UI uses `InMemorySaver`.
- `supervisor_agent.py` walks `plan_step` through `sub_questions`, writes one self-contained brief per worker call (workers only see the brief), and routes via strict JSON structured output. It can `REPLAN` (bounded by `max_replans`) or `FINISH`. Reply tokens are capped (`MAX_ROUTE_TOKENS`) with retries because of runaway generations.
- Workers are `create_react_agent` instances: researcher (`search_filing` RAG tool), quant (EDGAR Company Facts tools + `run_python`), risk diff (`compare_risk_factors`). Worker exceptions become `WORKER FAILED: ...` messages so the supervisor can retry/replan.
- Worker results accumulate in `narrative` / `facts` / `risk` lists as `"Q: <brief>\nA: <answer>"` via the `accumulate_or_reset` reducer; a replan sends `[RESET]` to clear them and removes messages after the original question.
- `writer_node` makes one LLM call for the final answer, then appends the raw worker findings verbatim under `"Supporting findings:"` (the UI splits on this marker). On LLM failure it falls back to the supervisor's notes.
- `langgraph_workflow.py` and `coordinator_agent.py` are older, simpler orchestrations (stdin-based approval); `workflow.py` is the current one used by `main.py` and the UI.

**LLMs** (`llm/llm.py`): OpenRouter via `ChatOpenAI`. `get_tool_llm()` = llama-3.3-70b-instruct (used everywhere), `get_fast_llm()` = llama-3.1-8b. Paths are resolved from `PROJECT_ROOT` (three parents up from the module), and `.env` is loaded from there.

**Risk diff** (`rag/risk_compare.py`, see its docstring): load Item 1A passages per year (`risk_section.py`) -> LLM extracts risk lists (`risk_extract.py`) -> LLM proposes added/removed/changed -> code verifies claims with embedding similarity over passages and a batched LLM materiality check, rejecting renamed/regrouped risks. Reads filing HTML directly, not the FAISS index.

**EDGAR** (`tools/edgar_tools.py`): Company Facts API only (no submissions/archives). Company directory is a small local list; responses cached per CIK in `data/edgar_cache/` (`force_refresh=True` to bypass). Tools return structured JSON, including errors. Quant prompt relies on data quirks: a row's `fiscal_year` is the filing year, so periods are matched via start/end dates and multi-year queries use the newest year.

**Sandbox** (`sandbox/python_sandbox.py`): AST-validated subset run in an isolated child process (`python -I`, empty env, restricted builtins, only math/statistics/fractions/decimal, timeout and output cap). It is a guard for our own model's arithmetic, not a security boundary.

## Untracked side projects

`rdayal_guardrails/` (rule-based input/output and tool-boundary guards, installed via `with install(question):` without editing team code) and `rdayal_redteam/` (attack suite + E2 defences off/on evaluation) are not covered by `pytest.ini` testpaths; run them explicitly, e.g. `python -m pytest rdayal_redteam/tests -q`, `python -m rdayal_redteam.run_redteam --targets sandbox`. See each folder's README.
