"""Red-first witnesses for DD/FD LD B/C/D/E,index-high/index-low."""

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
        pytest.fail(f"DD/FD load from index byte is not implemented: {exc}")


_CASES = (
    (0x44, "b", 0x0F),
    (0x45, "b", 0xF3),
    (0x4C, "c", 0x0F),
    (0x4D, "c", 0xF3),
    (0x54, "d", 0x0F),
    (0x55, "d", 0xF3),
    (0x5C, "e", 0x0F),
    (0x5D, "e", 0xF3),
)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "register", "expected"), _CASES)
def test_prefixed_load_register_from_index_byte(
    prefix: int, opcode: int, register: str, expected: int
) -> None:
    """DD/FD 44-5D uses only the selected IX/IY high or low byte."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x0FF3
    cpu.iy = 0x0FF3
    cpu.b = 0x11
    cpu.c = 0x22
    cpu.d = 0x33
    cpu.e = 0x44
    cpu.h = 0x55
    cpu.l = 0x66
    cpu.a = 0x77
    cpu.r = 0x3E
    cpu.f.byte = 0xA5
    cpu.q = 0xA5
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, opcode]))

    assert getattr(cpu, register) == expected
    assert cpu.ix == 0x0FF3
    assert cpu.iy == 0x0FF3
    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert tstates == 8
