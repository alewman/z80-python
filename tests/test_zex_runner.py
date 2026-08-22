"""Unit tests for the minimal CP/M boundary used by ZEXDOC and ZEXALL."""

from __future__ import annotations

import pytest

from validation.zex import ZexRunError, ZexRunner


def test_runner_handles_bdos_character_output_then_warm_boot() -> None:
    program = bytes((0x0E, 2, 0x1E, ord("A"), 0xCD, 5, 0, 0xC3, 0, 0))
    runner = ZexRunner(program)

    result = runner.run()

    assert result.output == "A"
    assert result.instructions == 4
    assert result.t_states == 41
    assert runner.cpu.read_byte(0x0006) | (runner.cpu.read_byte(0x0007) << 8) == 0xF000


def test_runner_handles_bdos_dollar_terminated_string_output() -> None:
    program = bytes((0x0E, 9, 0x11, 0x0B, 1, 0xCD, 5, 0, 0xC3, 0, 0, ord("O"), ord("K"), 36))

    result = ZexRunner(program).run()

    assert result.output == "OK"


def test_runner_rejects_unsupported_bdos_requests() -> None:
    program = bytes((0x0E, 1, 0xCD, 5, 0))

    with pytest.raises(ZexRunError, match="BDOS function 1"):
        ZexRunner(program).run()


def test_runner_rejects_non_terminating_programs() -> None:
    program = bytes((0xC3, 0, 1))

    with pytest.raises(ZexRunError, match="within 5 instructions"):
        ZexRunner(program).run(max_instructions=5)  # noqa: W292