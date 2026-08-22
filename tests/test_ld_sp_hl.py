"""Red-first witness for ordinary LD SP,HL."""

from __future__ import annotations

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


def test_ld_sp_hl_copies_pair_without_changing_flags_or_wz() -> None:
    cpu = MemoryCPU()
    cpu.pc, cpu.r, cpu.h, cpu.l, cpu.sp = 0x2000, 0x3E, 0xA6, 0x5A, 0x1234
    cpu.f.byte, cpu.q, cpu.wz = 0xC5, 0xC5, 0xBEEF
    cpu.write_byte(cpu.pc, 0xF9)

    assert cpu.decode_and_execute() == 6

    assert (cpu.pc, cpu.r, cpu.sp, int(cpu.f), cpu.q, cpu.wz) == (
        0x2001,
        0x3F,
        0xA65A,
        0xC5,
        0,
        0xBEEF,
    )  # noqa: W292