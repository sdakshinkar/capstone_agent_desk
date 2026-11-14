"""Shared state schema for the supervisor + specialist team."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

# Returned as the only item of a results update to empty the list (used when the plan is replaced).
RESET = "__reset_results__"


def accumulate_or_reset(current: list[str] | None, update: list[str]) -> list[str]:
    """Reducer for worker results: append new entries, or start over when the update is [RESET].

    Example: accumulate_or_reset(["a"], ["b"]) -> ["a", "b"]
             accumulate_or_reset(["a", "b"], [RESET]) -> []
    """
    if update == [RESET]:
        return []
    return (current or []) + update


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
    # Worker results accumulate (one entry per worker call) so repeat calls don't overwrite;
    # a replan empties them with [RESET] because the new plan starts from scratch.
    narrative: Annotated[list[str], accumulate_or_reset]
    facts: Annotated[list[str], accumulate_or_reset]
    risk: Annotated[list[str], accumulate_or_reset]
    # The writer's answer without the "Supporting findings" block; this is what the critic checks.
    draft: str
    # True when the writer's reply was cut off by the output limit; the critic then rejects it.
    draft_truncated: bool
    # Compliance loop: revisions done so far (the critic allows at most 2), the issues from the
    # latest check (the writer's brief for a revision) and whether the latest draft passed.
    revision: int
    critic_issues: list[dict]
    critic_passed: bool | None  # None: the critic did not run (no evidence register)
    final_answer: str
