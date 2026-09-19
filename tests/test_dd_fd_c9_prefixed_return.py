"""Red-first witnesses for prefix-ignored DD/FD RET."""

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
        pytest.fail(f"DD/FD-prefixed RET is not implemented: {exc}")


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
def test_prefixed_return_ignores_index_prefix(prefix: int) -> None:
    """DD/FD C9 returns normally, retaining IX/IY and adding four T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.sp = 0x4000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    cpu.r = 0x3E
    cpu.f.byte = 0xA5
    cpu.q = 0xA5
    cpu.write_byte(0x4000, 0xEF)
    cpu.write_byte(0x4001, 0xBE)

    tstates = _run(cpu, bytes([prefix, 0xC9]))

    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0xBEEF
    assert cpu.sp == 0x4002
    assert cpu.wz == 0xBEEF
    assert cpu.r == 0x40
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 14
