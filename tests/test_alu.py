"""Unit tests for the Z80 8-bit arithmetic and logic group (src/z80_python/).

The authoritative check for this group is the per-opcode SingleStepTests/z80
vector suite run by ``tests/test_z80.py`` (89 vector files, 1000 cases each,
covering ADD/ADC/SUB/SBC/AND/OR/XOR/CP with register, (HL) and immediate
operands, INC/DEC r, INC/DEC (HL) and DAA).  The tests here are a fast,
readable complement that pins down the documented flag semantics -- S, Z, H,
P/V, N, C plus the undocumented X/Y bits -- the WZ and Q behaviour, the T-state
counts and the register-field decode, so a regression is visible in a single
test name instead of a 1000-case vector diff.
"""

from __future__ import annotations

import pytest

from z80_python import Z80CPU

FLAG_S = 0x80
FLAG_Z = 0x40
FLAG_Y = 0x20
FLAG_H = 0x10
FLAG_X = 0x08
FLAG_PV = 0x04
FLAG_N = 0x02
FLAG_C = 0x01


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


def _program(cpu: MemoryCPU, pc: int, *bytes_: int) -> None:
    """Write a little program at ``pc`` and point the CPU at it."""
    for offset, value in enumerate(bytes_):
        cpu.write_byte(pc + offset, value)
    cpu.pc = pc


# --- ADD / ADC -------------------------------------------------------------


def test_add_register_sets_basic_flags() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x10
    cpu.b = 0x20
    _program(cpu, 0x0000, 0x80)  # ADD A,B
    assert cpu.decode_and_execute() == 4
    assert cpu.a == 0x30
    assert cpu.f.byte & (FLAG_S | FLAG_Z | FLAG_H | FLAG_PV | FLAG_N | FLAG_C) == 0
    # X/Y copy result bits 3/5 (0x30 -> bit5 set, bit3 clear).
    assert cpu.f.y == 1
    assert cpu.f.x == 0


def test_add_half_carry() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x0F
    cpu.b = 0x01
    _program(cpu, 0x0000, 0x80)
    cpu.decode_and_execute()
    assert cpu.a == 0x10
    assert cpu.f.h == 1
    assert cpu.f.c == 0


def test_add_carry_and_zero() -> None:
    cpu = MemoryCPU()
    cpu.a = 0xFF
    cpu.b = 0x01
    _program(cpu, 0x0000, 0x80)
    cpu.decode_and_execute()
    assert cpu.a == 0x00
    assert cpu.f.c == 1
    assert cpu.f.z == 1
    assert cpu.f.h == 1
    assert cpu.f.s == 0


def test_add_overflow() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x7F
    cpu.b = 0x01
    _program(cpu, 0x0000, 0x80)
    cpu.decode_and_execute()
    assert cpu.a == 0x80
    assert cpu.f.pv == 1  # +127 + 1 overflows into the sign bit
    assert cpu.f.s == 1
    assert cpu.f.z == 0
    assert cpu.f.c == 0


def test_adc_includes_carry() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x00
    cpu.b = 0x00
    cpu.f.c = 1
    _program(cpu, 0x0000, 0x88)  # ADC A,B
    cpu.decode_and_execute()
    assert cpu.a == 0x01
    assert cpu.f.c == 0
    assert cpu.f.z == 0


def test_add_immediate_advances_pc() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x22
    _program(cpu, 0x1000, 0xC6, 0x11)  # ADD A,0x11
    assert cpu.decode_and_execute() == 7
    assert cpu.a == 0x33
    assert cpu.pc == 0x1002


def test_add_hl_operand_reads_memory() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x03
    cpu.h = 0x20
    cpu.l = 0x00
    cpu.write_byte(0x2000, 0x05)
    cpu.wz = 0x1234
    _program(cpu, 0x0000, 0x86)  # ADD A,(HL)
    assert cpu.decode_and_execute() == 7
    assert cpu.a == 0x08
    # 8-bit ALU operations leave WZ untouched.
    assert cpu.wz == 0x1234


def test_alu_register_field_decode() -> None:
    """0x80-0x85/0x87 select B/C/D/E/H/L/A as the ADD source."""
    for opcode, reg in (
        (0x80, "b"),
        (0x81, "c"),
        (0x82, "d"),
        (0x83, "e"),
        (0x84, "h"),
        (0x85, "l"),
        (0x87, "a"),
    ):
        cpu = MemoryCPU()
        cpu.a = 0x10
        operand = cpu.a if reg == "a" else 0x07
        setattr(cpu, reg, operand)
        _program(cpu, 0x0000, opcode)
        cpu.decode_and_execute()
        assert cpu.a == 0x10 + operand, f"ADD A,{reg.upper()} via 0x{opcode:02X}"


