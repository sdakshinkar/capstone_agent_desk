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

## Quick start

Install dependencies and run the tests in cmd:

```bat
python -m pip install -r requirements.txt
python -m pytest
```

Run the agent by opening `src/agent_desk/__main__.py`, setting `QUESTION` at
the top, and pressing Run or Debug (F5). The researcher agent can use both
local filing retrieval and SEC Company Facts tools.

## Filings and embeddings

1. Download 10-Ks (HTML) with `src/agent_desk/utils/filling_download.py`; edit
   `SPECS` in `main()` and run it. Files go to
   `data/filings/<company>/<year>/`.
2. Build the index with `src/agent_desk/utils/create_embeddings.py`; uncomment
   one call in `main()`: `create_all_embeddings()`,
   `create_company_embeddings(name)`, `delete_company_embeddings(name)` or
   `delete_all_embeddings()`.

Embeddings are never built during a search. `create_embeddings.py` extracts text
with BeautifulSoup (`rag/filing_parser.py`), splits each Item passage with
`RecursiveCharacterTextSplitter` (1,000-character chunks, 150 overlap), embeds with
`sentence-transformers/all-MiniLM-L6-v2` (downloaded from Hugging Face on first
use) and saves one combined FAISS index in `data/faiss_index/`. Every chunk has
`company`, `year`, `item` and `source` metadata. `search_filing(query, company,
year, k)` searches that index and can filter by company and/or year; it raises an
error if the index has not been built.

This is the simple RAG foundation only: it flattens table contents to text, and does not yet include hybrid search,
reranking, or query decomposition.

## SEC Company Facts tools (L7 step)

`src/agent_desk/tools/edgar_tools.py` exposes LangChain tools backed only by the SEC
XBRL Company Facts API. It does not download or search filing HTML and does not
call SEC submissions, filing archives, or other SEC endpoints.

1. Copy `.env.example` to `.env` and replace its example value with a
   descriptive SEC-compliant `SEC_USER_AGENT` (include a contact address).
   `.env` is ignored by Git.
2. Install dependencies with `pip install -r requirements.txt`.
3. Import `list_edgar_companies`, `list_company_facts`, and
   `get_company_fact` from `agent_desk.tools.edgar_tools` in the project agent.

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

Running `src/agent_desk/__main__.py` runs a single standalone researcher: a
LangGraph ReAct agent that calls the filing retrieval and EDGAR tools one at a
time (serial, no parallel agents). It uses filing retrieval for narrative
questions and Company Facts for reported numbers.

1. `python -m pip install -r requirements.txt`
2. Put `SEC_USER_AGENT` and `OPENROUTER_API_KEY` in `.env` (see `.env.example`).
3. Run: edit `QUESTION` in `__main__.py` (for example, "Compare Microsoft and
   Alphabet operating margins over the last three fiscal years") and run or
   debug the file. Alternatively, run `python src\agent_desk\__main__.py` from
   the project root.

Models (OpenRouter, in `src/agent_desk/llm/llm.py`): `meta-llama/llama-3.3-70b-instruct`
for tool calls (`tool_llm`) and `meta-llama/llama-3.1-8b-instruct` for fast
routing or plain chat (`fast_llm`, not used by the researcher yet).

Narrative filing search covers the companies and years whose filings you downloaded and indexed (see "Filings and embeddings"). Company Facts supports reported XBRL data for the listed companies.

## Initial structure

```text
.
├── data/              # Local project data; generated data is not committed
├── documents/         # Capstone brief and other reference documents
├── notebooks/         # Lesson notebooks used as references only
├── src/
│   └── agent_desk/
│       ├── agents/    # researcher_agent.py (LangGraph ReAct agent)
│       ├── llm/       # llm.py (OpenRouter chat models)
│       ├── rag/       # filing_parser.py, filing_rag.py (FAISS search)
│       ├── tools/     # edgar_tools.py, rag_tools.py (agent tools)
│       ├── utils/     # filling_download.py, create_embeddings.py
│       └── __main__.py   # Run or debug this file
├── tests/             # Automated tests (see tests/unit_tests/)
├── .gitignore
├── .env.example
├── pytest.ini
├── requirements.txt
└── README.md
```

