"""Red-first witnesses for the remaining prefix-ignored DD/FD base forms."""

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
        pytest.fail(f"DD/FD-prefixed basic control form is not implemented: {exc}")


def _setup(cpu: MemoryCPU) -> None:
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    cpu.r = 0x3E
    cpu.wz = 0xBEEF
    cpu.f.byte = 0xC5
    cpu.q = 0xC5


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
def test_prefixed_nop_ignores_index_prefix(prefix: int) -> None:
    """DD/FD NOP affects no state beyond PC and R and takes eight T-states."""
    cpu = MemoryCPU()
    _setup(cpu)

    tstates = _run(cpu, bytes([prefix, 0x00]))

    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert int(cpu.f) == 0xC5
    assert cpu.q == 0
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 8


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
def test_prefixed_exchange_af_with_alternate_ignores_index_prefix(prefix: int) -> None:
    """DD/FD EX AF,AF' swaps only the AF register pair in eight T-states."""
    cpu = MemoryCPU()
    _setup(cpu)
    cpu.a, cpu.f.byte, cpu.af_ = 0xA6, 0x5A, 0x1234

    tstates = _run(cpu, bytes([prefix, 0x08]))

    assert (cpu.a, int(cpu.f), cpu.af_) == (0x12, 0x34, 0xA65A)
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert cpu.q == 0
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 8


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "expected"), ((0x01, 0x1234), (0x11, 0x1234), (0x31, 0x1234)))
def test_prefixed_immediate_pair_loads_ignore_index_prefix(
    prefix: int, opcode: int, expected: int
) -> None:
    """DD/FD LD BC/DE/SP,nn keeps IX/IY and costs 14 T-states."""
    cpu = MemoryCPU()
    _setup(cpu)

    tstates = _run(cpu, bytes([prefix, opcode, 0x34, 0x12]))

    assert cpu._read_pair((opcode >> 4) & 0x03) == expected
    assert int(cpu.f) == 0xC5
    assert cpu.q == 0
    assert cpu.pc == 0x2004
    assert cpu.r == 0x40
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 14


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("initial_b", "expected_b", "taken"), ((1, 0, False), (2, 1, True)))
def test_prefixed_djnz_ignores_index_prefix(
    prefix: int, initial_b: int, expected_b: int, taken: bool
) -> None:
    """DD/FD DJNZ decrements B without modifying flags and adds four T-states."""
    cpu = MemoryCPU()
    _setup(cpu)
    cpu.b = initial_b

    tstates = _run(cpu, bytes([prefix, 0x10, 0xFD]))

    assert cpu.b == expected_b
    assert int(cpu.f) == 0xC5
    assert cpu.q == 0
    assert cpu.pc == (0x2000 if taken else 0x2003)
    assert cpu.r == 0x40
    assert cpu.wz == (0x2000 if taken else 0xBEEF)
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == (17 if taken else 12)
