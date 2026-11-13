"""Compliance critic: checks a drafted note against the evidence register before it is accepted.

The checks are plain code wherever code can decide. This file holds the number check, the
wording check (code rules plus an LLM judge) and the claim judge.
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

from ..evidence import Register
from ..llm.llm import get_judge_llm


# One problem found in a draft. type is the check that found it ("number"), text is the offending
# text, start is its position in the draft and detail says what is wrong.
class Issue(TypedDict):
    type: str
    text: str
    start: int
    detail: str


# An evidence id as the workers write it: F1 (fact), D1 (calculation) or a passage id such as
# "microsoft-2025-1A-37"; ids sit in square brackets right after the figure they support.
_ID = r"(?:[FDP]\d+|[a-z]+-\d{4}-\w+-\d+)"
_TAG_GROUP_RE = re.compile(rf"(?:\[{_ID}(?:\s*,\s*{_ID})*\]\s*)+")
_TAG_RE = re.compile(rf"\[({_ID}(?:\s*,\s*{_ID})*)\]")

_NUMBER_RE = re.compile(
    r"""
    (?P<dollar>\$)?\s?
    (?<![\w.])
    (?P<digits>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<decimals>\d+))?)
    \s?
    (?P<unit>%|(?i:trillion|billion|million|thousand)\b|[TBMK]\b)?
    (?![A-Za-z])
    """,
    re.VERBOSE,
)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])|\n")
_OUTPUT_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

_UNIT_SCALES = {"t": 1e12, "trillion": 1e12, "b": 1e9, "billion": 1e9, "m": 1e6, "million": 1e6,
                "k": 1e3, "thousand": 1e3}
# Without a unit word a figure may be dollars or thousands, millions or billions of them.
_ANY_SCALE = (1.0, 1e3, 1e6, 1e9)


def _close(shown: float, actual: float, decimals: int) -> bool:
    """True if actual rounds to shown at the number of decimals shown.

    Example: _close(128.5, 128.528, 1) -> True; _close(128.6, 128.528, 1) -> False
    """
    return abs(shown - actual) <= 0.5 * 10**-decimals + 1e-9 * max(1.0, abs(actual))


def _is_claim(match: re.Match[str]) -> bool:
    """True if the figure needs evidence: years and plain counts below 1000 do not.

    Example: "$5 billion", "45.6%", "128,528" and "1.5" need evidence; "2025" and "three or 12" do not.
    """
    if match["dollar"] or match["unit"] or match["decimals"] or "," in match["digits"]:
        return True
    value = float(match["digits"])
    return value >= 1000 and not 1990 <= value <= 2100


def _matches_fact(value: float, decimals: int, unit: str | None, fact_value: object) -> bool:
    if not isinstance(fact_value, (int, float)):
        return False
    actual = abs(float(fact_value))
    if unit == "%":
        return any(_close(value, actual * factor, decimals) for factor in (1, 100))
    scales = (_UNIT_SCALES[unit.lower()],) if unit else _ANY_SCALE
    return any(_close(value, actual / scale, decimals) for scale in scales)


def _matches_calc(value: float, decimals: int, unit: str | None, output: str) -> bool:
    for token in _OUTPUT_NUMBER_RE.findall(output):
        if unit == "%":
            options = (float(token), float(token) * 100)
            if any(_close(value, option, decimals) for option in options):
                return True
        elif _matches_fact(value, decimals, unit, float(token)):
            return True
    return False


def _tag_groups(text: str) -> list[tuple[int, int, list[str]]]:
    """Each run of id tags in the text as (start, end, ids).

    Example: "$1B [F1][F2]" gives [(5, 12, ["F1", "F2"])]
    """
    groups = []
    for group in _TAG_GROUP_RE.finditer(text):
        ids = [i.strip() for tag in _TAG_RE.findall(group[0]) for i in tag.split(",")]
        groups.append((group.start(), group.end(), ids))
    return groups


_UNFINISHED_TAG_RE = re.compile(rf"\[(?:[FDP]\d*(?![A-Za-z])|[a-z]+-\d{{4}}-\w)[^\]\[]*(?:\Z|(?=\[))")


def check_complete(draft: str) -> list[Issue]:
    """Flag an evidence tag that is opened but never closed, which means the text was cut off.

    Example: check_complete("Risks changed [microsoft-2024-1A-56, microsoft-2024-1A-57") gives
    one issue; "Risks changed [microsoft-2024-1A-56]." gives none.
    """
    return [
        Issue(type="truncated", text=match[0][:60], start=match.start(),
              detail="The note stops inside an unfinished reference, so it was cut off. "
                     "Write the whole note again, shorter.")
        for match in _UNFINISHED_TAG_RE.finditer(draft)
    ]


def unknown_ids(text: str, register: Register) -> list[str]:
    """Evidence ids written in square brackets in the text that the register never issued.

    Example: with F1 recorded, unknown_ids("45.6% [D1] of $128.5B [F1]", register) -> ["D1"]
    """
    cited = [i for _, _, ids in _tag_groups(text) for i in ids]
    return [i for i in dict.fromkeys(cited) if register.get(i) is None]


def check_numbers(draft: str, register: Register) -> list[Issue]:
    """Check every dollar amount, percentage and large figure in the draft against the register.

    Each figure must be followed, in its sentence, by the id of the fact (F) or calculation (D)
    it came from, and must equal that record's value at the precision shown. An empty list means
    the numbers pass.
    """
    issues: list[Issue] = []
    groups = _tag_groups(draft)
    # Ids hide from the number search (their digits are not figures) but keep their positions.
    masked = draft
    for start, end, _ in groups:
        masked = masked[:start] + " " * (end - start) + masked[end:]

    flagged_calcs: set[str] = set()
    for match in _NUMBER_RE.finditer(masked):
        if not _is_claim(match):
            continue
        text = draft[match.start() : match.end()].strip()
        start = match.start("dollar") if match["dollar"] else match.start("digits")
        value = float(match["digits"].replace(",", ""))
        decimals = len(match["decimals"] or "")
        unit = match["unit"]

        group = next((g for g in groups if g[0] >= match.end()), None)
        if group is None or _SENTENCE_END_RE.search(masked, match.end(), group[0]):
            issues.append(Issue(type="number", text=text, start=start,
                                detail="No evidence id follows this figure."))
            continue

        problems: list[str] = []
        supported = False
        for record_id in group[2]:
            record = register.get(record_id)
            if record is None:
                problems.append(f"{record_id} is not in the evidence register.")
            elif record_id.startswith("F"):
                if _matches_fact(value, decimals, unit, record.get("value")):
                    supported = True
                else:
                    problems.append(f"{record_id} has value {record.get('value')}, which does not match.")
            elif record_id.startswith("D"):
                if _matches_calc(value, decimals, unit, record["output"]):
                    supported = True
                    if record["unmatched"] and record_id not in flagged_calcs:
                        flagged_calcs.add(record_id)
                        issues.append(Issue(
                            type="number", text=record_id, start=start,
                            detail=f"{record_id} used numbers that are not recorded facts: "
                                   f"{', '.join(record['unmatched'])}."))
                else:
                    problems.append(f"{record_id} printed {record['output'].strip()!r}, which does not match.")
            else:
                problems.append(f"{record_id} is a filing passage; a figure needs a fact (F) or calculation (D).")
        if not supported:
            issues.append(Issue(type="number", text=text, start=start, detail=" ".join(problems)))
    return issues


# Wording rules: a note may report and compare, but must not promise returns or tell the reader
# what to do with a stock. Each rule is (what it catches, pattern); matching ignores case.
_WORDING_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("promise of returns", re.compile(
        r"\b(guarantee[sd]?|risk[- ]free(?! (?:rate|return|asset|security|interest))|no risk|can'?t lose"
        r"|sure to|certain to"
        r"|will (?:outperform|beat the market|soar|double|appreciate|deliver (?:strong )?returns))\b",
        re.IGNORECASE)),
    ("recommendation", re.compile(
        r"\b(we recommend|i recommend|recommend(?:s|ed)? (?:buying|selling|holding|that)"
        r"|(?:should|must|time to|advise to) (?:buy|sell|invest|hold)"
        r"|(?:buy|sell|hold|strong buy|overweight|underweight|outperform|underperform) rating"
        r"|(?:buy|sell|accumulate) (?:the )?(?:stock|shares)"
        r"|good investment|worth buying|attractive entry)\b",
        re.IGNORECASE)),
    ("price target or valuation call", re.compile(
        r"\b(price target|target price|fair value estimate|upside to|(?:is|are|looks?) (?:under|over)valued)\b",
        re.IGNORECASE)),
]


def check_wording(draft: str) -> list[Issue]:
    """Find promises of returns, recommendations and price targets in the draft.

    Example: check_wording("We recommend buying MSFT.") gives one issue for "We recommend"
    """
    issues: list[Issue] = []
    for rule, pattern in _WORDING_RULES:
        for match in pattern.finditer(draft):
            issues.append(Issue(type="wording", text=match[0], start=match.start(),
                                detail=f"Not allowed in a research note ({rule})."))
    return sorted(issues, key=lambda issue: issue["start"])


MAX_JUDGE_TOKENS = 1000
JUDGE_ATTEMPTS = 2


# One breach the judge reports; `quote` must be copied exactly from the draft and `category` must
# be one of the three prohibited kinds, so a worry that fits none of them has nowhere to go.
WORDING_CATEGORIES = ("promise of returns", "recommendation", "price target or valuation call")


class WordingFinding(TypedDict):
    quote: str
    category: Literal["promise of returns", "recommendation", "price target or valuation call"]
    reason: str


class WordingVerdict(TypedDict):
    violations: list[WordingFinding]


WORDING_JUDGE_PROMPT = """You are a compliance reviewer for equity research notes.
A note may report facts, calculate figures, describe risks and compare companies or years. It
must not do any of these three things:
1. promise or imply returns: "guaranteed", "will outperform", "can't lose", or any statement
   that the price will rise or that an investment is safe;
