"""Opt-in CMOS OUT (C),0: 0xFF instead of the NMOS 0.

See docs/undocumented-behavior.md for the sourcing: reported (a test program run
on Game Gear hardware tells CMOS from NMOS this way), not hardware-captured here,
so it defaults off and must never affect the certified default behavior.
"""

from __future__ import annotations

from conftest import MemoryCPU


def _run_ed(second: int, *, cmos: bool, a: int = 0) -> list[tuple[int, int]]:
    cpu = MemoryCPU()
    cpu.cmos_out_c_zero = cmos
    cpu.pc, cpu.a, cpu.b, cpu.c = 0x1000, a, 0x12, 0xBE
    cpu.memory[0x1000:0x1002] = bytes((0xED, second))
    assert cpu.step() == 12
    return cpu.port_writes


def test_nmos_by_default() -> None:
    assert MemoryCPU().cmos_out_c_zero is False
    assert _run_ed(0x71, cmos=False) == [(0x12BE, 0x00)]  # OUT (C),0


def test_cmos_outputs_ff() -> None:
    assert _run_ed(0x71, cmos=True) == [(0x12BE, 0xFF)]


def test_cmos_leaves_out_c_r_alone() -> None:
    assert _run_ed(0x79, cmos=True, a=0x5A) == [(0x12BE, 0x5A)]  # OUT (C),A
