"""Optional z80test hardware-oracle integration gates.

z80test's reference values come from a real 48K ZX Spectrum, not another
emulator. Run ``python scripts/fetch_z80test.py`` to fetch the pinned,
MIT-licensed release before enabling these tests.

Only ``z80memptr``, ``z80full``, and ``z80ccf`` are exercised: ``z80full``
subsumes ``z80doc``, ``z80flags``, and ``z80docflags`` (it is the same
register+flags sweep at the strictest setting), and ``z80ccfscr`` is a visual
CCF-pattern demo rather than a pass/fail check.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from validation.z80test_runner import Z80TestRunner

_Z80TEST_DIR = Path(__file__).resolve().parents[1] / "validation" / "z80test_data"


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.parametrize("program_name", ("z80memptr.tap", "z80full.tap", "z80ccf.tap"))
def test_z80test_program_reports_all_tests_passed(program_name: str) -> None:
    """Each hardware-derived z80test program must report its own clean sweep."""
    program = _Z80TEST_DIR / program_name
    if not program.is_file():
        pytest.skip("run scripts/fetch_z80test.py to enable z80test integration tests")

    result = Z80TestRunner.from_file(program).run()

    assert result.passed, result.output
