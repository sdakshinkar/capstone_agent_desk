"""Shared state schema for the supervisor + specialist team."""

from __future__ import annotations

import operator
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
    # Worker results accumulate (one entry per worker call) so repeat calls don't overwrite.
    narrative: Annotated[list[str], operator.add]
    facts: Annotated[list[str], operator.add]
    risk: Annotated[list[str], operator.add]
    final_answer: str