2. tell the reader what to do with a security: buy, sell, hold, accumulate, or give a rating;
3. give a price target, or say a stock is undervalued, overvalued, cheap or a bargain.

These are allowed and are not breaches:
- Reported figures and ratios: "operating margin was 45.6%", "revenue was $281.7B".
- Comparisons of companies or years: "Microsoft's margin was higher than Alphabet's", "margin
  rose from 41.8% to 45.6%".
- Descriptions of what a filing says about risks, regulation or strategy: "Alphabet added a
  risk related to financing", "the risk factor now covers AI regulation".
Do not flag text because a reader might draw an investment conclusion from it. Flag it only if
it clearly does one of the three things above.

For each breach give `quote` (the exact words copied from the note; do not fix spelling or
shorten them), `category` (one of the three above) and `reason`. If there are no breaches, return
an empty list. Return JSON only."""


def _find_quote(draft: str, quote: str) -> re.Match[str] | None:
    """Locate a quote in the draft, ignoring case and differences in spacing."""
    words = quote.split()
    if not words:
        return None
    pattern = r"\s+".join(re.escape(word) for word in words)
    return re.search(pattern, draft, re.IGNORECASE)


def judge_wording(draft: str, llm=None) -> list[Issue]:
    """Ask a model to find promises, advice and price calls that the phrase list misses.

    The model must quote the offending words; a quote that is not in the draft is dropped, so the
    judge cannot report a breach that is not there. If the judge cannot be reached the result is
    one "judge_error" issue, never an empty list, so a failed check does not pass the draft.
    """
    llm = llm or get_judge_llm(max_tokens=MAX_JUDGE_TOKENS)
    judge = llm.with_structured_output(WordingVerdict, method="json_schema", strict=True)

    problem = ""
    for _ in range(JUDGE_ATTEMPTS):
        try:
            verdict = judge.invoke([("system", WORDING_JUDGE_PROMPT), ("user", draft)])
        except Exception as exc:
            problem = f"{type(exc).__name__}: {str(exc)[:200]}"
            continue
        issues: list[Issue] = []
        for finding in (verdict or {}).get("violations", []):
            if finding.get("category") not in WORDING_CATEGORIES:
                continue
            match = _find_quote(draft, str(finding.get("quote", "")))
            if match:
                issues.append(Issue(type="wording", text=match[0], start=match.start(),
                                    detail=f"Not allowed in a research note ({finding['category']}): "
                                           f"{finding.get('reason', '')}"))
        return sorted(issues, key=lambda issue: issue["start"])
    return [Issue(type="judge_error", text="", start=0,
                  detail=f"The wording judge could not be run ({problem}).")]


MAX_CLAIMS_PER_CALL = 8
MAX_PASSAGE_CHARS = 3000
MAX_CLAIM_JUDGE_TOKENS = 1500


# The judge's answer for one claim: claim is the number it was given in the request.
class ClaimVerdict(TypedDict):
    claim: int
    verdict: Literal["supported", "partial", "unsupported"]
    reason: str


class ClaimVerdictList(TypedDict):
    verdicts: list[ClaimVerdict]


CLAIM_JUDGE_PROMPT = """You check claims in an equity research note against the filing passages
they cite. You get numbered claims; under each are the passages it cites, as [id] text.

