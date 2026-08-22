"""Red-first witnesses for undocumented ED NOP forms."""

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


@pytest.mark.parametrize("opcode", (0x77, 0x7F))
def test_undocumented_ed_nops_change_only_execution_bookkeeping(opcode: int) -> None:
    cpu = MemoryCPU()
    cpu.pc, cpu.r, cpu.a, cpu.f.byte, cpu.q, cpu.wz = 0x2000, 0x3E, 0xA6, 0xC5, 0xC5, 0xBEEF
    cpu.write_byte(cpu.pc, 0xED)
    cpu.write_byte(cpu.pc + 1, opcode)

    assert cpu.decode_and_execute() == 8

    assert (cpu.pc, cpu.r, cpu.a, int(cpu.f), cpu.q, cpu.wz) == (
        0x2002,
        0x40,
        0xA6,
        0xC5,
        0,
        0xBEEF,
    )  # noqa: W292