"""Red-first witnesses for the ED NEG aliases."""

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


@pytest.mark.parametrize("opcode", (0x44, 0x4C, 0x54, 0x5C, 0x64, 0x6C, 0x74, 0x7C))
@pytest.mark.parametrize(
    ("initial_a", "expected_a", "expected_f"),
    ((0x00, 0x00, 0x42), (0x01, 0xFF, 0xBB), (0x80, 0x80, 0x87)),
)
def test_ed_neg_aliases_share_subtraction_flags(
    opcode: int, initial_a: int, expected_a: int, expected_f: int
) -> None:
    cpu = MemoryCPU()
    cpu.pc, cpu.r, cpu.a, cpu.f.byte, cpu.q, cpu.wz = 0x2000, 0x3E, initial_a, 0xC5, 0xC5, 0xBEEF
    cpu.write_byte(cpu.pc, 0xED)
    cpu.write_byte(cpu.pc + 1, opcode)

    assert cpu.decode_and_execute() == 8

    assert (cpu.pc, cpu.r, cpu.a, int(cpu.f), cpu.q, cpu.wz) == (
        0x2002,
        0x40,
        expected_a,
        expected_f,
        expected_f,
        0xBEEF,
    )  # noqa: W292