For each claim decide, using only those passages:
- supported: the passages say what the claim says.
- partial: the passages support only part of the claim, or support a weaker or narrower claim.
- unsupported: the passages do not say it, or say something different.

Ignore figures followed by ids such as F1 or D1; they are checked elsewhere. Judge the meaning of
the claim, not its wording. Do not use outside knowledge. Give each claim a one-sentence reason.
Return one verdict per claim, using the claim's number. Return JSON only."""


def _is_passage_id(record_id: str) -> bool:
    return not re.fullmatch(r"[FD]\d+", record_id)


# Ids from search_filing look like P3. Risk-diff ids ("microsoft-2025-1A-37") come from
# compare_risk_factors, which already verified each finding against its passages.
def _is_search_passage_id(record_id: str) -> bool:
    return re.fullmatch(r"P\d+", record_id) is not None


def _claims(draft: str) -> list[tuple[int, str, list[str]]]:
    """Sentences of the draft that cite filing passages, as (start, sentence, passage ids).

    Example: "Azure demand depends on capacity [P3]. Margin was 45.6% [D1]." gives
    [(0, "Azure demand depends on capacity [P3].", ["P3"])]
    """
    claims = []
    start = 0
    for end in [m.start() for m in _SENTENCE_END_RE.finditer(draft)] + [len(draft)]:
        sentence = draft[start:end]
        ids = [i.strip() for tag in _TAG_RE.findall(sentence) for i in tag.split(",")]
        passage_ids = [i for i in dict.fromkeys(ids) if _is_passage_id(i)]
        if passage_ids:
            claims.append((start + len(sentence) - len(sentence.lstrip()), sentence.strip(), passage_ids))
        start = end
    return claims


