"""Red-first witnesses for DDCB/FDCB indexed BIT operations."""

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
        pytest.fail(f"DDCB/FDCB indexed BIT operation is not implemented: {exc}")


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(
    ("index", "displacement", "opcode", "value", "expected_address", "expected_flags"),
    (
        (0x2800, 0xFF, 0x40, 0x00, 0x27FF, 0x75),
        (0xA810, 0x01, 0x7F, 0x80, 0xA811, 0xB9),
        (0xFFFF, 0x01, 0x46, 0x01, 0x0000, 0x11),
    ),
)
def test_indexed_bit_uses_selected_index_wz_high_xy_and_no_register_writeback(
    prefix: int,
    index: int,
    displacement: int,
    opcode: int,
    value: int,
    expected_address: int,
    expected_flags: int,
) -> None:
    """DDCB/FDCB BIT b,(index+d) always reads memory and ignores opcode low bits."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = index if prefix == 0xDD else 0x1234
    cpu.iy = index if prefix == 0xFD else 0x5678
    cpu.a, cpu.b, cpu.c, cpu.d, cpu.e, cpu.h, cpu.l = 1, 2, 3, 4, 5, 6, 7
    cpu.r = 0x3E
    cpu.f.byte = 0x01
    cpu.q = 0x01
    cpu.wz = 0xBEEF
    cpu.write_byte(expected_address, value)

    tstates = _run(cpu, bytes([prefix, 0xCB, displacement, opcode]))

    assert cpu.read_byte(expected_address) == value
    assert (cpu.a, cpu.b, cpu.c, cpu.d, cpu.e, cpu.h, cpu.l) == (1, 2, 3, 4, 5, 6, 7)
    assert cpu.ix == (index if prefix == 0xDD else 0x1234)
    assert cpu.iy == (index if prefix == 0xFD else 0x5678)
    assert int(cpu.f) == expected_flags
    assert cpu.q == expected_flags
    assert cpu.pc == 0x2004
    assert cpu.r == 0x40
    assert cpu.wz == expected_address
    assert tstates == 20
