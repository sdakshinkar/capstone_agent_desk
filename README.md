# Agent Desk

A company-filings research assistant built in small, reviewable stages. The
capstone notebooks and project brief are reference material only; the project
implementation will be original code.

## Planned scope

1. Create a basic project structure and a working proof of concept.
2. Add retrieval for filings: cover 10–15 companies across two sectors and
   three years each; split 10-K HTML by Item, preserve tables, and attach
   company, year, and Item metadata. The retrieval stage will include hybrid
   search, a reranker, and one query-side technique.
3. Add the `filings-kb`, `edgar`, and `python-sandbox` tools.
4. Add orchestration and planning through a plan and outline.

The initial goal is to stop after the plan-and-outline stage. More advanced
capstone topics are out of scope unless requested later.

## Working agreement

- Notebook lessons guide concepts and implementation options; their code is
  not copied or run as the project implementation.
- Before choosing among reasonable implementation options, explain the
  alternatives and ask for approval.
- Before each step that creates or changes files, describe the intended files
  and their contents and wait for approval.

## Quick start (proof of concept)

The first prototype is a local keyword search over a saved 10-K. It makes no
network calls and uses no model.


## ********************************************
```powershell
pip install -r requirements.txt
set PYTHONPATH=src
python -m agent_desk "supply chain risk"
python -m pytest
```
## ********************************************

Place filings under `data/filings/<company>/<year>/`. By default the CLI reads
`data/filings/apple/2025/aapl-20251227.html` (Apple's FY2025 10-K); use
`--filing PATH` to point at another file.

Current limits: literal keyword scoring only, table text is flattened, and
there is no embedding search, reranking, query decomposition or answer
generation yet. These arrive in later stages.

## SEC Company Facts tools (L7 step)

`src/agent_desk/edgar_tools.py` exposes LangChain tools backed only by the SEC
XBRL Company Facts API. It does not download or search filing HTML and does not
call SEC submissions, filing archives, or other SEC endpoints.

1. Copy `.env.example` to `.env` and replace its example value with a
   descriptive SEC-compliant `SEC_USER_AGENT` (include a contact address).
   `.env` is ignored by Git.
2. Install dependencies with `pip install -r requirements.txt`.
3. Import `list_edgar_companies`, `list_company_facts`, and
   `get_company_fact` from `agent_desk.edgar_tools` in the project agent.

Company Facts provides facts for a known CIK; it does not provide company
discovery. `list_edgar_companies` therefore lists the small local company
directory in the tool module (currently Apple, Microsoft and Alphabet). The fact-list and fact-lookup tools accept any CIK.

Successful Company Facts responses are cached in `data/edgar_cache/` by CIK so
repeat lookups do not make another request. Pass `force_refresh=True` to fetch
fresh API data. Results retain reported value, unit, fiscal year and period,
filing form/date, start/end dates, and accession number. Errors, including a
missing User-Agent or SEC request failure, are returned explicitly as
structured JSON.

## Researcher agent

`python -m agent_desk "question"` runs a single standalone researcher: a
LangGraph ReAct agent that calls the EDGAR tools one at a time (serial, no
parallel agents) and answers from the data they return.

1. `python -m pip install -r requirements.txt`
2. Put `SEC_USER_AGENT` and `OPENROUTER_API_KEY` in `.env` (see `.env.example`).
3. Run (cmd shown; set `PYTHONPATH` once per terminal):

```bat
set PYTHONPATH=src
python -m agent_desk "Compare Microsoft and Alphabet operating margins over the last three fiscal years"
python -m agent_desk --search "supply chain risk"
```

`--search` keeps the offline keyword search over the saved Apple 10-K.

Models (OpenRouter, in `src/agent_desk/llm.py`): `meta-llama/llama-3.3-70b-instruct`
for tool calls (`tool_llm`) and `meta-llama/llama-3.1-8b-instruct` for fast
routing or plain chat (`fast_llm`, not used by the researcher yet).

Limitation: the agent only has XBRL facts, so it cannot read narrative text
such as risk factors until filing retrieval is added.

## Initial structure

```text
.
├── data/                  # Local project data; generated data is not committed
├── documents/             # Capstone brief and other reference documents
├── notebooks/             # Lesson notebooks used as references only
├── src/
│   └── agent_desk/        # Application package and SEC Company Facts tools
├── tests/                 # Automated tests
├── .gitignore
├── .env.example
├── pytest.ini
├── requirements.txt
└── README.md
```

python -m agent_desk "supply chain risk"