def judge_claims(draft: str, register: Register, llm=None) -> list[Issue]:
    """Check every sentence that cites a filing passage against that passage's text.

    A cited id that is not a passage in the register is an issue without asking the model. Claims
    that cite risk-diff ids only are not judged: the comparison tool already verified them, and a
    claim that something was added or removed cannot be shown by quoting passages. The rest go
    to the judge in batches of MAX_CLAIMS_PER_CALL (a claim is judged against its search-passage
    ids); partial and unsupported verdicts become issues. If the judge cannot be reached or skips
    a claim, that is a "judge_error" issue, never a pass.
    """
    issues: list[Issue] = []
    checkable: list[tuple[int, str, list[str]]] = []
    for start, sentence, ids in _claims(draft):
        missing = [i for i in ids if register.passages.get(i) is None]
        if missing:
            issues.append(Issue(type="claim", text=sentence, start=start,
                                detail=f"{', '.join(missing)} is not a filing passage in the evidence register."))
            continue
        to_judge = [i for i in ids if _is_search_passage_id(i)]
        if to_judge:
            checkable.append((start, sentence, to_judge))
    if not checkable:
        return sorted(issues, key=lambda issue: issue["start"])

    llm = llm or get_judge_llm(max_tokens=MAX_CLAIM_JUDGE_TOKENS)
    judge = llm.with_structured_output(ClaimVerdictList, method="json_schema", strict=True)

    for first in range(0, len(checkable), MAX_CLAIMS_PER_CALL):
        batch = checkable[first : first + MAX_CLAIMS_PER_CALL]
        blocks = []
        for number, (_, sentence, ids) in enumerate(batch, start=1):
            passages = "\n".join(
                f"[{i}] {register.passages[i]['text'][:MAX_PASSAGE_CHARS]}" for i in ids
            )
            blocks.append(f"Claim {number}: {sentence}\nPassages:\n{passages}")

        verdicts: dict[int, ClaimVerdict] | None = None
        problem = ""
        for _ in range(JUDGE_ATTEMPTS):
            try:
                reply = judge.invoke([("system", CLAIM_JUDGE_PROMPT), ("user", "\n\n".join(blocks))])
            except Exception as exc:
                problem = f"{type(exc).__name__}: {str(exc)[:200]}"
                continue
            verdicts = {v["claim"]: v for v in (reply or {}).get("verdicts", [])}
            break

        for number, (start, sentence, _) in enumerate(batch, start=1):
            verdict = (verdicts or {}).get(number)
            if verdict is None:
                reason = problem or "the judge returned no verdict for this claim"
                issues.append(Issue(type="judge_error", text=sentence, start=start,
                                    detail=f"The claim judge could not check this claim ({reason})."))
            elif verdict["verdict"] != "supported":
                issues.append(Issue(type="claim", text=sentence, start=start,
                                    detail=f"{verdict['verdict'].capitalize()}: {verdict['reason']}"))
    return sorted(issues, key=lambda issue: issue["start"])