# --- SUB / SBC -------------------------------------------------------------


def test_sub_borrow_and_half_carry() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x00
    cpu.b = 0x01
    _program(cpu, 0x0000, 0x90)  # SUB B
    cpu.decode_and_execute()
    assert cpu.a == 0xFF
    assert cpu.f.c == 1
    assert cpu.f.n == 1
    assert cpu.f.h == 1
    assert cpu.f.s == 1
    assert cpu.f.z == 0
    assert cpu.f.x == 1
    assert cpu.f.y == 1


def test_sub_overflow() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x80
    cpu.b = 0x01
    _program(cpu, 0x0000, 0x90)
    cpu.decode_and_execute()
    assert cpu.a == 0x7F
    assert cpu.f.pv == 1  # -128 - 1 underflows past the sign bit
    assert cpu.f.s == 0
    assert cpu.f.c == 0


def test_sbc_includes_carry() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x10
    cpu.b = 0x01
    cpu.f.c = 1
    _program(cpu, 0x0000, 0x98)  # SBC A,B
    cpu.decode_and_execute()
    assert cpu.a == 0x0E
    assert cpu.f.c == 0
    assert cpu.f.n == 1


# --- AND / OR / XOR --------------------------------------------------------


def test_and_sets_half_carry_and_parity() -> None:
    cpu = MemoryCPU()
    cpu.a = 0xFF
    cpu.b = 0x0F
    _program(cpu, 0x0000, 0xA0)  # AND B
    cpu.decode_and_execute()
    assert cpu.a == 0x0F
    assert cpu.f.h == 1
    assert cpu.f.c == 0
    assert cpu.f.n == 0
    assert cpu.f.pv == 1  # 0x0F has four set bits -> even parity
    assert cpu.f.x == 1  # bit 3 of 0x0F
    assert cpu.f.y == 0


def test_and_zero_result() -> None:
    cpu = MemoryCPU()
    cpu.a = 0xF0
    cpu.b = 0x0F
    _program(cpu, 0x0000, 0xA0)
    cpu.decode_and_execute()
    assert cpu.a == 0x00
    assert cpu.f.z == 1
    assert cpu.f.pv == 1  # zero set bits -> even parity


def test_or_clears_h_and_c() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x80
    cpu.b = 0x01
    _program(cpu, 0x0000, 0xB0)  # OR B
    cpu.decode_and_execute()
    assert cpu.a == 0x81
    assert cpu.f.h == 0
    assert cpu.f.c == 0
    assert cpu.f.n == 0
    assert cpu.f.pv == 1  # 0x81 has two set bits -> even parity
    assert cpu.f.s == 1


def test_xor_clears_h_and_c() -> None:
    cpu = MemoryCPU()
    cpu.a = 0xFF
    cpu.b = 0x0F
    _program(cpu, 0x0000, 0xA8)  # XOR B
    cpu.decode_and_execute()
    assert cpu.a == 0xF0
    assert cpu.f.h == 0
    assert cpu.f.c == 0
    assert cpu.f.n == 0
    assert cpu.f.pv == 1  # 0xF0 has four set bits -> even parity
    assert cpu.f.s == 1
    assert cpu.f.y == 1  # bit 5 of 0xF0


# --- CP --------------------------------------------------------------------


def test_cp_leaves_a_and_copies_xy_from_operand() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x00
    cpu.b = 0x28
    _program(cpu, 0x0000, 0xB8)  # CP B
    cpu.decode_and_execute()
    assert cpu.a == 0x00  # accumulator untouched
    assert cpu.f.c == 1
    assert cpu.f.n == 1
    assert cpu.f.s == 1
    assert cpu.f.z == 0
    # CP copies X/Y from the operand (0x28 -> bits 5 and 3 both set).
    assert cpu.f.y == 1
    assert cpu.f.x == 1


def test_cp_equal_sets_zero() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x42
    cpu.b = 0x42
    _program(cpu, 0x0000, 0xB8)
    cpu.decode_and_execute()
    assert cpu.a == 0x42
    assert cpu.f.z == 1
    assert cpu.f.c == 0


# --- INC / DEC -------------------------------------------------------------


@pytest.mark.parametrize(
    ("inc_opcode", "dec_opcode", "reg"),
    [
        (0x04, 0x05, "b"),
        (0x0C, 0x0D, "c"),
        (0x14, 0x15, "d"),
        (0x1C, 0x1D, "e"),
        (0x24, 0x25, "h"),
        (0x2C, 0x2D, "l"),
        (0x3C, 0x3D, "a"),
    ],
)
def test_inc_dec_r_targets_all_registers(inc_opcode: int, dec_opcode: int, reg: str) -> None:
    cpu = MemoryCPU()
    setattr(cpu, reg, 0x05)
    _program(cpu, 0x0000, inc_opcode)
    assert cpu.decode_and_execute() == 4
    assert getattr(cpu, reg) == 0x06
    _program(cpu, 0x0000, dec_opcode)
    cpu.decode_and_execute()
    assert getattr(cpu, reg) == 0x05


