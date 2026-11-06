"""Shared state schema for the supervisor + specialist team."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class TeamState(TypedDict):
    question: str
    messages: Annotated[list, add_messages]
    next: str
    task: str
    plan: dict
    plan_step: int
    replan_count: int
    max_replans: int
    replan_reason: str
    narrative: str
    facts: str
    risk: str
    final_answer: str