# The critic's answer: passed is True only when there are no issues of any kind, including a
# judge that could not be run.
class Verdict(TypedDict):
    passed: bool
    issues: list[Issue]


def _overlaps(a: Issue, b: Issue) -> bool:
    return a["start"] < b["start"] + len(b["text"]) and b["start"] < a["start"] + len(a["text"])


def critique(draft: str, register: Register, llm=None) -> Verdict:
    """Run every check on the draft and return the verdict with all issues in text order.

    Checks: figures against facts and calculations (code), claims against their passages (judge),
    and wording (phrase rules, then the judge). A judge breach that overlaps text the phrase rules
    already flagged is dropped, so one problem is reported once. llm is for tests; by default the
    judges use the judge model.
    """
    if not draft.strip():
        return Verdict(passed=False, issues=[
            Issue(type="number", text="", start=0, detail="The draft is empty.")])

    issues = check_complete(draft)
    issues += check_numbers(draft, register)
    issues += judge_claims(draft, register, llm)

    wording = check_wording(draft)
    issues += wording
    issues += [
        found for found in judge_wording(draft, llm)
        if found["type"] != "wording" or not any(_overlaps(found, seen) for seen in wording)
    ]

    issues.sort(key=lambda issue: issue["start"])
    return Verdict(passed=not issues, issues=issues)