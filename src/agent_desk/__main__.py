import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_desk.researcher_agent import run_researcher

QUESTION1 = "What was Apple's operating income in the latest fiscal year?"
QUESTION2 = (
    "According to Apple's 10-K, what supply chain risks does the company "
    "describe in its Risk Factors?"
)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run_researcher(QUESTION2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
