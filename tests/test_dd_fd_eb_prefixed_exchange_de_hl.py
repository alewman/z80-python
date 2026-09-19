"""Red-first witnesses for prefix-ignored DD/FD EX DE,HL."""

from __future__ import annotations

import pytest
from conftest import MemoryCPU


def _run(cpu: MemoryCPU, opcode_bytes: bytes) -> int:
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(f"DD/FD-prefixed EX DE,HL is not implemented: {exc}")


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
def test_prefixed_exchange_de_hl_ignores_index_prefix(prefix: int) -> None:
    """DD/FD EB exchanges DE and HL, retaining IX/IY and adding four T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.d = 0x12
    cpu.e = 0x34
    cpu.h = 0x56
    cpu.l = 0x78
    cpu.ix = 0x9ABC
    cpu.iy = 0xDEF0
    cpu.r = 0x3E
    cpu.f.byte = 0xA5
    cpu.q = 0xA5
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, 0xEB]))

    assert (cpu.d, cpu.e) == (0x56, 0x78)
    assert (cpu.h, cpu.l) == (0x12, 0x34)
    assert cpu.ix == 0x9ABC
    assert cpu.iy == 0xDEF0
    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert tstates == 8
