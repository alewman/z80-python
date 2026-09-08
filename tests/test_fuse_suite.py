"""FUSE's Z80 core test set, an emulator-derived oracle with six known divergences.

Run ``python scripts/fetch_fuse_tests.py`` to fetch the pinned release
(FUSE 1.6.0, GPL-2.0) before enabling these tests. Every case is compared
on registers, MEMPTR, I, R, the flip-flops, IM, the halted flag, the
T-state total, and the memory it lists; bus events are outside this core's
claim and are not compared.

Six cases disagree with the hardware-derived oracles this core follows.
They are pinned as strict xfails so a change on either side is noticed:

* ``76``: FUSE leaves PC on the HALT opcode while halted; SingleStepTests
  ``76.json`` advances it past the opcode, as this core does.
* ``edb2_1``, ``edb3_1``, ``edba_1``, ``edbb_1``: an interrupted INIR /
  OTIR / INDR / OTDR iteration. FUSE 1.6.0 expects MEMPTR = BC +/- 1 and the
  pre-2021 flags; SingleStepTests encodes MEMPTR = PC + 1 and the corrected
  PV/H/X/Y for a repeating iteration, and z80test 1.2a's ``z80memptr``
  ("Fixed CRCs of interrupted INIR and INDR") captured the same from real
  silicon. See ``_io.py``, ``_post_in_o_r``.
* ``edb9_2``: an interrupted CPDR iteration. FUSE 1.6.0 does not take X/Y
  from the rewound PC's high byte; SingleStepTests does. See ``_blocks.py``,
  ``_block_repeat``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from validation.fuse_runner import load_suite, run_case

_FUSE_DIR = Path(__file__).resolve().parents[1] / "validation" / "fuse_data"

KNOWN_DIVERGENCES = {
    "76": "FUSE keeps PC on the HALT opcode; SingleStepTests 76.json advances it",
    "edb2_1": "interrupted INIR: FUSE 1.6.0 predates the MEMPTR = PC+1 and flag findings",
    "edb3_1": "interrupted OTIR: FUSE 1.6.0 predates the MEMPTR = PC+1 and flag findings",
    "edb9_2": "interrupted CPDR: FUSE 1.6.0 does not take X/Y from the rewound PC",
    "edba_1": "interrupted INDR: FUSE 1.6.0 predates the MEMPTR = PC+1 and flag findings",
    "edbb_1": "interrupted OTDR: FUSE 1.6.0 predates the MEMPTR = PC+1 and flag findings",
}


def _suite():
    if not (_FUSE_DIR / "tests.in").is_file():
        return []
    return load_suite(_FUSE_DIR)


_SUITE = _suite()


@pytest.mark.skipif(not _SUITE, reason="run scripts/fetch_fuse_tests.py to enable the FUSE suite")
@pytest.mark.parametrize(
    ("case", "expected"),
    [
        pytest.param(
            case,
            expected,
            id=case.name,
            marks=(
                pytest.mark.xfail(reason=KNOWN_DIVERGENCES[case.name], strict=True)
                if case.name in KNOWN_DIVERGENCES
                else ()
            ),
        )
        for case, expected in _SUITE
    ],
)
def test_fuse_case_matches(case, expected) -> None:
    differences = run_case(case, expected)
    assert not differences, f"{case.name}: " + "; ".join(differences)


def test_suite_has_the_pinned_size() -> None:
    if not _SUITE:
        pytest.skip("run scripts/fetch_fuse_tests.py to enable the FUSE suite")
    assert len(_SUITE) == 1356
    assert set(KNOWN_DIVERGENCES) <= {case.name for case, _ in _SUITE}
