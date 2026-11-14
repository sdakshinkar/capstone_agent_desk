import os
import sys
from pathlib import Path

from langsmith import tracing_context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_desk.agents.langgraph_workflow import run_langgraph_workflow
from agent_desk.agents.workflow import run_team_workflow
from agent_desk.guardrails import app_hooks as guard

QUESTION1 = "What was Apple's operating income in the latest fiscal year?"
QUESTION2 = (
    "According to Apple's 10-K, what supply chain risks does the company "
    "describe in its Risk Factors?"
)

QUESTION3 = (
    "Compare Microsoft’s and Alphabet’s operating margins over the last three fiscal years, "
    "and tell me what changed in their risk factors."
)

# The question main() runs, and the one that is traced.
QUESTION = QUESTION3


# Tracing is on when LANGSMITH_API_KEY is set (in .env or the environment); it is forced off
# otherwise, so a stray LANGSMITH_TRACING=true without a key does not produce failed uploads.
# The project comes from LANGSMITH_PROJECT.
def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        with tracing_context(
            enabled=bool(os.getenv("LANGSMITH_API_KEY")),
            project_name=os.getenv("LANGSMITH_PROJECT", "agent-desk"),
            tags=["agent-desk"],
            metadata={"question": QUESTION},
        ):
            # print(run_langgraph_workflow(QUESTION))
            guard.enable_by_default()  # guardrails on unless AGENT_DESK_DEFENCES=off
            print(guard.run_guarded(QUESTION, run_team_workflow))
        return 0
    except Exception as exc:  # pragma: no cover - debugger path
        print(f"Workflow failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