def test_inc_preserves_carry_and_sets_overflow() -> None:
    cpu = MemoryCPU()
    cpu.b = 0x7F
    cpu.f.c = 1
    _program(cpu, 0x0000, 0x04)  # INC B
    cpu.decode_and_execute()
    assert cpu.b == 0x80
    assert cpu.f.pv == 1
    assert cpu.f.c == 1  # INC/DEC never touch carry
    assert cpu.f.s == 1
    assert cpu.f.n == 0
    assert cpu.f.h == 1


def test_inc_zero_result() -> None:
    cpu = MemoryCPU()
    cpu.b = 0xFF
    _program(cpu, 0x0000, 0x04)
    cpu.decode_and_execute()
    assert cpu.b == 0x00
    assert cpu.f.z == 1
    assert cpu.f.pv == 0
    assert cpu.f.c == 0


def test_dec_preserves_carry_and_sets_overflow() -> None:
    cpu = MemoryCPU()
    cpu.b = 0x80
    cpu.f.c = 1
    _program(cpu, 0x0000, 0x05)  # DEC B
    cpu.decode_and_execute()
    assert cpu.b == 0x7F
    assert cpu.f.pv == 1
    assert cpu.f.c == 1
    assert cpu.f.n == 1
    assert cpu.f.s == 0
    assert cpu.f.h == 1  # borrow out of bit 3


def test_inc_hl_updates_memory_and_preserves_carry() -> None:
    cpu = MemoryCPU()
    cpu.h = 0x40
    cpu.l = 0x00
    cpu.write_byte(0x4000, 0xFF)
    cpu.f.c = 1
    _program(cpu, 0x0000, 0x34)  # INC (HL)
    assert cpu.decode_and_execute() == 11
    assert cpu.read_byte(0x4000) == 0x00
    assert cpu.f.z == 1
    assert cpu.f.c == 1


def test_dec_hl_updates_memory_and_preserves_carry() -> None:
    cpu = MemoryCPU()
    cpu.h = 0x40
    cpu.l = 0x00
    cpu.write_byte(0x4000, 0x00)
    cpu.f.c = 1
    _program(cpu, 0x0000, 0x35)  # DEC (HL)
    assert cpu.decode_and_execute() == 11
    assert cpu.read_byte(0x4000) == 0xFF
    assert cpu.f.n == 1
    assert cpu.f.h == 1
    assert cpu.f.c == 1


# --- DAA -------------------------------------------------------------------


def test_daa_no_adjustment() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x15
    _program(cpu, 0x0000, 0x27)  # DAA
    assert cpu.decode_and_execute() == 4
    assert cpu.a == 0x15
    assert cpu.f.c == 0
    assert cpu.f.z == 0
    assert cpu.f.n == 0


def test_daa_after_bcd_add_9_plus_9() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x12  # 0x09 + 0x09 left A=0x12 with H set
    cpu.f.h = 1
    _program(cpu, 0x0000, 0x27)
    cpu.decode_and_execute()
    assert cpu.a == 0x18  # 9 + 9 = 18 in BCD
    assert cpu.f.c == 0


def test_daa_after_bcd_add_99_plus_1() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x9A  # 0x99 + 0x01 left A=0x9A with H set
    cpu.f.h = 1
    _program(cpu, 0x0000, 0x27)
    cpu.decode_and_execute()
    assert cpu.a == 0x00  # 99 + 1 = 100 in BCD, carry out
    assert cpu.f.c == 1
    assert cpu.f.z == 1


# --- Q flag and WZ ---------------------------------------------------------


def test_alu_ops_latch_q_and_leave_wz() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x10
    cpu.b = 0x20
    cpu.wz = 0xABCD
    _program(cpu, 0x0000, 0x80)  # ADD A,B
    cpu.decode_and_execute()
    assert cpu.q == cpu.f.byte
    assert cpu.wz == 0xABCD


def test_inc_dec_latch_q() -> None:
    cpu = MemoryCPU()
    cpu.b = 0x05
    _program(cpu, 0x0000, 0x04)  # INC B
    cpu.decode_and_execute()
    assert cpu.q == cpu.f.byte
    _program(cpu, 0x0000, 0x05)  # DEC B
    cpu.decode_and_execute()
    assert cpu.q == cpu.f.byte
