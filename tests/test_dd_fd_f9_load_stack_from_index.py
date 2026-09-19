"""Red-first witnesses for DD/FD LD SP,IX/IY."""

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
        pytest.fail(f"DD/FD LD SP,IX/IY is not implemented: {exc}")


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
def test_load_stack_pointer_from_selected_index(prefix: int) -> None:
    """DD/FD F9 loads SP from IX/IY without changing flags or WZ."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.sp = 0x4000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    cpu.r = 0x3E
    cpu.f.byte = 0xA5
    cpu.q = 0xA5
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, 0xF9]))

    assert cpu.sp == (0x1234 if prefix == 0xDD else 0x5678)
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert tstates == 10
