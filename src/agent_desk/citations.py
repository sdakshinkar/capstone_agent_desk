"""Turn the evidence tags in a note into numbered references for display.

The drafted note carries tags such as [F1], [D3] and [microsoft-2024-1A-71] so the compliance
critic can check it. A reader should not see those; this replaces each tag with a number ([1],
[2], ...) and describes what each number refers to, using the run's evidence register.
"""

from __future__ import annotations

from typing import TypedDict

from .agents.compliance_critic import _TAG_RE
from .evidence import Register

FACT_PASSAGE_CHARS = 200
GROUP_PASSAGE_CHARS = 110


# One numbered reference: ids are the evidence ids the tag held, text says what they are.
class Source(TypedDict):
    number: int
    ids: list[str]
    text: str


def _amount(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    return f"{value:,}" if isinstance(value, int) else f"{value:,.2f}"


def _brief_fact(record: dict) -> str:
    return f"{record.get('label', record.get('concept', ''))} ({record.get('end', '?')}) {_amount(record.get('value'))} {record.get('unit', '')}".strip()


def _passage_line(record: dict, chars: int) -> str:
    text = " ".join(str(record.get("text", "")).split())
    if len(text) > chars:
        text = text[:chars].rstrip() + "..."
    where = ", ".join(str(record[k]) for k in ("company", "year", "item") if record.get(k))
    return f"{where}: \"{text}\"" if where else f"\"{text}\""


def _describe(record_id: str, register: Register, chars: int = FACT_PASSAGE_CHARS) -> str:
    """One evidence id in words. Example: "Microsoft Corp, Operating Income (Loss), 2024-07-01 to
    2025-06-30: 128,528,000,000 USD (10-K, accession 0000950170-25-100235)"."""
    record = register.get(record_id)
    if record is None:
        return f"{record_id}: not in the evidence register"
    if record_id in register.facts:
        return (
            f"{record.get('entity', '')}, {record.get('label', record.get('concept', ''))}, "
            f"{record.get('start', '?')} to {record.get('end', '?')}: "
            f"{_amount(record.get('value'))} {record.get('unit', '')} "
            f"({record.get('form', '?')}, accession {record.get('accession_number', '?')})"
        )
    if record_id in register.calcs:
        inputs = "; ".join(_brief_fact(register.facts[i]) for i in record["inputs"] if i in register.facts)
        line = f"Calculation {record['code']!r} printed {record['output'].strip()!r}"
        if inputs:
            line += f", from {inputs}"
        if record["unmatched"]:
            line += f" (also used numbers not tied to a fact: {', '.join(record['unmatched'])})"
        return line
    return _passage_line(record, chars)


def _describe_group(ids: list[str], register: Register) -> str:
    if len(ids) == 1:
        return _describe(ids[0], register)
    shown = [_describe(i, register, GROUP_PASSAGE_CHARS) for i in ids[:2]]
    more = f" ... and {len(ids) - 2} more" if len(ids) > 2 else ""
    return f"{len(ids)} sources, e.g. " + "; ".join(shown) + more


def number_references(text: str, register: Register | None) -> tuple[str, list[Source]]:
    """Replace each evidence tag in text with a number and return the numbered sources.

    Numbers follow first appearance and a tag that appears again keeps its number. Brackets that
    are not evidence tags are left alone. Without a register the text is returned unchanged.

    Example: "Margin 45.6% [D1] on $281.7B [F2]; again [D1]." gives
    ("Margin 45.6% [1] on $281.7B [2]; again [1].", [Source 1 (D1), Source 2 (F2)])
    """
    if register is None:
        return text, []

    numbers: dict[tuple[str, ...], int] = {}
    sources: list[Source] = []

    def replace(match) -> str:
        ids = tuple(i.strip() for i in match.group(1).split(","))
        if ids not in numbers:
            numbers[ids] = len(sources) + 1
            sources.append(Source(number=numbers[ids], ids=list(ids), text=_describe_group(list(ids), register)))
        return f"[{numbers[ids]}]"

    return _TAG_RE.sub(replace, text), sources
