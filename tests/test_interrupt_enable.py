"""Red-first witnesses for DI/EI and their prefix-ignored forms."""

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


@pytest.mark.parametrize("prefix", (None, 0xDD, 0xFD))
@pytest.mark.parametrize(("opcode", "enabled"), ((0xF3, False), (0xFB, True)))
def test_interrupt_enable_forms_update_both_flip_flops(
    prefix: int | None, opcode: int, enabled: bool
) -> None:
    cpu = MemoryCPU()
    cpu.pc, cpu.r, cpu.f.byte, cpu.q, cpu.wz = 0x2000, 0x3E, 0xC5, 0xC5, 0xBEEF
    cpu.iff1, cpu.iff2 = (not enabled), (not enabled)
    if prefix is not None:
        cpu.write_byte(cpu.pc, prefix)
        cpu.write_byte(cpu.pc + 1, opcode)
    else:
        cpu.write_byte(cpu.pc, opcode)

    assert cpu.decode_and_execute() == (8 if prefix is not None else 4)

    assert (cpu.pc, cpu.r, int(cpu.f), cpu.q, cpu.wz, cpu.iff1, cpu.iff2) == (
        0x2002 if prefix is not None else 0x2001,
        0x40 if prefix is not None else 0x3F,
        0xC5,
        0,
        0xBEEF,
        enabled,
        enabled,
    )  # noqa: W292