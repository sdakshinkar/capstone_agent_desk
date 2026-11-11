"""Find numbers in an answer and match them against XBRL truth (no LLM).

An answer may write the same value in many ways: "$245.1 billion", "245,122 million",
"$245,122,000,000", "245.12B". extract_numbers() turns each into a value in base units (dollars,
percent points or plain numbers) and remembers how precisely it was written, so "$4.2 billion"
matches 4,224,000,000 (it is that value rounded to one decimal) but "$4.5 billion" does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SCALES = {
    "trillion": 1e12, "tn": 1e12, "t": 1e12,
    "billion": 1e9, "bn": 1e9, "b": 1e9,
    "million": 1e6, "mn": 1e6, "mm": 1e6, "m": 1e6,
    "thousand": 1e3, "k": 1e3,
}

# A number, optionally followed by a scale word or a percent sign.
_NUMBER = re.compile(
    r"(?<![\w.])(?P<neg>[-−])?\$?\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<suffix>%|percent\b|trillion\b|billion\b|million\b|thousand\b|tn\b|bn\b|mn\b|mm\b|[tbmk]\b)?",
    re.IGNORECASE,
)


@dataclass
class Number:
    value: float  # base units: dollars, percent points, or a plain number
    tolerance: float  # half of the last written digit, in the same units
    is_percent: bool
    raw: str


def extract_numbers(text: str) -> list[Number]:
    found: list[Number] = []
    for m in _NUMBER.finditer(text):
        digits = m.group("num")
        suffix = (m.group("suffix") or "").lower()
        base = float(digits.replace(",", ""))
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        step = 10 ** -decimals  # size of the last written digit
        is_percent = suffix in {"%", "percent"}
        scale = 1.0 if is_percent or not suffix else SCALES[suffix]
        if m.group("neg"):
            base = -base
        found.append(
            Number(
                value=base * scale,
                tolerance=step * scale / 2,
                is_percent=is_percent,
                raw=m.group(0).strip(),
            )
        )
    return found


def matches(number: Number, truth: float, *, percent: bool) -> bool:
    """True if `number` is `truth` written at the precision the answer used."""
    if number.is_percent != percent:
        return False
    if percent:
        # Rounding to the written precision, but never looser than half a percentage point.
        tol = min(max(number.tolerance, 0.06), 0.5)
    else:
        # Allow the written precision, plus 0.5% for answers that round sloppily.
        tol = max(number.tolerance, abs(truth) * 0.005)
    return abs(number.value - truth) <= tol + 1e-9


def find_value(numbers: list[Number], accepted: list[float], *, percent: bool) -> Number | None:
    """Return the first answer number that matches any accepted truth value."""
    for number in numbers:
        if any(matches(number, value, percent=percent) for value in accepted):
            return number
    return None
