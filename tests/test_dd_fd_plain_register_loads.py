"""Red-first witnesses for prefix-ignored DD/FD ordinary register loads."""

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
        pytest.fail(f"DD/FD-prefixed ordinary register load is not implemented: {exc}")


_REGISTERS = ((0, "b"), (1, "c"), (2, "d"), (3, "e"), (7, "a"))
_CASES = tuple(
    (0x40 | (destination << 3) | source, destination_name, source_name)
    for destination, destination_name in _REGISTERS
    for source, source_name in _REGISTERS
)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "destination", "source"), _CASES)
def test_prefixed_plain_register_load_ignores_index_prefix(
    prefix: int, opcode: int, destination: str, source: str
) -> None:
    """DD/FD B/C/D/E/A transfers retain IX/IY and take eight T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    cpu.b = 0x11
    cpu.c = 0x22
    cpu.d = 0x33
    cpu.e = 0x44
    cpu.a = 0x77
    expected = getattr(cpu, source)
    cpu.r = 0x3E
    cpu.f.byte = 0xA5
    cpu.q = 0xA5
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, opcode]))

    assert getattr(cpu, destination) == expected
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert tstates == 8
