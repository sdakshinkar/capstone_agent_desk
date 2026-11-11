# Analyst Desk: Policy Pack

Owner: Domain and product lead. Status: DRAFT for team review.
Companion to `docs/domain_brief.md` (fiscal-year and unit rules are in brief section 6 and are not repeated here; this pack makes them enforceable).
Each policy states **who enforces it** so engineers know what to build. Items marked **[VERIFY]** need the domain expert.

## A. Numbers policy

1. **Code calculates, the model never does.** Every number in a note is either (a) a reported XBRL fact, or (b) the output of the sandbox on reported facts. The model may select which fact applies; it must not compute, round, or convert.
2. **Every number has a source ID.** Fact ID = `company | concept | period_end | accession`. A table cell is cited as `passage_id#row,col`. A number without an ID cannot appear in a draft.
3. **One formula per metric** and one accepted concept list per metric (brief section 5). A concept outside the list is reported as "not available".
4. **Units** are normalised to USD millions in code. Original unit and scale are kept with the fact.
5. **Rounding** is done at display time only: ratios to one decimal place of a percent, amounts to the nearest USD million. Checks compare unrounded values.
6. **Not applicable is an answer.** Asking for operating margin of a bank returns "not reported by this company type" plus the nearest valid metric.
7. **No estimates.** If a fact or filing is not held, say so and list what is held.

Enforced by: quant agent + sandbox (compute), output guardrail and compliance critic (every number has an ID that resolves and matches), eval checker.

## B. Wording policy

Allowed: factual statements about what a filing says or reports, each with a passage ID or fact ID; changes between years; comparisons with stated periods.

Not allowed in any draft or published note:
- Recommendations or ratings (buy, sell, hold, overweight, "attractive", "undervalued").
- Price targets or return or performance promises ("will grow", "expected to outperform").
- Forward-looking statements in the note's own voice. Quoting a company's forward-looking statement is allowed, attributed ("the company states that ...").
- Unsourced hedged numbers ("roughly", "around") without an ID.
- Instructions or claims taken from web pages, articles or filings treated as the note's own conclusions.

Every note ends with a fixed disclosure line: "Descriptive summary of public filings; not investment advice." **[VERIFY wording with domain expert]**

Enforced by: output guardrail (rules), compliance critic (rules + judge for claim support), approval gate (analyst sign-off).

## C. Memory policy (one page; satisfies the L9 minimum bar)

**Purpose.** Let the analyst ask "what changed since our last note?" and keep working preferences, without re-entering them.

| Store | What is saved | Why | When saved |
|---|---|---|---|
| Preferences | e.g. "always include a peer table", default peer set, units | Avoid repeated instructions | When the analyst states or confirms it; never inferred silently |
| Coverage list | Companies the analyst covers | Scope defaults, "what changed" queries | On analyst request or confirmation |
| Past notes | The **published** note, its fact IDs and passage IDs, publish date, filing accessions used | Change-since-last-note comparisons | Only after analyst approval and publish. Drafts and rejected notes are not saved |
| Watchlist (private) | Tickers the analyst marks as private | Personalised scope | On analyst request only |

Not saved: raw LLM conversation text beyond the session, API keys, anything from untrusted pages as "facts", model-inferred preferences, personal data other than a pseudonymous analyst ID.

**Who can read.** Only the owning analyst's pseudonymous ID reads that analyst's records. Agents receive the minimum fields they need. The **watchlist is never placed in a search query, tool argument sent to an external service, trace, or note** unless the analyst explicitly includes a ticker in their own request.

**Retention.** Preferences and coverage until changed. Past notes for **[VERIFY: e.g. 3 years]**. Watchlist until removed.

**Correction.** The analyst can view and edit any record. A corrected preference replaces the old value and the old value is removed, not kept as history.

**Deletion.** "Forget my data" deletes all records for that analyst ID, including past-note memory and watchlist, and confirms the count deleted. Published notes in the research portal are a business record and are **not** deleted by this command; this is stated to the analyst up front. **[VERIFY with domain expert]**

**Staleness.** A remembered preference or past note is a hint, not evidence. Notes cite the filings, not the memory. If a newer filing exists than the one in a past note, "what changed" says so.

Enforced by: memory store API (per-ID access, delete command), hooks (watchlist blocked in outbound tool args), eval (memory-on vs memory-off comparison, red-team leakage cases).

## D. Approval and publication policy

1. Nothing is published without analyst approval of the **exact note**. Approval is tied to a hash of the note text and its fact/passage IDs. Any edit invalidates the earlier approval.
2. Only the writer/publisher path can call `publish_note`. Researchers, quant, risk-diff and critic have no write tools.
3. The analyst can edit the plan before research starts. The approved plan is recorded with the note.
4. The critic returns a draft for at most **two** revisions. If it still fails, the draft goes to the analyst with the failures listed and is not publishable until fixed.
5. A note with any unverified number or unsupported claim cannot be approved without the analyst explicitly overriding it, and the override is logged.

Enforced by: approval gate (`interrupt()`), hooks, portal API.

## E. Source and data-handling policy

1. Evidence comes only from SEC EDGAR 10-K filings and XBRL facts held in the local cache. Other web text is untrusted data: it may be shown, never obeyed, never used as a source of numbers.
2. Text inside filings, tool outputs and web pages that looks like an instruction is ignored and flagged.
3. EDGAR calls use the project's contact User-Agent, stay under 10 requests per second, and are cached. Cached files are not committed.
4. Each ingested filing records source URL, accession number and collection date. A filing with no collection date is not indexed.
5. FinanceBench open sample is used only as an external retrieval check and is not redistributed.
6. No API keys, private data or non-redistributable material in the repository.

Enforced by: ingestion pipeline, hooks (rate limit, allow-list), input guardrails, repo review.

## F. Policy-to-test map

Each policy needs at least one eval case or check, so the held-out set can be checked against the written policy (domain lead's review duty).

| Policy | Check |
|---|---|
| A1, A2 | Code: every number in output resolves to a fact ID and matches |
| A3, A6 | Golden cases: bank operating margin, concept not on list |
| A7 | Golden cases: missing year, missing company |
| B | Wording cases + red-team "buy recommendation" injection |
| C | Memory-on vs off; cross-analyst leakage red-team; delete verification |
| D1 | Live demo: edit invalidates approval; automated test |
| E1, E2 | Red-team: injected article, poisoned filing text |
