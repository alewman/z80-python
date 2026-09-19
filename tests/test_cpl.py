"""Red-first witnesses for CPL and prefix-ignored CPL."""

from __future__ import annotations

import pytest
from conftest import MemoryCPU


@pytest.mark.parametrize("prefix", (None, 0xDD, 0xFD))
def test_cpl_complements_a_preserves_szpvc_and_latches_result_flags(
    prefix: int | None,
) -> None:
    cpu = MemoryCPU()
    cpu.pc, cpu.r, cpu.a, cpu.f.byte, cpu.q, cpu.wz = 0x2000, 0x3E, 0x5A, 0xC5, 0xC5, 0xBEEF
    if prefix is not None:
        cpu.write_byte(cpu.pc, prefix)
        cpu.write_byte(cpu.pc + 1, 0x2F)
    else:
        cpu.write_byte(cpu.pc, 0x2F)

    assert cpu.decode_and_execute() == (8 if prefix is not None else 4)

    assert (cpu.pc, cpu.r, cpu.a, int(cpu.f), cpu.q, cpu.wz) == (
        0x2002 if prefix is not None else 0x2001,
        0x40 if prefix is not None else 0x3F,
        0xA5,
        0xF7,
        0xF7,
        0xBEEF,
    )
