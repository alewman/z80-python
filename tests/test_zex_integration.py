"""Optional full-program ZEXDOC/ZEXALL integration gates.

The GPL-licensed upstream binaries are intentionally not vendored.  Download
zexdoc.com and zexall.com from https://github.com/agn453/ZEXALL and set
``Z80_PYTHON_ZEX_DIR`` to their directory to enable these long-running tests.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from validation.zex import ZexRunner

_ZEX_DIR = (
    Path(os.environ["Z80_PYTHON_ZEX_DIR"])
    if "Z80_PYTHON_ZEX_DIR" in os.environ
    else None
)


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.parametrize("program_name", ("zexdoc.com", "zexall.com"))
def test_zex_exerciser_completes_without_crc_errors(program_name: str) -> None:
    """The authoritative long-sequence exercisers must report their own success."""
    if _ZEX_DIR is None:
        pytest.skip("set Z80_PYTHON_ZEX_DIR to enable ZEXDOC/ZEXALL integration tests")
    program = _ZEX_DIR / program_name
    if not program.is_file():
        pytest.skip(f"missing upstream ZEX program: {program}")

    result = ZexRunner.from_file(program).run(max_instructions=10_000_000_000)

    assert result.passed, result.output
