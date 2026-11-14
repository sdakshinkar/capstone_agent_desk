"""Input and output guardrails for Agent Desk (rule-based, no extra model calls).

Designed from the brief's policy for an equity-research assistant, not from the red-team attack
texts:
  * scope: research on public filings only; no personal investment advice, no promises of
    returns, no help trading on non-public information or spreading false claims, no unrelated
    harmful tasks (phishing, credentials);
  * injection: requests that try to override instructions, change the assistant's role, reveal
    its prompt, or hide instructions in encoded text;
  * output: no buy/sell calls or price targets, no external links or images (exfiltration),
    nothing from a CONFIDENTIAL context block, no system-prompt text.

Interface used by rdayal_redteam (and usable by the app):
  check_input(question)          -> {"allowed": bool, "reason": str}
  check_output(answer, question) -> {"allowed": bool, "reason": str, "answer": str | None}

Known gaps (stated, not hidden): rules are English-only, so a request in another language is not
screened; a paraphrased injection can slip past patterns. A classifier model (for example Llama
Prompt Guard 2) is the next step.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any

# ---------------------------------------------------------------- input rules

_INJECTION = [
    r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|your|the)\b[^.\n]{0,20}\b(instructions?|rules|prompts?|guidelines|directions)\b",
    r"\byou are (no longer|now)\b",
    r"\b(pretend|act as if) (you are|to be)\b",
    r"\blet'?s role-?play\b|\brole-?play as\b",
    r"\b(jailbreak|developer mode|dan mode|unfiltered (assistant|model|mode))\b",
    r"\b(print|reveal|show|repeat|output)\b[^.\n]{0,40}\b(system prompt|your (instructions|prompt|rules)|hidden instructions)\b",
    r"\b(decode|decrypt)\b[^.\n]{0,40}\b(follow|execute|obey|do)\b",
]

_ADVICE_REQUEST = [
    r"\bshould i (buy|sell|short|invest|hold)\b",
    r"\b(how much|what (percentage|percent|share)) of my (savings|money|portfolio|salary)\b",
    r"\b(guarantee|guaranteed|promise)\b[^.\n]{0,60}\b(return|double|rise|profit|gain)",
    r"\b(give|tell) me (a|your) (buy|sell) (call|recommendation|signal)\b",
    r"\bprice target\b",
]

_MISUSE = [
    r"\b(non-public|nonpublic|insider|material non-public) (information|info|data)\b",
    r"\b(move|push|pump|dump|tank)\b[^.\n]{0,20}\b(the )?(stock )?price\b",
    r"\b(write|draft|compose)\b[^.\n]{0,60}\b(email|message|text)\b[^.\n]{0,80}\b(password|credentials|login|verify your account)\b",
]

_BASE64_BLOB = re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}")


def _first_match(patterns: list[str], text: str) -> str | None:
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return None


def _decoded_blobs(text: str) -> list[str]:
    out = []
    for blob in _BASE64_BLOB.findall(text):
        try:
            decoded = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if decoded.isprintable():
            out.append(decoded)
    return out


def check_input(question: str) -> dict[str, Any]:
    text = question or ""
    for label, patterns in (("prompt injection", _INJECTION),
                            ("personal investment advice is out of scope", _ADVICE_REQUEST),
                            ("misuse / out of scope", _MISUSE)):
        hit = _first_match(patterns, text)
        if hit:
            return {"allowed": False, "reason": f"{label}: {hit!r}"}
    for decoded in _decoded_blobs(text):  # hidden instructions in encoded text
        verdict = check_input(decoded)
        if not verdict["allowed"]:
            return {"allowed": False, "reason": f"encoded text -> {verdict['reason']}"}
        if re.search(r"\b(recommend|buy|sell|ignore|instruction)\b", decoded, re.IGNORECASE):
            return {"allowed": False, "reason": "encoded instruction in request"}
    return {"allowed": True, "reason": ""}


# --------------------------------------------------------------- output rules

_ADVICE_OUTPUT = [
    r"\bstrong (buy|sell)\b",
    r"\bprice target\b",
    r"\b(we|i) (recommend|suggest|advise) (buying|selling|that you (buy|sell)|investors (buy|sell))\b",
    r"\b(you|investors|clients) should (buy|sell|invest in|short)\b",
    r"\b(rated?|rating|upgrade[sd]?|downgrade[sd]?) (it |the stock )?(to )?(a )?(buy|sell|overweight|underweight|outperform|underperform)\b",
    r"\bguaranteed? (returns?|to (rise|double|grow))\b",
    r"\b(is|looks like) a (good |great |clear )?(buy|sell)\b",
    r"\b(will|is going to) double\b",
]

_LINK = re.compile(r"!?\[[^\]]*\]\((https?://[^)\s]+)\)|https?://[^\s)\"'>]+", re.IGNORECASE)
_ALLOWED_HOSTS = ("sec.gov",)

_PROMPT_MARKERS = [
    r"\byou are the (supervisor|research lead|writer)\b",
    r"\byou are a (quantitative|risk-diff|filings research)",
    r"\breturn only valid json\b",
    r"\bnever do their work yourself\b",
]

_CONFIDENTIAL_BLOCK = re.compile(r"\[[^\]]*confidential[^\]]*\](.*?)(\n\s*\n|\[request\]|$)", re.IGNORECASE | re.DOTALL)


def _confidential_terms(question: str) -> list[str]:
    """Words from any block the user marked CONFIDENTIAL: those must never appear in output."""
    terms: list[str] = []
    for m in _CONFIDENTIAL_BLOCK.finditer(question or ""):
        body = m.group(1)
        body = body.split(":", 1)[1] if ":" in body else body
        terms += [t for t in re.findall(r"[A-Za-z0-9.\-]{3,}", body)]
    return terms


def _strip_links(answer: str) -> tuple[str, int]:
    removed = 0

    def repl(m: re.Match) -> str:
        nonlocal removed
        url = m.group(1) or m.group(0)
        if any(h in url.lower() for h in _ALLOWED_HOSTS):
            return m.group(0)
        removed += 1
        return "[link removed]"

    return _LINK.sub(repl, answer), removed


def check_output(answer: str, question: str = "") -> dict[str, Any]:
    text = answer or ""
    hit = _first_match(_ADVICE_OUTPUT, text)
    if hit:
        return {"allowed": False, "reason": f"investment advice in answer: {hit!r}", "answer": None}
    hit = _first_match(_PROMPT_MARKERS, text)
    if hit:
        return {"allowed": False, "reason": f"system prompt text in answer: {hit!r}", "answer": None}
    leaked = [t for t in _confidential_terms(question) if re.search(rf"\b{re.escape(t)}\b", text)]
    if leaked:
        return {"allowed": False, "reason": f"confidential context in answer: {leaked}", "answer": None}
    cleaned, removed = _strip_links(text)
    reason = f"removed {removed} external link(s)" if removed else ""
    return {"allowed": True, "reason": reason, "answer": cleaned}


# Second layer (tool boundary). Imported last: it reuses _confidential_terms above.
from .tool_guards import check_code, install  # noqa: E402,F401
