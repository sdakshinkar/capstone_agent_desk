"""Shared state schema for the supervisor + specialist team."""

from __future__ import annotations

from typing import Literal, TypedDict


class Route(TypedDict):
    next: Literal["researcher_worker", "quant_worker", "risk_worker", "FINISH"]
    message: str


class TeamState(TypedDict):
    messages: list
    next: str
    task: str
    narrative: str
    facts: str
    risk: str
    final_answer: str
