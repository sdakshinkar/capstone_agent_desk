"""Company-name normalisation used by the filing search and the risk tools (no network)."""

import pytest

from agent_desk.companies import normalize_company
from agent_desk.rag import filing_rag, risk_section


@pytest.mark.parametrize("name, folder", [
    ("jpmorgan chase", "jpmorgan"),        # the name C2 actually used in eval case t03
    ("JPMorgan Chase & Co.", "jpmorgan"),
    ("JPM", "jpmorgan"),
    ("jpmorgan", "jpmorgan"),
    ("Bank of America Corporation", "bank_of_america"),
    ("bank_of_america", "bank_of_america"),
    ("The Goldman Sachs Group, Inc.", "goldman_sachs"),
    ("Meta Platforms, Inc.", "meta"),
    ("Google", "alphabet"),
    ("Amazon.com, Inc.", "amazon"),
    ("Apple Inc.", "apple"),
    ("Mastercard Incorporated", "mastercard"),
    ("  Microsoft Corporation ", "microsoft"),
])
def test_known_names_map_to_folder_names(name, folder):
    assert normalize_company(name) == folder


def test_unknown_names_stay_unknown():
    # Not mapped to a covered company, so the caller still reports "no filings for tesla".
    assert normalize_company("Tesla, Inc.") == "tesla"
    assert normalize_company("Morgan Stanley") == "morgan_stanley"


def test_search_filter_uses_the_index_name():
    assert filing_rag._metadata_filter("jpmorgan chase", 2025) == {"company": "jpmorgan", "year": "2025"}


def test_risk_lookup_accepts_an_alias():
    path = risk_section.find_filing("JPMorgan Chase & Co.", 2025)
    assert path.parent.parent.name == "jpmorgan"
    with pytest.raises(FileNotFoundError, match="No filings for company 'tesla'"):
        risk_section.find_filing("Tesla", 2025)
