"""Red-first witnesses for prefix-ignored DD/FD stack and exchange forms."""

from __future__ import annotations

import pytest

from z80_python import Z80CPU


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
        pytest.fail(f"DD/FD-prefixed stack or exchange form is not implemented: {exc}")


def _setup(cpu: MemoryCPU) -> None:
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    cpu.sp = 0x4000
    cpu.r = 0x3E
    cpu.wz = 0xBEEF


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize("opcode", (0xD1, 0xF1), ids=("de", "af"))
def test_prefixed_pop_ignores_index_prefix(prefix: int, opcode: int) -> None:
    """DD/FD POP DE/AF keeps IX/IY and adds the prefix fetch cost."""
    cpu = MemoryCPU()
    _setup(cpu)
    cpu.d, cpu.e = 0xA6, 0x5A
    cpu.a, cpu.f.byte = 0xB3, 0xC5
    cpu.q = 0xC5
    cpu.write_byte(cpu.sp, 0x12)
    cpu.write_byte(cpu.sp + 1, 0x34)

    tstates = _run(cpu, bytes([prefix, opcode]))

    assert (cpu.d, cpu.e) == ((0x34, 0x12) if opcode == 0xD1 else (0xA6, 0x5A))
    assert (cpu.a, int(cpu.f)) == ((0x34, 0x12) if opcode == 0xF1 else (0xB3, 0xC5))
    assert cpu.q == 0
    assert cpu.sp == 0x4002
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 14


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize("opcode", (0xD5, 0xF5), ids=("de", "af"))
def test_prefixed_push_ignores_index_prefix(prefix: int, opcode: int) -> None:
    """DD/FD PUSH DE/AF keeps IX/IY and adds the prefix fetch cost."""
    cpu = MemoryCPU()
    _setup(cpu)
    cpu.d, cpu.e = 0xA6, 0x5A
    cpu.a, cpu.f.byte = 0xB3, 0xC5
    cpu.q = 0xC5

    tstates = _run(cpu, bytes([prefix, opcode]))

    value = 0xA65A if opcode == 0xD5 else 0xB3C5
    assert cpu.read_byte(0x3FFE) == (value & 0xFF)
    assert cpu.read_byte(0x3FFF) == (value >> 8)
    assert int(cpu.f) == 0xC5
    assert cpu.q == 0
    assert cpu.sp == 0x3FFE
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 15


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
def test_prefixed_exx_ignores_index_prefix(prefix: int) -> None:
    """DD/FD EXX swaps ordinary and alternate BC/DE/HL in eight T-states."""
    cpu = MemoryCPU()
    _setup(cpu)
    cpu.b, cpu.c = 0x12, 0x34
    cpu.d, cpu.e = 0x56, 0x78
    cpu.h, cpu.l = 0x9A, 0xBC
    cpu.bc_ = 0xDEF0
    cpu.de_ = 0x1357
    cpu.hl_ = 0x2468
    cpu.f.byte = 0xC5
    cpu.q = 0xC5

    tstates = _run(cpu, bytes([prefix, 0xD9]))

    assert (cpu.b, cpu.c, cpu.d, cpu.e, cpu.h, cpu.l) == (0xDE, 0xF0, 0x13, 0x57, 0x24, 0x68)
    assert (cpu.bc_, cpu.de_, cpu.hl_) == (0x1234, 0x5678, 0x9ABC)
    assert int(cpu.f) == 0xC5
    assert cpu.q == 0
    assert cpu.sp == 0x4000
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 8
