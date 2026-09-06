"""Red-first witnesses for DDCB/FDCB indexed rotate and shift operations."""

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
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte(cpu.pc + offset, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(f"DDCB/FDCB indexed rotate or shift is not implemented: {exc}")


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(
    ("index", "displacement", "opcode", "value", "carry", "expected", "flags", "register"),
    (
        (0x2800, 0xFF, 0x00, 0x81, 0, 0x03, 0x05, "b"),
        (0xA810, 0x01, 0x1D, 0x02, 1, 0x81, 0x84, "l"),
        (0xFFFF, 0x01, 0x3E, 0x01, 0, 0x00, 0x45, None),
    ),
)
def test_indexed_rotates_write_memory_and_ordinary_destination_register(
    prefix: int,
    index: int,
    displacement: int,
    opcode: int,
    value: int,
    carry: int,
    expected: int,
    flags: int,
    register: str | None,
) -> None:
    """DDCB/FDCB rotate/shift writes the result to memory and opcode-selected B..A."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = index if prefix == 0xDD else 0x1234
    cpu.iy = index if prefix == 0xFD else 0x5678
    cpu.a, cpu.b, cpu.c, cpu.d, cpu.e, cpu.h, cpu.l = 1, 2, 3, 4, 5, 6, 7
    cpu.r = 0x3E
    cpu.f.byte = carry
    cpu.q = carry
    address = (index + (displacement if displacement < 0x80 else displacement - 0x100)) & 0xFFFF
    cpu.write_byte(address, value)

    tstates = _run(cpu, bytes([prefix, 0xCB, displacement, opcode]))

    assert cpu.read_byte(address) == expected
    if register is not None:
        assert getattr(cpu, register) == expected
    assert cpu.ix == (index if prefix == 0xDD else 0x1234)
    assert cpu.iy == (index if prefix == 0xFD else 0x5678)
    assert int(cpu.f) == flags
    assert cpu.q == flags
    assert cpu.pc == 0x2004
    assert cpu.r == 0x40
    assert cpu.wz == address
    assert tstates == 23
