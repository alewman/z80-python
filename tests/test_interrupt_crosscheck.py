"""Optional interrupt-lifecycle cross-check against an independent Z80 core.

Run ``python scripts/fetch_interrupt_oracle.py`` first to fetch and build the
comparison oracle (superzazu/z80). See
:mod:`validation.interrupt_crosscheck` for what this is -- and, importantly,
is not -- evidence of.
"""

from __future__ import annotations

import pytest

from validation.interrupt_crosscheck import _LIBRARY, SCENARIOS, run_scenario

_KNOWN_ORACLE_BUGS = {
    "IM0 device-supplied RST 10h": (
        "superzazu/z80 double-counts the interrupt-acknowledge M1 cycle for "
        "IM 0: it increments R and charges 11 T-states for the ack in "
        "process_interrupts(), then calls its generic exec_opcode() to run "
        "the injected RST, which independently increments R and charges "
        "another 11 T-states as if freshly fetched. On real Z80 silicon the "
        "IM 0 acknowledge cycle *is* the fetch of the injected opcode -- one "
        "M1 cycle, one R increment -- which is what z80_python's "
        "_accept_maskable_interrupt does (single _inc_r(), 13 T-states "
        "total, matching docs/interrupt-lifecycle.md's own table). This is "
        "the oracle's bug, not z80_python's."
    ),
}


@pytest.mark.integration
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_interrupt_scenario_matches_independent_core(scenario) -> None:
    """Deliberately adversarial interrupt scenarios must match a second core."""
    if not _LIBRARY.is_file():
        pytest.skip("run scripts/fetch_interrupt_oracle.py to enable this cross-check")

    if scenario.name in _KNOWN_ORACLE_BUGS:
        pytest.xfail(_KNOWN_ORACLE_BUGS[scenario.name])

    result = run_scenario(scenario)

    assert result.matches, result.mismatches
