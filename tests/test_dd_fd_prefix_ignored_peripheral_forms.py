"""Red-first witnesses for a larger DD/FD prefix-ignored base-instruction batch."""

from __future__ import annotations

import pytest

from z80.cpu import Z80CPU


class MemoryCPU(Z80CPU):
    """Concrete Z80CPU backed by flat memory and simple I/O ports."""

    def __init__(self) -> None:
        super().__init__()
        self.memory = bytearray(0x10000)
        self.ports: dict[int, int] = {}
        self.port_writes: list[tuple[int, int]] = []

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        return self.ports[addr & 0xFFFF]

    def write_port(self, addr: int, value: int) -> None:
        self.port_writes.append((addr & 0xFFFF, value & 0xFF))


def _run(cpu: MemoryCPU, opcode_bytes: bytes) -> int:
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(f"DD/FD-prefixed base instruction is not implemented: {exc}")


def _setup(cpu: MemoryCPU) -> None:
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    cpu.r = 0x3E
    cpu.f.byte = 0xA5
    cpu.q = 0xA5
    cpu.wz = 0xBEEF


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(
    ("opcode", "register"),
    ((0x06, "b"), (0x0E, "c"), (0x16, "d"), (0x1E, "e"), (0x3E, "a")),
)
def test_prefixed_immediate_register_loads_ignore_index_prefix(
    prefix: int, opcode: int, register: str
) -> None:
    """DD/FD LD r,n keeps the index registers and costs 11 T-states."""
    cpu = MemoryCPU()
    _setup(cpu)

    tstates = _run(cpu, bytes([prefix, opcode, 0xA6]))

    assert getattr(cpu, register) == 0xA6
    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0x2003
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 11


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(
    ("opcode", "pair", "loads_a", "expected_wz"),
    (
        (0x0A, 0x3456, True, 0x3457),
        (0x1A, 0x789A, True, 0x789B),
        (0x02, 0x3456, False, 0x5A57),
        (0x12, 0x789A, False, 0x5A9B),
    ),
)
def test_prefixed_pair_indirect_accumulator_transfers_ignore_index_prefix(
    prefix: int, opcode: int, pair: int, loads_a: bool, expected_wz: int
) -> None:
    """DD/FD LD A,(BC/DE) and LD (BC/DE),A retain their base behavior."""
    cpu = MemoryCPU()
    _setup(cpu)
    cpu.b, cpu.c = (pair >> 8) & 0xFF, pair & 0xFF
    if opcode in (0x1A, 0x12):
        cpu.d, cpu.e = (pair >> 8) & 0xFF, pair & 0xFF
    cpu.a = 0x5A
    cpu.write_byte(pair, 0xA6)

    tstates = _run(cpu, bytes([prefix, opcode]))

    assert cpu.a == (0xA6 if loads_a else 0x5A)
    assert cpu.read_byte(pair) == (0xA6 if loads_a else 0x5A)
    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == expected_wz
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 11


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize("opcode", (0x32, 0x3A), ids=("store", "load"))
def test_prefixed_absolute_accumulator_transfers_ignore_index_prefix(
    prefix: int, opcode: int
) -> None:
    """DD/FD LD (nn),A and LD A,(nn) keep ordinary absolute addressing."""
    cpu = MemoryCPU()
    _setup(cpu)
    cpu.a = 0x5A
    cpu.write_byte(0x3456, 0xA6)

    tstates = _run(cpu, bytes([prefix, opcode, 0x56, 0x34]))

    assert cpu.a == (0xA6 if opcode == 0x3A else 0x5A)
    assert cpu.read_byte(0x3456) == (0xA6 if opcode == 0x3A else 0x5A)
    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0x2004
    assert cpu.r == 0x40
    assert cpu.wz == (0x3457 if opcode == 0x3A else 0x5A57)
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 17


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize("opcode", (0xD3, 0xDB), ids=("out", "in"))
def test_prefixed_immediate_io_ignores_index_prefix(prefix: int, opcode: int) -> None:
    """DD/FD immediate I/O uses the ordinary A:n port address and costs 15 T-states."""
    cpu = MemoryCPU()
    _setup(cpu)
    cpu.a = 0x5A
    cpu.ports[0x5A44] = 0xA6

    tstates = _run(cpu, bytes([prefix, opcode, 0x44]))

    assert cpu.a == (0xA6 if opcode == 0xDB else 0x5A)
    assert cpu.port_writes == ([(0x5A44, 0x5A)] if opcode == 0xD3 else [])
    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0x2003
    assert cpu.r == 0x40
    assert cpu.wz == 0x5A45
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 15


_JR_CASES = (
    (0x18, 0xA5, True),
    (0x20, 0xA5, True),
    (0x20, 0xE5, False),
    (0x28, 0xE5, True),
    (0x28, 0xA5, False),
    (0x30, 0xA4, True),
    (0x30, 0xA5, False),
    (0x38, 0xA5, True),
    (0x38, 0xA4, False),
)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "flags", "taken"), _JR_CASES)
def test_prefixed_relative_jumps_ignore_index_prefix(
    prefix: int, opcode: int, flags: int, taken: bool
) -> None:
    """DD/FD JR and JR cc use ordinary conditions and only add four T-states."""
    cpu = MemoryCPU()
    _setup(cpu)
    cpu.f.byte = flags

    tstates = _run(cpu, bytes([prefix, opcode, 0xFD]))

    assert int(cpu.f) == flags
    assert cpu.q == 0
    assert cpu.pc == (0x2000 if taken else 0x2003)
    assert cpu.r == 0x40
    assert cpu.wz == (0x2000 if taken else 0xBEEF)
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == (16 if taken else 11)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(
    ("opcode", "a", "flags", "expected_a", "expected_flags"),
    (
        (0x07, 0x81, 0xC4, 0x03, 0xC5),
        (0x0F, 0x03, 0xC4, 0x81, 0xC5),
        (0x17, 0x81, 0xC5, 0x03, 0xC5),
        (0x1F, 0x03, 0xC5, 0x81, 0xC5),
        (0x27, 0x0A, 0x00, 0x10, 0x10),
    ),
)
def test_prefixed_accumulator_rotates_and_daa_ignore_index_prefix(
    prefix: int, opcode: int, a: int, flags: int, expected_a: int, expected_flags: int
) -> None:
    """DD/FD accumulator rotates and DAA retain base flags and timing."""
    cpu = MemoryCPU()
    _setup(cpu)
    cpu.a = a
    cpu.f.byte = flags

    tstates = _run(cpu, bytes([prefix, opcode]))

    assert cpu.a == expected_a
    assert int(cpu.f) == expected_flags
    assert cpu.q == expected_flags
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 8
