"""Red-first witnesses for Q-sensitive SCF/CCF flag behavior."""

from __future__ import annotations

import pytest
from conftest import MemoryCPU


@pytest.mark.parametrize(
    ("opcode", "expected_preserved", "expected_flagged"),
    ((0x37, 0xED, 0xC5), (0x3F, 0xFC, 0xD4)),
)
@pytest.mark.parametrize("prefix", (None, 0xDD, 0xFD))
@pytest.mark.parametrize("q", (0, 0xED))
def test_scf_ccf_q_sensitive_xy_behavior(
    opcode: int,
    expected_preserved: int,
    expected_flagged: int,
    prefix: int | None,
    q: int,
) -> None:
    cpu = MemoryCPU()
    cpu.pc, cpu.r, cpu.a, cpu.f.byte, cpu.q, cpu.wz = 0x2000, 0x3E, 0, 0xED, q, 0xBEEF
    if prefix is not None:
        cpu.write_byte(cpu.pc, prefix)
        cpu.write_byte(cpu.pc + 1, opcode)
    else:
        cpu.write_byte(cpu.pc, opcode)

    assert cpu.decode_and_execute() == (8 if prefix is not None else 4)

    expected_f = expected_preserved if prefix is not None or not q else expected_flagged
    assert (cpu.pc, cpu.r, int(cpu.f), cpu.q, cpu.wz) == (
        0x2002 if prefix is not None else 0x2001,
        0x40 if prefix is not None else 0x3F,
        expected_f,
        expected_f,
        0xBEEF,
    )
