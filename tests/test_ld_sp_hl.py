"""Red-first witness for ordinary LD SP,HL."""

from __future__ import annotations

from conftest import MemoryCPU


def test_ld_sp_hl_copies_pair_without_changing_flags_or_wz() -> None:
    cpu = MemoryCPU()
    cpu.pc, cpu.r, cpu.h, cpu.l, cpu.sp = 0x2000, 0x3E, 0xA6, 0x5A, 0x1234
    cpu.f.byte, cpu.q, cpu.wz = 0xC5, 0xC5, 0xBEEF
    cpu.write_byte(cpu.pc, 0xF9)

    assert cpu.decode_and_execute() == 6

    assert (cpu.pc, cpu.r, cpu.sp, int(cpu.f), cpu.q, cpu.wz) == (
        0x2001,
        0x3F,
        0xA65A,
        0xC5,
        0,
        0xBEEF,
    )
