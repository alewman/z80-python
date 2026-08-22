"""Smoke test verifying the pytest toolchain is wired up correctly.

This suite currently contains no emulator source; this placeholder test
proves that collection and execution work end to end so that future
emulator tests start from a verified, green baseline.
"""


def test_pytest_collects_and_runs() -> None:
    """Trivial test that must always pass when the runner executes."""
    assert 1 + 1 == 2
