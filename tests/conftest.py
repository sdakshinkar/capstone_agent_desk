import pytest

from agent_desk.evidence import use_register


@pytest.fixture(autouse=True)
def no_active_register():
    """Runs that start a register leave it active in this thread; start every test without one."""
    use_register(None)
    yield
    use_register(None)
