"""Unit tests for the Z80 16-bit arithmetic group (src/z80_python/).

The authoritative check for this group is the per-opcode SingleStepTests/z80
vector suite run by ``tests/test_z80.py`` (09/19/29/39.json for ADD HL,rr,
ed 42/52/62/72.json for SBC HL,rr, ed 4a/5a/6a/7a.json for ADC HL,rr and
03/0b/13/1b/23/2b/33/3b.json for INC/DEC rr, 1000 cases each).  The tests
here are a fast, readable complement that pins down the documented
semantics -- the ADD HL,rr H/N/C-only flag recipe (S/Z/PV preserved), the
full 16-bit flag recipes of ADC/SBC HL,rr (S/Z/H/PV/N/C plus X/Y from the
result high byte), the WZ <- HL + 1 (MEMPTR) side effect shared by all three,
the no-flags INC/DEC rr, the T-state counts and the Q latching -- so a
regression is visible in a single test name instead of a 1000-case vector
diff.
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


def _set_hl(cpu: MemoryCPU, value: int) -> None:
    cpu.h = (value >> 8) & 0xFF
    cpu.l = value & 0xFF


def _set_bc(cpu: MemoryCPU, value: int) -> None:
    cpu.b = (value >> 8) & 0xFF
    cpu.c = value & 0xFF


def _set_de(cpu: MemoryCPU, value: int) -> None:
    cpu.d = (value >> 8) & 0xFF
    cpu.e = value & 0xFF


# --- ADD HL,rr (0x09/0x19/0x29/0x39) ----------------------------------------


def test_add_hl_bc_basic_and_xy_flags() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x1000)
    _set_bc(cpu, 0x2000)
    _program(cpu, 0x0000, 0x09)  # ADD HL,BC
    assert cpu.decode_and_execute() == 11
    assert cpu._hl() == 0x3000
    assert cpu.f.byte & (FLAG_S | FLAG_Z | FLAG_H | FLAG_PV | FLAG_N | FLAG_C) == 0
    # X/Y copy result bits 3/5 (0x30 -> bit5 set, bit3 clear).
    assert cpu.f.y == 1
    assert cpu.f.x == 0


def test_add_hl_carry_and_half_carry() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0xFFFF)
    _set_bc(cpu, 0x0001)
    _program(cpu, 0x0000, 0x09)
    cpu.decode_and_execute()
    assert cpu._hl() == 0x0000
    assert cpu.f.c == 1
    assert cpu.f.h == 1  # carry from bit 7 of the low byte
    assert cpu.f.n == 0


def test_add_hl_preserves_szpv() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x0100)
    _set_bc(cpu, 0x0100)
    cpu.f.byte = 0xAB  # S=1 Z=0 Y=1 H=0 X=1 PV=0 N=1 C=1
    _program(cpu, 0x0000, 0x09)
    cpu.decode_and_execute()
    assert cpu._hl() == 0x0200
    # Only H/N/C/X/Y change: H=0, N=0, C=0, X=0 (result high 0x02), Y=0.
    assert cpu.f.byte == 0x80  # S and Z preserved, everything else cleared


def test_add_hl_wz_is_hl_plus_one() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x1234)
    _set_bc(cpu, 0x0001)
    cpu.wz = 0xFFFF
    _program(cpu, 0x0000, 0x09)
    cpu.decode_and_execute()
    assert cpu.wz == 0x1235  # MEMPTR <- HL + 1


@pytest.mark.parametrize(
    ("opcode", "reg_name", "value"),
    [
        (0x09, "b", 0x2000),  # ADD HL,BC
        (0x19, "d", 0x2000),  # ADD HL,DE
        (0x29, "h", 0x1000),  # ADD HL,HL (operand is HL itself)
        (0x39, "sp", 0x2000),  # ADD HL,SP
    ],
)
def test_add_hl_register_field_decode(opcode: int, reg_name: str, value: int) -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x1000)
    if reg_name == "b":
        _set_bc(cpu, value)
    elif reg_name == "d":
        _set_de(cpu, value)
    else:
        cpu.sp = value
    _program(cpu, 0x0000, opcode)
    cpu.decode_and_execute()
    assert cpu._hl() == 0x1000 + value, f"ADD HL,{reg_name.upper()} via 0x{opcode:02X}"


def test_add_hl_latches_q() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x0001)
    _set_bc(cpu, 0x0001)
    _program(cpu, 0x0000, 0x09)
    cpu.decode_and_execute()
    assert cpu.q == cpu.f.byte


# --- ADC HL,rr (ED 0x4A/0x5A/0x6A/0x7A) --------------------------------------


def test_adc_hl_includes_carry() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x1000)
    _set_bc(cpu, 0x2000)
    cpu.f.c = 1
    _program(cpu, 0x0000, 0xED, 0x4A)  # ADC HL,BC
    assert cpu.decode_and_execute() == 15
    assert cpu._hl() == 0x3001
    assert cpu.f.n == 0
    assert cpu.f.c == 0


def test_adc_hl_sets_full_flags() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x7FFF)
    _set_bc(cpu, 0x0001)
    cpu.f.c = 0
    _program(cpu, 0x0000, 0xED, 0x4A)
    cpu.decode_and_execute()
    assert cpu._hl() == 0x8000
    assert cpu.f.s == 1  # bit 15 set
    assert cpu.f.z == 0
    assert cpu.f.pv == 1  # 0x7FFF + 1 overflows into the sign bit
    assert cpu.f.h == 1  # carry from bit 7 of the low byte
    assert cpu.f.n == 0
    assert cpu.f.c == 0
    # X/Y come from the result high byte 0x80 = 1000 0000: bits 5 and 3 clear.
    assert cpu.f.y == 0
    assert cpu.f.x == 0


def test_adc_hl_carry_out_and_zero() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0xFFFF)
    _set_bc(cpu, 0x0000)
    cpu.f.c = 1
    _program(cpu, 0x0000, 0xED, 0x4A)
    cpu.decode_and_execute()
    assert cpu._hl() == 0x0000
    assert cpu.f.c == 1
    assert cpu.f.z == 1
    assert cpu.f.s == 0


def test_adc_hl_wz_is_hl_plus_one() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x1234)
    _set_bc(cpu, 0x0000)
    cpu.wz = 0xFFFF
    _program(cpu, 0x0000, 0xED, 0x4A)
    cpu.decode_and_execute()
    assert cpu.wz == 0x1235


@pytest.mark.parametrize(
    ("opcode", "reg_name"),
    [
        (0x4A, "b"),  # ADC HL,BC
        (0x5A, "d"),  # ADC HL,DE
        (0x6A, "h"),  # ADC HL,HL
        (0x7A, "sp"),  # ADC HL,SP
    ],
)
def test_adc_hl_register_field_decode(opcode: int, reg_name: str) -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x0100)
    if reg_name == "b":
        _set_bc(cpu, 0x0100)
    elif reg_name == "d":
        _set_de(cpu, 0x0100)
    elif reg_name == "h":
        _set_hl(cpu, 0x0100)
    else:
        cpu.sp = 0x0100
    _program(cpu, 0x0000, 0xED, opcode)
    cpu.decode_and_execute()
    assert cpu._hl() == 0x0200, f"ADC HL,{reg_name.upper()} via ED 0x{opcode:02X}"


# --- SBC HL,rr (ED 0x42/0x52/0x62/0x72) --------------------------------------


def test_sbc_hl_includes_carry_and_sets_n() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x1000)
    _set_bc(cpu, 0x0001)
    cpu.f.c = 1
    _program(cpu, 0x0000, 0xED, 0x42)  # SBC HL,BC
    assert cpu.decode_and_execute() == 15
    assert cpu._hl() == 0x0FFE
    assert cpu.f.n == 1
    assert cpu.f.c == 0


def test_sbc_hl_borrow_and_half_carry() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x0000)
    _set_bc(cpu, 0x0001)
    cpu.f.c = 0
    _program(cpu, 0x0000, 0xED, 0x42)
    cpu.decode_and_execute()
    assert cpu._hl() == 0xFFFF
    assert cpu.f.c == 1
    assert cpu.f.n == 1
    assert cpu.f.h == 1
    assert cpu.f.s == 1
    assert cpu.f.z == 0
    assert cpu.f.x == 1  # high byte 0xFF -> bits 5 and 3 both set
    assert cpu.f.y == 1


def test_sbc_hl_overflow() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x8000)
    _set_bc(cpu, 0x0001)
    cpu.f.c = 0
    _program(cpu, 0x0000, 0xED, 0x42)
    cpu.decode_and_execute()
    assert cpu._hl() == 0x7FFF
    assert cpu.f.pv == 1  # -32768 - 1 underflows past the sign bit
    assert cpu.f.c == 0
    assert cpu.f.s == 0


def test_sbc_hl_zero_result() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x1234)
    _set_bc(cpu, 0x1234)
    cpu.f.c = 0
    _program(cpu, 0x0000, 0xED, 0x42)
    cpu.decode_and_execute()
    assert cpu._hl() == 0x0000
    assert cpu.f.z == 1
    assert cpu.f.c == 0
    assert cpu.f.n == 1


def test_sbc_hl_wz_is_hl_plus_one() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x1234)
    _set_bc(cpu, 0x0000)
    cpu.wz = 0xFFFF
    _program(cpu, 0x0000, 0xED, 0x42)
    cpu.decode_and_execute()
    assert cpu.wz == 0x1235


@pytest.mark.parametrize(
    ("opcode", "reg_name", "expected"),
    [
        (0x42, "b", 0x0100),  # SBC HL,BC
        (0x52, "d", 0x0100),  # SBC HL,DE
        (0x62, "h", 0x0000),  # SBC HL,HL (operand is HL itself: 0x0200 - 0x0200)
        (0x72, "sp", 0x0100),  # SBC HL,SP
    ],
)
def test_sbc_hl_register_field_decode(opcode: int, reg_name: str, expected: int) -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x0200)
    if reg_name == "b":
        _set_bc(cpu, 0x0100)
    elif reg_name == "d":
        _set_de(cpu, 0x0100)
    else:
        cpu.sp = 0x0100
    _program(cpu, 0x0000, 0xED, opcode)
    cpu.decode_and_execute()
    assert cpu._hl() == expected, f"SBC HL,{reg_name.upper()} via ED 0x{opcode:02X}"


# --- INC rr / DEC rr (0x03/0x13/0x23/0x33, 0x0B/0x1B/0x2B/0x3B) --------------


@pytest.mark.parametrize(
    ("inc_opcode", "dec_opcode", "reg_name"),
    [
        (0x03, 0x0B, "b"),
        (0x13, 0x1B, "d"),
        (0x23, 0x2B, "h"),
        (0x33, 0x3B, "sp"),
    ],
)
def test_inc_dec_rr_targets_all_pairs(inc_opcode: int, dec_opcode: int, reg_name: str) -> None:
    cpu = MemoryCPU()
    if reg_name == "b":
        _set_bc(cpu, 0x1000)
    elif reg_name == "d":
        _set_de(cpu, 0x1000)
    elif reg_name == "h":
        _set_hl(cpu, 0x1000)
    else:
        cpu.sp = 0x1000

    def pair() -> int:
        if reg_name == "b":
            return cpu._bc()
        if reg_name == "d":
            return cpu._de()
        if reg_name == "h":
            return cpu._hl()
        return cpu.sp

    _program(cpu, 0x0000, inc_opcode)
    assert cpu.decode_and_execute() == 6
    assert pair() == 0x1001
    _program(cpu, 0x0000, dec_opcode)
    cpu.decode_and_execute()
    assert pair() == 0x1000


def test_inc_rr_wraps_at_ffff_and_affects_no_flags() -> None:
    cpu = MemoryCPU()
    _set_bc(cpu, 0xFFFF)
    cpu.f.byte = 0xAB
    _program(cpu, 0x0000, 0x03)  # INC BC
    cpu.decode_and_execute()
    assert cpu._bc() == 0x0000
    assert cpu.f.byte == 0xAB  # flags completely untouched
    assert cpu.q == 0  # no flag modification -> Q cleared


def test_dec_rr_wraps_at_zero_and_affects_no_flags() -> None:
    cpu = MemoryCPU()
    _set_bc(cpu, 0x0000)
    cpu.f.byte = 0xAB
    _program(cpu, 0x0000, 0x0B)  # DEC BC
    cpu.decode_and_execute()
    assert cpu._bc() == 0xFFFF
    assert cpu.f.byte == 0xAB  # flags completely untouched
    assert cpu.q == 0  # no flag modification -> Q cleared
