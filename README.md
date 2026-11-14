# Agent Desk

A SEC company-filings research assistant built in small, reviewable stages.
The current implementation combines local 10-K retrieval, XBRL facts, restricted
Python calculations, year-over-year risk comparison, multi-agent planning,
human plan approval, evidence citations, and a compliance critic.
The [notebooks](notebooks/) and [project brief](documents/) are reference material.

## Current scope

- A research lead builds a plan and outline; a supervisor routes work to
  researcher, quant, and risk-diff specialists, one worker at a time.
- A Streamlit UI lets the user edit and approve the plan before execution.
- Tool observations are recorded in a per-run evidence register.
- A writer produces a cited answer; a critic can request up to two revisions.
- The UI renders numbered citations, a Sources expander, supporting findings,
  and compliance status.
- Company Facts responses and per-year risk extractions have local disk caches.
- The terminal runner supports optional LangSmith tracing.

The original goal stopped at planning. Subsequent approved work added the UI,
critic, citations, caching, and tracing. This is still a POC, not the complete
capstone target; see [Remaining limitations](#remaining-limitations).

## Working agreement

- Notebook lessons guide concepts and implementation options; their code is
  not copied or run as the project implementation.
- Before choosing among reasonable implementation options, explain the
  alternatives and ask for approval.
- Before each step that creates or changes files, describe the intended files
  and their contents and wait for approval.

## Setup

Run these commands from the project root with the project's Python environment
active:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Copy the template only if you do not already have an [.env](.env); do not
overwrite existing credentials. Edit it using [.env.example](.env.example):

| Variable | Purpose |
| --- | --- |
| `SEC_USER_AGENT` | Descriptive SEC-compliant User-Agent, including a contact address. |
| `OPENROUTER_API_KEY` | API key for the specialist, writer, and judge models. |
| `LANGSMITH_API_KEY` | Optional tracing key; remove the placeholder if tracing is not wanted. |
| `LANGSMITH_PROJECT` | Optional trace project; terminal default is `agent-desk`. |
| `LANGSMITH_TRACING` | Enables library-level automatic tracing; see the terminal override below. |

The environment file and generated data are ignored by Git. Do not commit API
keys. Model calls require network access and may incur provider charges.
Prepare local filings and their FAISS index before asking narrative questions.

Embeddings are never built during a search. `create_embeddings.py` extracts text
with BeautifulSoup (`rag/filing_parser.py`), joins consecutive paragraphs of the same
Item, splits each Item's text with
`RecursiveCharacterTextSplitter` (1,000-character chunks, 150 overlap), embeds with
`sentence-transformers/all-MiniLM-L6-v2` (downloaded from Hugging Face on first
use) and saves one combined FAISS index in `data/faiss_index/`. Every chunk has
`company`, `year`, `item` and `source` metadata. `search_filing(query, company,
year, k, mode)` searches that index and can filter by company and/or year; it raises an
error if the index has not been built.

### Retrieval modes

`search_chunks(..., mode=...)` in `rag/filing_rag.py` (and the `mode` argument of the
`search_filing` tool) supports three modes over the same chunks and filters:

| Mode | How it ranks | Best for |
|---|---|---|
| `semantic` (default) | FAISS vector similarity of `all-MiniLM-L6-v2` embeddings | paraphrased questions, broad topics |
| `keyword` | BM25 (LangChain `BM25Retriever`, `rank-bm25`) | exact names, terms and numbers ("First Republic", "166,000") |
| `hybrid` | both, merged with Reciprocal Rank Fusion, then reranked by a cross-encoder | general use (best recall) |

The BM25 index is built in memory from the chunks in the FAISS docstore the first
time a keyword or hybrid search runs (one per company/year filter, rebuilt when the
FAISS index changes), so there is no separate build step. Its tokenizer lowercases
text, keeps numbers like `166,000` and `72.22` whole, splits words on punctuation,
drops common stopwords ("how", "does", "the", …) and applies a light suffix stemmer,
so "employ", "employed" and "employees" all match.

Hybrid search fuses the semantic and keyword rankings (`Σ weight / (60 + rank)`,
weights in `HYBRID_WEIGHTS`, 0.5 / 0.5), keeps the top 30 (`RERANK_CANDIDATES`) and
re-scores them with the local cross-encoder `cross-encoder/ms-marco-MiniLM-L-6-v2`
(part of `sentence-transformers`, downloaded from Hugging Face on first use, runs on
CPU). Set `HYBRID_RERANK = False` to skip the reranker for faster but less accurate
results. All constants are at the top of `filing_rag.py`; to change the default mode
for every caller, set `DEFAULT_SEARCH_MODE`.

Compare the modes on the retrieval eval set:

```bat
python tests/evals/run_retrieval_eval.py --mode all --k 5
```

Tables are still flattened to text, and there is no query decomposition yet.

## Run the Streamlit UI

```powershell
python -m streamlit run src\agent_desk\ui\app.py
```

Use the browser URL printed by Streamlit. Do not launch
[app.py](src/agent_desk/ui/app.py) with plain Python.

1. Enter a question and select **Run**.
2. Review the generated goal, sub-questions, and outline. Select **Edit** to
   change them, then **Approve and run**.
3. The supervisor executes the plan through the specialist workers. If it
   requests a replan, the new plan returns to the approval screen.
4. Read the answer, numbered references, Sources, supporting findings, and
   compliance result.
5. Approve the answer or start a new question. Answer approval only marks the
   answer approved in the UI; it does not publish or export it.

The UI displays locally available filing years. It uses `InMemorySaver` and a
thread ID for interrupt/resume, and retains the evidence register in Streamlit
session state. This is not durable storage: a page reload or server restart
loses the session's paused workflow.

Example question:

> Compare Microsoft's and Alphabet's operating margins over the last three
> fiscal years, and tell me what changed in their risk factors.

## Run from the terminal

Set `QUESTION` in [main.py](src/agent_desk/main.py), then run:

```powershell
python src\agent_desk\main.py
```

This runs the **team workflow**, not the earlier standalone researcher. It
builds the graph without a checkpointer, so there is no human approval pause.
The package's [__main__.py](src/agent_desk/__main__.py) delegates to the same
runner; use the command above for direct execution from the project root.

## Workflow

The active graph is defined in [workflow.py](src/agent_desk/agents/workflow.py),
with shared state in [team_state.py](src/agent_desk/agents/team_state.py):

```text
Question -> Research lead -> Plan approval (UI only) -> Supervisor
                                                      |
                          +---------------------------+-------------------+
                          |                           |                   |
                     Researcher                     Quant              Risk-diff
                          |                           |                   |
                          +---------------------------+-------------------+
                                                      |
                                           Results back to supervisor

Supervisor -> REPLAN -> Research lead -> approval again (UI)
Supervisor -> FINISH -> Writer -> Critic -> END
                         ^         |
                         +---------+  Fail: up to 2 revisions
```

The specialist branches are alternatives, not parallel execution. The supervisor
dispatches a task, reads the worker result, and chooses the next action.

| Component | Responsibility |
| --- | --- |
| [Research lead](src/agent_desk/agents/research_lead_agent.py) | Creates the goal, ordered sub-questions, and answer outline. |
| [Supervisor](src/agent_desk/agents/supervisor_agent.py) | Routes tasks, evaluates progress, and requests replanning or finishing. |
| [Researcher](src/agent_desk/agents/researcher_agent.py) | Retrieves narrative passages; also has Company Facts tools. |
| [Quant](src/agent_desk/agents/quant_agent.py) | Retrieves XBRL observations and uses Python for arithmetic. |
| [Risk-diff](src/agent_desk/agents/risk_diff_agent.py) | Compares local Item 1A sections across two fiscal years. |
| Writer in [workflow.py](src/agent_desk/agents/workflow.py) | Synthesizes findings with citations and no new arithmetic. |
| [Compliance critic](src/agent_desk/agents/compliance_critic.py) | Checks the draft and reports issues for revision. |

Quant output with unknown evidence IDs is retried once; a second failure is
reported to the supervisor. Worker exceptions are also reported to it.
The initial state permits up to two replans; the runners use a graph recursion
limit of 50.

The older [coordinator_agent.py](src/agent_desk/agents/coordinator_agent.py) and
[langgraph_workflow.py](src/agent_desk/agents/langgraph_workflow.py) remain in the
repository, but are not the active team execution path.

## Filings and retrieval

1. Edit `SPECS` in
   [filling_download.py](src/agent_desk/utils/filling_download.py) and run:

   ```powershell
   python src\agent_desk\utils\filling_download.py
   ```

   The downloader uses SEC submissions and archives, saves HTML under
   `data\filings\<company>\<year>\`, and skips an existing target file.
   The year is taken from the filing's report-period end date.

2. Select the intended operation in `main()` in
   [create_embeddings.py](src/agent_desk/utils/create_embeddings.py) and run:

   ```powershell
   python src\agent_desk\utils\create_embeddings.py
   ```

   `create_all_embeddings()` rebuilds the combined index;
   `create_company_embeddings(name)` replaces one company's chunks while
   retaining the others. The file also exposes company/all-index deletion
   operations. Choose the operation explicitly before running the script.

[filing_parser.py](src/agent_desk/rag/filing_parser.py) extracts Item-labelled
passages with BeautifulSoup. The index builder splits them into 1,000-character
chunks with 150-character overlap, embeds with
`sentence-transformers/all-MiniLM-L6-v2`, and stores a combined FAISS index in
[data/faiss_index](data/faiss_index/). The embedding model is downloaded from
Hugging Face on first use.

Chunks carry `company`, `year`, `item`, `source`, and `start_index` metadata.
The start index is relative to the parsed passage, not the complete filing.
[search_filing](src/agent_desk/tools/rag_tools.py) performs vector similarity
search with optional company/year filters. A missing index raises an error;
search never builds embeddings automatically. Rebuild affected embeddings after
adding or replacing filings.

Local coverage is discovered from HTML files, not hardcoded in the planner.
Having a local filing does not guarantee that it is correctly labelled or that
the FAISS index has been rebuilt to include it.

Retrieval currently flattens tables to text. It does not preserve structured
tables, use hybrid search or reranking, or implement retrieval-level query
decomposition. Planner sub-questions are separate from that retrieval feature.

## Tools and caches

### SEC Company Facts

[edgar_tools.py](src/agent_desk/tools/edgar_tools.py) exposes
`list_edgar_companies`, `list_company_facts`, and `get_company_fact`.
These runtime tools use only the SEC XBRL Company Facts API; unlike the
downloader, they do not call submissions or filing archives.

The local directory contains Apple, Microsoft, and Alphabet. Fact-list and
fact-lookup tools accept other valid CIKs; the directory is not company
discovery. Results retain values, units, periods, fiscal-year information,
forms, filing dates, and accession numbers. Input and request errors are
returned explicitly as structured JSON.

Successful responses are cached by CIK under
[data/edgar_cache/companyfacts](data/edgar_cache/companyfacts/).
Pass `force_refresh=True` to request fresh API data.

### Python arithmetic

[run_python](src/agent_desk/tools/sandbox_tools.py) executes calculations through
[python_sandbox.py](src/agent_desk/sandbox/python_sandbox.py). It validates an
allowed Python subset, restricts imports and builtins, and runs a child process
with a default five-second timeout and a 4,000-character output cap.

Network-capable imports and file access are blocked at the Python restriction
layer. This is **not an OS-enforced security boundary** or a safe service for
arbitrary untrusted code. Child-process memory is not limited on Windows.

### Risk comparison

[compare_risk_factors](src/agent_desk/tools/risk_tools.py) reads both local
Item 1A sections, extracts structured risks, and returns added, removed, and
materially changed disclosures with quotes and passage IDs.
[risk_compare.py](src/agent_desk/rag/risk_compare.py) uses candidate matching and
model verification; unavailable local years produce an explicit error.

[risk_extract.py](src/agent_desk/rag/risk_extract.py) caches each company/year's
structured extraction under [data/risk_cache](data/risk_cache/). Its fingerprint
includes passage IDs/text, extraction prompts, configured model name, and quote
length setting. A matching cache skips extraction model calls, but the HTML
is still parsed and the comparison still runs.

The cache stores structured risks, not complete passage text or final
comparisons. Empty results are not cached. Remove a specific company/year cache
file to force that extraction to refresh. Caching is enabled by default; set
`AGENT_DESK_RISK_CACHE=0` to bypass it. Evaluation runs set this switch from
their `risk_extraction` cache configuration. Cached runs can still take minutes;
runtime depends on the plan, model latency, and revisions.

## Evidence, citations, and compliance review

[evidence.py](src/agent_desk/evidence.py) records tool observations in a
code-side, per-run register:

| ID | Evidence |
| --- | --- |
| `F1`, `F2`, ... | Reported XBRL facts. |
| `P1`, `P2`, ... | Exact retrieved passage text and metadata. |
| `D1`, `D2`, ... | Successful Python code/output and inferred input references. |
| `microsoft-2024-1A-71`, etc. | Existing Item 1A passage IDs used by risk comparison. |

The register is separate from graph checkpoints. Workers cite these IDs; the
writer keeps them in the draft. Writer output is capped at 3,000 tokens, with
token-limit truncation treated as a review issue. Code also caps recognized
multi-ID citation groups at three IDs using positional selection.

[citations.py](src/agent_desk/citations.py) converts answer citations to numbered
references for UI display and produces source descriptions. It does not rewrite
the stored draft or final answer. Supporting findings retain their raw IDs.

The critic checks:

- Recognized numeric expressions against cited XBRL facts or calculation outputs.
- Cited search-passage claims against their text using a separate LLM judge.
- Wording using phrase rules and an LLM judge, including return promises,
  investment recommendations, and price targets.
- Missing evidence IDs, unfinished evidence references, and reported writer
  truncation.

A failing draft returns to the writer for at most **two revisions** (three drafts
total). If issues remain, the answer is still returned with an explicit
unresolved-issues warning. Without an active register, the review is marked
not checked rather than passed.

**A passing review is not a guarantee of correctness or completeness.**
Risk-only citations are checked for existence but their final paraphrases are
not semantically rejudged by the critic. Numeric matching and calculation-input
provenance are heuristic, not rigorous unit/sign/year validation. Figures from
table cells are not independently verified. There is no check ensuring every
planned comparison appears in the final answer, nor a judge for every uncited
textual claim.

## Models and LangSmith tracing

Models are configured in [llm.py](src/agent_desk/llm/llm.py) through OpenRouter:

| Setting | Model |
| --- | --- |
| `TOOL_MODEL` | `meta-llama/llama-3.3-70b-instruct` |
| `FAST_MODEL` | `meta-llama/llama-3.1-8b-instruct` |
| `JUDGE_MODEL` | `openai/gpt-4o-mini` |

The writer uses the tool model; claim and wording judges use the separate judge
model. Model availability depends on the OpenRouter account and its guardrails.

The terminal [main.py](src/agent_desk/main.py) wraps the team run in
`tracing_context`, with project, an `agent-desk` tag, and question metadata.
Its explicit `enabled` value is determined by the presence of
`LANGSMITH_API_KEY`: a set key enables terminal tracing even if
`LANGSMITH_TRACING=false`. To run that entry point untraced, remove or unset the
tracing key.

Automatic instrumentation covers LangGraph nodes, LangChain tools, and model
calls. Plain Python helpers do not get their own spans without additional
instrumentation. The UI has no explicit tracing wrapper, but global
`LANGSMITH_TRACING=true` can also enable automatic library tracing there.

No endpoint URL is needed for the default US LangSmith service. Set
`LANGSMITH_ENDPOINT` for another region or a self-hosted endpoint. Authenticated
trace upload has not been verified as part of this implementation.
Traces can include questions, prompts, tool outputs, and answers; enable tracing
only when sending that content to the configured service is appropriate.

## Tests

```powershell
python -m pytest tests -q
```

[pytest.ini](pytest.ini) adds the source directory to the Python import path.
Existing [unit tests](tests/unit_tests/) cover retrieval/parsing, EDGAR tools,
sandbox restrictions, risk comparison and extraction caching, supervisor
retries, and mocked plan-approval/UI behavior.

Automated tests do not prove live model quality. Dedicated regression coverage
for several newer evidence/critic behaviors and final-answer coverage checking
remains incomplete.

## Project structure

```text
.
|-- data/                       Local filings, FAISS index, and caches
|-- documents/                  Capstone reference documents
|-- notebooks/                  Lesson references
|-- src/agent_desk/
|   |-- agents/                 Lead, supervisor, specialists, writer/critic graph
|   |-- llm/                    OpenRouter model factories
|   |-- rag/                    Parsing, retrieval, risk extraction/comparison
|   |-- sandbox/                Restricted Python calculations
|   |-- tools/                  LangChain tools
|   |-- ui/                     Streamlit application
|   |-- utils/                  Download and embedding maintenance scripts
|   |-- evidence.py             Per-run evidence register
|   |-- citations.py            Numbered UI references and source descriptions
|   |-- main.py                 Terminal team runner and tracing context
|   `-- __main__.py             Delegates to main()
|-- tests/                      Automated tests
|-- .env.example                Configuration template
|-- pytest.ini
|-- requirements.txt
|-- README.md
`-- README copy.md              This current implementation guide
```

## Remaining limitations

- The target of 10-15 companies across two sectors with three years each is not
  complete; local filing coverage and indexed coverage must be checked separately.
- Structured table preservation, hybrid search, reranking, and retrieval query
  decomposition are not implemented.
- Runtime EDGAR tools do not yet expose general filing-list or section-fetch
  operations.
- Final-answer plan coverage is not enforced, and critic checks have the
  limitations described above.
- No persistent checkpointer, long-term analyst memory, publishing portal, or
  runtime budget enforcement is implemented.
