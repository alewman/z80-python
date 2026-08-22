"""Unit tests for the Z80 CPU skeleton (src/z80/cpu.py)."""

import pytest

from z80.cpu import (
    FLAG_C,
    FLAG_H,
    FLAG_N,
    FLAG_PV,
    FLAG_S,
    FLAG_X,
    FLAG_Y,
    FLAG_Z,
    Z80CPU,
    Flags,
)


class MemoryCPU(Z80CPU):
    """Concrete Z80CPU backed by a flat 64 KiB bytearray."""

    def __init__(self, memory: bytes = bytes(0x10000)) -> None:
        super().__init__()
        self.memory = bytearray(memory)

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        raise NotImplementedError("test MemoryCPU does not model I/O ports")

    def write_port(self, addr: int, value: int) -> None:
        raise NotImplementedError("test MemoryCPU does not model I/O ports")


def test_all_registers_initialized_to_zero() -> None:
    cpu = MemoryCPU()
    for name in ("a", "b", "c", "d", "e", "h", "l", "ix", "iy", "sp", "pc", "i", "r"):
        assert getattr(cpu, name) == 0
    assert cpu.wz == 0
    assert cpu.q == 0
    assert cpu.f.byte == 0
    assert cpu.af_ == 0
    assert cpu.bc_ == 0
    assert cpu.de_ == 0
    assert cpu.hl_ == 0
    assert cpu.iff1 is False
    assert cpu.iff2 is False
    assert cpu.im == 0


def test_z80cpu_is_abstract() -> None:
    with pytest.raises(TypeError):
        Z80CPU()  # type: ignore[abstract]


def test_flag_constants_cover_all_f_bits() -> None:
    assert FLAG_S == 0x80
    assert FLAG_Z == 0x40
    assert FLAG_Y == 0x20  # undocumented bit 5
    assert FLAG_H == 0x10
    assert FLAG_X == 0x08  # undocumented bit 3
    assert FLAG_PV == 0x04
    assert FLAG_N == 0x02
    assert FLAG_C == 0x01


def test_flags_byte_roundtrip() -> None:
    flags = Flags(0b1011_0101)
    assert flags.byte == 0b1011_0101
    assert int(flags) == 0b1011_0101
    flags.byte = 0xFF
    assert flags.byte == 0xFF
    flags.byte = 0x1FF
    assert flags.byte == 0xFF  # masked to 8 bits


def test_flags_individual_bits_set_and_clear() -> None:
    flags = Flags()
    for attr in ("s", "z", "y", "h", "x", "pv", "n", "c"):
        setattr(flags, attr, 1)
    assert flags.byte == 0xFF
    flags.c = 0
    flags.x = 0
    assert flags.byte == 0b1111_0110
    assert flags.s == 1
    assert flags.z == 1
    assert flags.y == 1
    assert flags.h == 1
    assert flags.x == 0
    assert flags.pv == 1
    assert flags.n == 1
    assert flags.c == 0


def test_set_xy_copies_result_bits_3_and_5_only() -> None:
    flags = Flags(0b0000_0001)  # keep the carry flag set
    flags.set_xy(0b0010_1000)
    assert flags.byte == 0b0010_1001
    flags.set_xy(0x00)
    assert flags.byte == 0b0000_0001


def test_read_write_byte_through_memory_bus() -> None:
    cpu = MemoryCPU()
    cpu.write_byte(0x1234, 0xAB)
    assert cpu.read_byte(0x1234) == 0xAB
    assert cpu.memory[0x1234] == 0xAB


def test_decode_and_execute_fetches_index_prefix_and_raises_for_unknown_subopcode() -> None:
    cpu = MemoryCPU()
    cpu.pc = 0x1234
    cpu.write_byte(0x1234, 0xDD)
    cpu.write_byte(0x1235, 0xED)  # DD ED remains unimplemented.
    with pytest.raises(NotImplementedError):
        cpu.decode_and_execute()
    assert cpu.pc == 0x1235


def test_halt_sets_halted_flag_and_leaves_state_untouched() -> None:
    cpu = MemoryCPU()
    cpu.pc = 0x1000
    cpu.write_byte(0x1000, 0x76)  # HALT
    cpu.f.byte = 0xD7
    cpu.q = 0xD7
    assert cpu.decode_and_execute() == 4
    assert cpu.halted is True
    assert cpu.pc == 0x1001
    assert cpu.r == 1  # the opcode fetch bumped the refresh register
    assert cpu.f.byte == 0xD7  # no flags modified
    assert cpu.q == 0  # HALT does not write F, so Q is cleared


def test_q_tracking_latches_f_or_clears() -> None:
    cpu = MemoryCPU()
    cpu.f.byte = 0b1011_0101
    cpu._update_q(True)
    assert cpu.q == 0b1011_0101
    cpu._update_q(False)
    assert cpu.q == 0


def test_inc_r_preserves_bit7() -> None:
    cpu = MemoryCPU()
    cpu.r = 0x7F
    cpu._inc_r()
    assert cpu.r == 0x00
    cpu.r = 0xFF
    cpu._inc_r()
    assert cpu.r == 0x80
