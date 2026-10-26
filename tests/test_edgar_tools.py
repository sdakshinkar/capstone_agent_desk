import json

import requests

from agent_desk import edgar_tools


def sample_company_facts():
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "val": 100,
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-10-31",
                                "start": "2024-09-29",
                                "end": "2025-09-27",
                                "accn": "0000320193-25-000079",
                            },
                            {
                                "val": 90,
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-11-01",
                                "start": "2023-10-01",
                                "end": "2024-09-28",
                                "accn": "0000320193-24-000123",
                            },
                        ]
                    },
                }
            }
        },
    }


def test_company_fact_cache_avoids_repeat_request(monkeypatch, tmp_path):
    monkeypatch.setattr(edgar_tools, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("SEC_USER_AGENT", "Agent Desk contact@example.org")
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return sample_company_facts()

    def fake_get(url, headers, timeout):
        calls.append((url, headers, timeout))
        return Response()

    monkeypatch.setattr(edgar_tools.requests, "get", fake_get)

    first, first_error = edgar_tools._fetch_company_facts("0000320193")
    second, second_error = edgar_tools._fetch_company_facts("0000320193")

    assert first_error is second_error is None
    assert first == second == sample_company_facts()
    assert len(calls) == 1
    assert calls[0][0].endswith("/CIK0000320193.json")
    assert calls[0][1]["User-Agent"] == "Agent Desk contact@example.org"


def test_missing_user_agent_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(edgar_tools, "CACHE_DIR", tmp_path)
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)

    data, error = edgar_tools._fetch_company_facts("0000320193")

    assert data is None
    assert "SEC_USER_AGENT" in error


def test_get_company_fact_filters_fiscal_year_and_keeps_filing_metadata(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(edgar_tools, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("SEC_USER_AGENT", "Agent Desk contact@example.org")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return sample_company_facts()

    monkeypatch.setattr(edgar_tools.requests, "get", lambda *args, **kwargs: Response())

    result = json.loads(
        edgar_tools.get_company_fact.invoke(
            {
                "cik": "320193",
                "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
                "fiscal_year": 2025,
                "unit": "USD",
            }
        )
    )

    assert result["ok"] is True
    assert len(result["observations"]) == 1
    assert result["observations"][0]["value"] == 100
    assert result["observations"][0]["form"] == "10-K"
    assert result["observations"][0]["accession_number"] == "0000320193-25-000079"


def test_invalid_cik_does_not_make_request(monkeypatch):
    def unexpected_request(*args, **kwargs):
        raise AssertionError("invalid CIK must not trigger a request")

    monkeypatch.setattr(edgar_tools.requests, "get", unexpected_request)
    result = json.loads(
        edgar_tools.list_company_facts.invoke({"cik": "not-a-cik"})
    )
    assert result["ok"] is False
    assert "cik" in result["error"]


def test_http_error_is_returned_explicitly(monkeypatch, tmp_path):
    monkeypatch.setattr(edgar_tools, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("SEC_USER_AGENT", "Agent Desk contact@example.org")

    def failed_request(*args, **kwargs):
        response = requests.Response()
        response.status_code = 403
        raise requests.HTTPError("403 Forbidden", response=response)

    monkeypatch.setattr(edgar_tools.requests, "get", failed_request)
    data, error = edgar_tools._fetch_company_facts("0000320193")

    assert data is None
    assert error is not None
    assert "request failed" in error
