"""Red-first witnesses for DD/FD AND A,index-high/index-low forms."""

from __future__ import annotations

import pytest

from z80.cpu import Z80CPU


class MemoryCPU(Z80CPU):
    """Concrete Z80CPU backed by a flat 64 KiB bytearray."""

    def __init__(self) -> None:
        super().__init__()
        self.memory = bytearray(0x10000)

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        raise NotImplementedError("unit-test CPU does not model I/O ports")

    def write_port(self, addr: int, value: int) -> None:
        raise NotImplementedError("unit-test CPU does not model I/O ports")


def _run(cpu: MemoryCPU, opcode_bytes: bytes) -> int:
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(f"DD/FD-prefixed AND index-byte form is not implemented: {exc}")


_CASES = (
    (0xA4, 0x0FF3, 0x00, 0x54),
    (0xA5, 0x0FF3, 0xF0, 0xB4),
)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "index_value", "result", "flags"), _CASES)
def test_prefixed_and_a_index_byte(
    prefix: int, opcode: int, index_value: int, result: int, flags: int
) -> None:
    """DD/FD A4-A5 read only the selected IX/IY high or low byte."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    if prefix == 0xDD:
        cpu.ix = index_value
    else:
        cpu.iy = index_value
    cpu.a = 0xF0
    cpu.r = 0x3E
    cpu.f.byte = 0x01
    cpu.q = 0x01
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, opcode]))

    assert cpu.a == result
    assert int(cpu.f) == flags
    assert cpu.q == flags
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert cpu.ix == (index_value if prefix == 0xDD else 0x1234)
    assert cpu.iy == (index_value if prefix == 0xFD else 0x5678)
    assert tstates == 8
