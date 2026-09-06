"""Pytest configuration: per-opcode vector run tracking and terminal summary.

The SingleStepTests/z80 runner in ``tests/test_z80.py`` parametrizes one test
per per-opcode JSON vector file and, inside that test, executes all 1000
cases.  This module supplies the bookkeeping that turns those per-file test
results into a per-opcode pass/fail report:

* :data:`VECTOR_RESULTS` -- a plain dict keyed by vector file name holding
  ``{"passed", "failed", "not_implemented", "total", "error"}`` counters.
* the session-scoped :func:`vector_results` fixture -- tests update this dict
  as they run (also on failure, via ``try/finally``), so the summary reflects
  every file that was attempted.
* :func:`pytest_terminal_summary` -- prints the per-opcode table after the
  whole session, followed by grand totals.
"""

from __future__ import annotations

import pytest

#: Per-file counters, keyed by the vector JSON file name
#: (e.g. ``"dd cb __ 06.json"``).  Mutated by ``tests/test_z80.py`` through the
#: ``vector_results`` fixture; read by :func:`pytest_terminal_summary`.
VECTOR_RESULTS: dict[str, dict[str, int | str | None]] = {}


@pytest.fixture(scope="session")
def vector_results() -> dict[str, dict[str, int | str | None]]:
    """Session-scoped dict that per-opcode vector tests update with results.

    The dict is keyed by vector file name; each value has ``passed``,
    ``failed``, ``not_implemented``, ``total`` and ``error`` keys.  A test
    must record its file even when it fails, so the terminal summary below
    covers every file that was attempted.
    """
    return VECTOR_RESULTS


def _count_vector_files_by_outcome(
    results: dict[str, dict[str, int | str | None]],
) -> dict[str, int]:
    """Aggregate per-file outcomes: passed / not implemented (skipped) / failed.

    A file counts as "failed" if any of its cases produced a real register/RAM
    mismatch (``failed`` > 0); as "not implemented" if every case hit an
    unimplemented opcode; otherwise as "passed".  This mirrors
    ``tests/test_z80.py::_classify_vector_outcome``.
    """
    counts = {"passed": 0, "not_implemented": 0, "failed": 0}
    for stats in results.values():
        failed = int(stats.get("failed", 0) or 0)
        not_implemented = int(stats.get("not_implemented", 0) or 0)
        if failed:
            counts["failed"] += 1
        elif not_implemented:
            counts["not_implemented"] += 1
        else:
            counts["passed"] += 1
    return counts


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Print per-opcode pass/fail counts collected during the session."""
    if not VECTOR_RESULTS:
        return
    terminalreporter.write_sep("=", "Z80 vector per-opcode results")
    totals = {"passed": 0, "failed": 0, "not_implemented": 0, "total": 0}
    for name in sorted(VECTOR_RESULTS):
        stats = VECTOR_RESULTS[name]
        for key in totals:
            totals[key] += int(stats.get(key, 0) or 0)
        line = (
            f"{name}: {stats.get('passed', 0)} passed, {stats.get('failed', 0)} failed, "
            f"{stats.get('not_implemented', 0)} not implemented / "
            f"{stats.get('total', 0)} cases"
        )
        if stats.get("error"):
            line += f"  [{stats['error']}]"
        terminalreporter.write_line(line)
    terminalreporter.write_line(
        f"TOTAL: {totals['passed']} passed, {totals['failed']} failed, "
        f"{totals['not_implemented']} not implemented / {totals['total']} cases"
    )
    file_outcomes = _count_vector_files_by_outcome(VECTOR_RESULTS)
    terminalreporter.write_line(
        f"FILES: {file_outcomes['passed']} passed, "
        f"{file_outcomes['not_implemented']} not implemented (skipped), "
        f"{file_outcomes['failed']} failed"
    )
