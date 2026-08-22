"""Red-first witnesses for DD/FD absolute IX/IY word transfers."""

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
        pytest.fail(f"DD/FD absolute index transfer is not implemented: {exc}")


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
def test_prefixed_store_index_word_at_absolute_address(prefix: int) -> None:
    """DD/FD 22 stores the selected index word at nn in 20 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0xA65A
    cpu.iy = 0xB34C
    cpu.r = 0x3E
    cpu.f.byte = 0xA5
    cpu.q = 0xA5
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, 0x22, 0xFF, 0xFF]))

    value = cpu.ix if prefix == 0xDD else cpu.iy
    assert cpu.read_byte(0xFFFF) == (value & 0xFF)
    assert cpu.read_byte(0x0000) == (value >> 8)
    assert cpu.ix == 0xA65A
    assert cpu.iy == 0xB34C
    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0x2004
    assert cpu.r == 0x40
    assert cpu.wz == 0x0000
    assert tstates == 20


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
def test_prefixed_load_index_word_from_absolute_address(prefix: int) -> None:
    """DD/FD 2A loads the selected index word from nn in 20 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0xA65A
    cpu.iy = 0xB34C
    cpu.r = 0x3E
    cpu.f.byte = 0xA5
    cpu.q = 0xA5
    cpu.wz = 0xBEEF
    cpu.write_byte(0xFFFF, 0x12)
    cpu.write_byte(0x0000, 0x34)

    tstates = _run(cpu, bytes([prefix, 0x2A, 0xFF, 0xFF]))

    assert cpu.ix == (0x3412 if prefix == 0xDD else 0xA65A)
    assert cpu.iy == (0x3412 if prefix == 0xFD else 0xB34C)
    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0x2004
    assert cpu.r == 0x40
    assert cpu.wz == 0x0000
    assert tstates == 20
