"""Red-first witnesses for DD/FD LD index-high/index-low,B/C/D/E."""

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
        pytest.fail(f"DD/FD load index byte from register is not implemented: {exc}")


_CASES = (
    (0x60, 0x11F3),
    (0x61, 0x22F3),
    (0x62, 0x33F3),
    (0x63, 0x44F3),
    (0x68, 0x0F11),
    (0x69, 0x0F22),
    (0x6A, 0x0F33),
    (0x6B, 0x0F44),
)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "expected"), _CASES)
def test_prefixed_load_index_byte_from_register(prefix: int, opcode: int, expected: int) -> None:
    """DD/FD 60-6B writes only the selected IX/IY high or low byte."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x0FF3
    cpu.iy = 0x0FF3
    cpu.b = 0x11
    cpu.c = 0x22
    cpu.d = 0x33
    cpu.e = 0x44
    cpu.r = 0x3E
    cpu.f.byte = 0xA5
    cpu.q = 0xA5
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, opcode]))

    assert cpu.ix == (expected if prefix == 0xDD else 0x0FF3)
    assert cpu.iy == (expected if prefix == 0xFD else 0x0FF3)
    assert (cpu.b, cpu.c, cpu.d, cpu.e) == (0x11, 0x22, 0x33, 0x44)
    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert tstates == 8
