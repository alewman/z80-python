"""Red-first witnesses for ED interrupt-mode instruction aliases."""

from __future__ import annotations

import pytest
from conftest import MemoryCPU


@pytest.mark.parametrize(
    ("opcode", "mode"),
    (
        (0x46, 0),
        (0x4E, 0),
        (0x66, 0),
        (0x6E, 0),
        (0x56, 1),
        (0x76, 1),
        (0x5E, 2),
        (0x7E, 2),
    ),
)
def test_ed_interrupt_mode_aliases_select_mode_without_other_changes(
    opcode: int, mode: int
) -> None:
    cpu = MemoryCPU()
    cpu.pc, cpu.r, cpu.f.byte, cpu.q, cpu.wz, cpu.im = 0x2000, 0x3E, 0xC5, 0xC5, 0xBEEF, 2
    cpu.write_byte(cpu.pc, 0xED)
    cpu.write_byte(cpu.pc + 1, opcode)

    assert cpu.decode_and_execute() == 8

    assert (cpu.pc, cpu.r, int(cpu.f), cpu.q, cpu.wz, cpu.im) == (
        0x2002,
        0x40,
        0xC5,
        0,
        0xBEEF,
        mode,
    )
