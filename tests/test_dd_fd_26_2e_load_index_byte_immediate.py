"""Red-first witnesses for DD/FD LD index-high/index-low,n."""

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
        pytest.fail(f"DD/FD immediate index-byte load is not implemented: {exc}")


_CASES = ((0x26, 0xA5F3), (0x2E, 0x0FA5))


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "expected"), _CASES)
def test_prefixed_load_immediate_into_index_byte(prefix: int, opcode: int, expected: int) -> None:
    """DD/FD 26/2E writes n only into the selected IX/IY high or low byte."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x0FF3
    cpu.iy = 0x0FF3
    cpu.r = 0x3E
    cpu.f.byte = 0x5A
    cpu.q = 0x5A
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, opcode, 0xA5]))

    assert cpu.ix == (expected if prefix == 0xDD else 0x0FF3)
    assert cpu.iy == (expected if prefix == 0xFD else 0x0FF3)
    assert int(cpu.f) == 0x5A
    assert cpu.q == 0
    assert cpu.pc == 0x2003
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert tstates == 11
