"""Per-run register of the evidence behind an answer: XBRL facts, filing passages, calculations.

Tools record what they return here and hand the model a short id (F1, P1, D1). The compliance
critic later checks the draft against these records, so the checks never depend on text the
model retyped.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from threading import Lock
from typing import Any

# Scale factors a model may apply when it copies a dollar value into a calculation
# (88,523,000,000 written as 88523 in millions).
_SCALES = (1, 1e3, 1e6, 1e9)
# Literals that appear in almost every calculation and say nothing about the source.
_TRIVIAL_LITERALS = {0.0, 1.0, 100.0}
_NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def _numbers_in(text: str) -> list[float]:
    """Numbers written in text, thousands separators removed.

    Example: _numbers_in("print(88,523 / 211915 * 100)") -> [88523.0, 211915.0, 100.0]
    """
    numbers = []
    for token in _NUMBER_RE.findall(text):
        try:
            numbers.append(float(token.replace(",", "")))
        except ValueError:
            continue
    return numbers


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


class Register:
    """The records of one run. Ids are F<n> for facts, P<n> for passages, D<n> for calculations."""

    def __init__(self) -> None:
        self.facts: dict[str, dict[str, Any]] = {}
        self.passages: dict[str, dict[str, Any]] = {}
        self.calcs: dict[str, dict[str, Any]] = {}
        self._fact_ids: dict[tuple, str] = {}
        self._passage_ids: dict[tuple, str] = {}
        self._lock = Lock()

    def add_fact(self, record: dict[str, Any]) -> str:
        """Store one XBRL observation and return its id; the same observation keeps its id.

        The record needs cik, concept, unit, value, start, end and accession_number.
        """
        key = tuple(
            record.get(name)
            for name in ("cik", "taxonomy", "concept", "unit", "start", "end", "accession_number")
        )
        with self._lock:
            if key in self._fact_ids:
                return self._fact_ids[key]
            fact_id = f"F{len(self.facts) + 1}"
            self.facts[fact_id] = {"id": fact_id, **record}
            self._fact_ids[key] = fact_id
            return fact_id

    def add_passage(
        self, text: str, metadata: dict[str, Any], passage_id: str | None = None
    ) -> str:
        """Store one filing passage and return its id.

        Pass passage_id to store the passage under an id the caller already has; otherwise the
        next P<n> is used. The same passage keeps its id.
        """
        key = (passage_id, metadata.get("company"), metadata.get("year"), metadata.get("item"), text)
        with self._lock:
            if key in self._passage_ids:
                return self._passage_ids[key]
            new_id = passage_id or f"P{len(self.passages) + 1}"
            self.passages[new_id] = {"id": new_id, "text": text, **metadata}
            self._passage_ids[key] = new_id
            return new_id

    def add_calc(self, code: str, output: str) -> str:
        """Store one calculation and return its id.

        inputs lists the facts (and earlier calculations) whose values appear in the code;
        unmatched lists the numbers in the code that match no recorded value.
        """
        inputs: list[str] = []
        unmatched: list[str] = []
        with self._lock:
            known = [
                (fact_id, float(fact["value"]))
                for fact_id, fact in self.facts.items()
                if isinstance(fact.get("value"), (int, float))
            ]
            for calc_id, calc in self.calcs.items():
                known.extend((calc_id, number) for number in _numbers_in(calc["output"]))

            for literal in _numbers_in(code):
                match = next(
                    (
                        source
                        for source, value in known
                        if any(_same(literal * scale, value) for scale in _SCALES)
                    ),
                    None,
                )
                if match is not None:
                    if match not in inputs:
                        inputs.append(match)
                elif literal not in _TRIVIAL_LITERALS:
                    text = f"{literal:g}"
                    if text not in unmatched:
                        unmatched.append(text)

            calc_id = f"D{len(self.calcs) + 1}"
            self.calcs[calc_id] = {
                "id": calc_id,
                "code": code,
                "output": output,
                "inputs": inputs,
                "unmatched": unmatched,
            }
            return calc_id

    def get(self, record_id: str) -> dict[str, Any] | None:
        """The record for an id, or None if the id was never issued."""
        for records in (self.facts, self.passages, self.calcs):
            if record_id in records:
                return records[record_id]
        return None


_current: ContextVar[Register | None] = ContextVar("evidence_register", default=None)


def new_register() -> Register:
    """Start a register for the current run and make it the active one."""
    register = Register()
    _current.set(register)
    return register


def use_register(register: Register | None) -> None:
    """Make an existing register the active one (for example when a paused run resumes)."""
    _current.set(register)


def current_register() -> Register | None:
    """The active register, or None when no run has started one (tools then record nothing)."""
    return _current.get()
