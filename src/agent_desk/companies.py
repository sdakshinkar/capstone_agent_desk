"""Map the company names models write to the folder names the filings and index use.

Agents call tools with names such as "JPMorgan Chase", "jpmorgan chase & co.", "JPM" or
"Bank of America Corp", while data/filings/ and the search index use one lowercase folder name per
company ("jpmorgan", "bank_of_america"). Without this mapping a filtered search for
"jpmorgan chase" silently returns nothing, and a risk comparison reports that the company has no
filings. An unknown name is returned in folder style unchanged, so the caller's own "not found"
message still lists the companies that exist.

Example: normalize_company("JPMorgan Chase & Co.") -> "jpmorgan"
"""

from __future__ import annotations

import re

# Folder name -> other names and tickers a model may use (compared after _clean()).
_ALIASES: dict[str, tuple[str, ...]] = {
    "microsoft": ("msft",),
    "apple": ("aapl",),
    "alphabet": ("google", "googl", "goog"),
    "amazon": ("amazon com", "amzn"),
    "meta": ("meta platforms", "facebook", "fb"),
    "nvidia": ("nvda",),
    "jpmorgan": ("jpmorgan chase", "jp morgan", "jp morgan chase", "jpm", "chase"),
    "bank_of_america": ("bank of america", "bofa", "bac", "boa"),
    "goldman_sachs": ("goldman sachs", "goldman", "gs"),
    "mastercard": ("ma",),
}

# Legal-form words dropped before matching ("Apple Inc." -> "apple").
_SUFFIXES = {"inc", "incorporated", "corp", "corporation", "co", "company", "group", "the",
             "holdings", "plc", "ltd", "llc", "and", "subsidiaries"}

_LOOKUP = {alias: folder for folder, aliases in _ALIASES.items() for alias in (folder, *aliases)}
_LOOKUP.update({folder.replace("_", " "): folder for folder in _ALIASES})


def _clean(name: str) -> str:
    """Lowercase, '&' and punctuation to spaces, legal-form words removed."""
    words = re.sub(r"[^a-z0-9]+", " ", name.lower().replace("&", " and ")).split()
    return " ".join(w for w in words if w not in _SUFFIXES)


def normalize_company(name: str) -> str:
    """The folder name for a company name, alias or ticker; unknown names in folder style."""
    cleaned = _clean(name)
    if cleaned in _LOOKUP:
        return _LOOKUP[cleaned]
    return cleaned.replace(" ", "_") or name.strip().lower()
