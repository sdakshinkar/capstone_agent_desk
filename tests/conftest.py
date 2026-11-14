import pytest

from agent_desk.evidence import use_register


@pytest.fixture(autouse=True)
def no_active_register():
    """Runs that start a register leave it active in this thread; start every test without one."""
    use_register(None)
    yield
    use_register(None)


@pytest.fixture(autouse=True)
def guardrail_switch_starts_unset():
    """The app switches the guardrails on by default (os.environ.setdefault). Give every test an
    unset switch and put it back afterwards, so one test's page run cannot turn it on for the next."""
    import os

    before = os.environ.pop("AGENT_DESK_DEFENCES", None)
    yield
    os.environ.pop("AGENT_DESK_DEFENCES", None)
    if before is not None:
        os.environ["AGENT_DESK_DEFENCES"] = before
