"""Red-first witness for the FD-prefixed SBC A,A (FD 9F) form."""

from __future__ import annotations

import pytest
from conftest import MemoryCPU


def _run(cpu: MemoryCPU, opcode_bytes: bytes) -> int:
    """Place the instruction at PC and execute the intended FD 9F form."""
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(f"FD-prefixed SBC A,A is not implemented: {exc}")


def test_fd_9f_prefixed_sbc_a_a() -> None:
    """FD 9F ignores FD: SBC A,A preserves IX/IY and costs 8 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    cpu.a = 0x00
    cpu.r = 0x3E
    cpu.f.byte = 0x01
    cpu.q = 0x01
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([0xFD, 0x9F]))

    assert cpu.a == 0xFF
    assert int(cpu.f) == 0xBB
    assert cpu.q == 0xBB
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 8
