"""Red-first witnesses for DDCB/FDCB indexed RES and SET operations."""

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
        pytest.fail(f"DDCB/FDCB indexed RES or SET is not implemented: {exc}")


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(
    ("index", "displacement", "opcode", "value", "expected", "register"),
    (
        (0x2800, 0xFF, 0x80, 0xFF, 0xFE, "b"),
        (0xA810, 0x01, 0xAD, 0x2F, 0x0F, "l"),
        (0xFFFF, 0x01, 0xFE, 0x01, 0x81, None),
    ),
)
def test_indexed_res_set_writes_memory_and_ordinary_destination_register(
    prefix: int,
    index: int,
    displacement: int,
    opcode: int,
    value: int,
    expected: int,
    register: str | None,
) -> None:
    """DDCB/FDCB RES/SET updates memory and B..A while leaving flags intact."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = index if prefix == 0xDD else 0x1234
    cpu.iy = index if prefix == 0xFD else 0x5678
    cpu.a, cpu.b, cpu.c, cpu.d, cpu.e, cpu.h, cpu.l = 1, 2, 3, 4, 5, 6, 7
    cpu.r = 0x3E
    cpu.f.byte = 0xC5
    cpu.q = 0xC5
    address = (index + (displacement if displacement < 0x80 else displacement - 0x100)) & 0xFFFF
    cpu.write_byte(address, value)

    tstates = _run(cpu, bytes([prefix, 0xCB, displacement, opcode]))

    assert cpu.read_byte(address) == expected
    if register is not None:
        assert getattr(cpu, register) == expected
    assert int(cpu.f) == 0xC5
    assert cpu.q == 0
    assert cpu.pc == 0x2004
    assert cpu.r == 0x40
    assert cpu.wz == address
    assert tstates == 23
