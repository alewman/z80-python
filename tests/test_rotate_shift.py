"""Unit tests for the Z80 rotate and shift group (src/z80/cpu.py).

The authoritative check for this group is the per-opcode SingleStepTests/z80
vector suite run by ``tests/test_z80.py`` (cb 00.json-cb 3f.json plus
ed 67.json/ed 6f.json, 1000 cases each, covering RLC/RRC/RL/RR/SLA/SRA/SLL/SRL
on every register and (HL) plus RLD/RRD).  The tests here are a fast, readable
complement that pins down the documented flag semantics -- S, Z, P/V, H, N, C
plus the undocumented X/Y bits -- the WZ and Q behaviour, the T-state counts
and the register-field decode, so a regression is visible in a single test
name instead of a 1000-case vector diff.
"""

from __future__ import annotations

import pytest

from z80.cpu import Z80CPU

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


# --- CB register rotates/shifts --------------------------------------------


def test_rlc_a_rotates_left_and_sets_flags() -> None:
    cpu = MemoryCPU()
    cpu.a = 0xBF  # 1011 1111
    _program(cpu, 0x0000, 0xCB, 0x07)  # RLC A
    assert cpu.decode_and_execute() == 8
    assert cpu.a == 0x7F  # bit 7 wraps into bit 0 and into C
    assert cpu.f.c == 1
    assert cpu.f.n == 0
    assert cpu.f.h == 0
    assert cpu.f.s == 0
    assert cpu.f.z == 0
    assert cpu.f.pv == 0  # 0x7F has seven set bits -> odd parity
    assert cpu.f.x == 1  # bit 3 of 0x7F
    assert cpu.f.y == 1  # bit 5 of 0x7F
    assert cpu.f.byte == 0x29
    assert cpu.pc == 0x0002  # CB prefix + sub-opcode, no operands
    assert cpu.q == cpu.f.byte


def test_rrc_a_rotates_right_and_sets_carry() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x01
    _program(cpu, 0x0000, 0xCB, 0x0F)  # RRC A
    cpu.decode_and_execute()
    assert cpu.a == 0x80  # bit 0 wraps into bit 7 and into C
    assert cpu.f.c == 1
    assert cpu.f.s == 1
    assert cpu.f.pv == 0  # 0x80 has one set bit -> odd parity
    assert cpu.f.byte == 0x81


def test_rl_feeds_old_carry_into_bit0() -> None:
    cpu = MemoryCPU()
    cpu.b = 0x80
    cpu.f.c = 1
    _program(cpu, 0x0000, 0xCB, 0x10)  # RL B
    cpu.decode_and_execute()
    assert cpu.b == 0x01  # carry fed in, old bit 7 went to C
    assert cpu.f.c == 1
    assert cpu.f.byte == 0x01


def test_rr_feeds_old_carry_into_bit7() -> None:
    cpu = MemoryCPU()
    cpu.b = 0x01
    cpu.f.c = 1
    _program(cpu, 0x0000, 0xCB, 0x18)  # RR B
    cpu.decode_and_execute()
    assert cpu.b == 0x80  # carry fed in, old bit 0 went to C
    assert cpu.f.c == 1
    assert cpu.f.s == 1
    assert cpu.f.byte == 0x81


def test_sla_shifts_left_and_zeroes_bit0() -> None:
    cpu = MemoryCPU()
    cpu.b = 0x80
    _program(cpu, 0x0000, 0xCB, 0x20)  # SLA B
    cpu.decode_and_execute()
    assert cpu.b == 0x00
    assert cpu.f.c == 1
    assert cpu.f.z == 1
    assert cpu.f.pv == 1  # zero set bits -> even parity
    assert cpu.f.byte == 0x45


def test_sra_replicates_sign_bit() -> None:
    cpu = MemoryCPU()
    cpu.b = 0x81
    _program(cpu, 0x0000, 0xCB, 0x28)  # SRA B
    cpu.decode_and_execute()
    assert cpu.b == 0xC0  # bit 7 stays set, bit 0 moved into C
    assert cpu.f.c == 1
    assert cpu.f.s == 1
    assert cpu.f.pv == 1  # 0xC0 has two set bits -> even parity
    assert cpu.f.byte == 0x85


def test_sll_shifts_left_and_sets_bit0() -> None:
    cpu = MemoryCPU()
    cpu.b = 0x40
    _program(cpu, 0x0000, 0xCB, 0x30)  # SLL B (undocumented)
    cpu.decode_and_execute()
    assert cpu.b == 0x81
    assert cpu.f.c == 0
    assert cpu.f.s == 1
    assert cpu.f.pv == 1  # 0x81 has two set bits -> even parity
    assert cpu.f.byte == 0x84


def test_srl_logical_shift_right_zeroes_bit7() -> None:
    cpu = MemoryCPU()
    cpu.b = 0x81
    _program(cpu, 0x0000, 0xCB, 0x38)  # SRL B
    cpu.decode_and_execute()
    assert cpu.b == 0x40
    assert cpu.f.c == 1
    assert cpu.f.s == 0
    assert cpu.f.y == 0  # 0x40 has bit 6 set, bit 5 clear
    assert cpu.f.byte == 0x01


@pytest.mark.parametrize(
    ("opcode", "reg"),
    [
        (0x00, "b"),
        (0x01, "c"),
        (0x02, "d"),
        (0x03, "e"),
        (0x04, "h"),
        (0x05, "l"),
        (0x07, "a"),
    ],
)
def test_rotate_targets_all_registers(opcode: int, reg: str) -> None:
    cpu = MemoryCPU()
    setattr(cpu, reg, 0x81)
    _program(cpu, 0x0000, 0xCB, opcode)  # RLC r
    assert cpu.decode_and_execute() == 8
    assert getattr(cpu, reg) == 0x03
    assert cpu.f.c == 1


# --- CB (HL) rotates/shifts -------------------------------------------------


def test_rlc_hl_reads_memory_and_writes_back() -> None:
    cpu = MemoryCPU()
    cpu.h = 0x40
    cpu.l = 0x00
    cpu.write_byte(0x4000, 0x15)
    _program(cpu, 0x0000, 0xCB, 0x06)  # RLC (HL)
    assert cpu.decode_and_execute() == 15
    assert cpu.read_byte(0x4000) == 0x2A
    assert cpu.f.c == 0
    assert cpu.f.byte == 0x28
    assert cpu.pc == 0x0002
    assert cpu.q == cpu.f.byte


# --- RLD / RRD --------------------------------------------------------------


def test_rld_rotates_nibbles_left_and_sets_wz() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x9F
    cpu.h = 0xA6
    cpu.l = 0x81
    cpu.write_byte(0xA681, 0x83)
    _program(cpu, 0x0000, 0xED, 0x6F)  # RLD
    assert cpu.decode_and_execute() == 18
    assert cpu.a == 0x98
    assert cpu.read_byte(0xA681) == 0x3F
    assert cpu.wz == 0xA682  # WZ <- HL + 1
    assert cpu.f.n == 0
    assert cpu.f.h == 0
    assert cpu.f.c == 0  # carry preserved (was 0)
    assert cpu.f.s == 1
    assert cpu.f.x == 1  # bit 3 of 0x98
    assert cpu.f.byte == 0x88
    assert cpu.pc == 0x0002
    assert cpu.q == cpu.f.byte


def test_rrd_rotates_nibbles_right_and_sets_wz() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x42
    cpu.h = 0x09
    cpu.l = 0x8F
    cpu.write_byte(0x098F, 0x38)
    _program(cpu, 0x0000, 0xED, 0x67)  # RRD
    assert cpu.decode_and_execute() == 18
    assert cpu.a == 0x48
    assert cpu.read_byte(0x098F) == 0x23
    assert cpu.wz == 0x0990  # WZ <- HL + 1
    assert cpu.f.n == 0
    assert cpu.f.h == 0
    assert cpu.f.c == 0  # carry preserved
    assert cpu.f.pv == 1  # 0x48 has two set bits -> even parity
    assert cpu.f.byte == 0x0C
    assert cpu.pc == 0x0002


def test_rld_preserves_carry_flag() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x00
    cpu.h = 0x40
    cpu.l = 0x00
    cpu.write_byte(0x4000, 0x00)
    cpu.f.c = 1
    _program(cpu, 0x0000, 0xED, 0x6F)  # RLD
    cpu.decode_and_execute()
    assert cpu.f.c == 1
    assert cpu.a == 0x00
    assert cpu.f.z == 1


def test_rld_rrd_advance_refresh_register_by_two() -> None:
    cpu = MemoryCPU()
    cpu.r = 0x10
    cpu.h = 0x40
    cpu.l = 0x00
    _program(cpu, 0x0000, 0xED, 0x6F)  # RLD
    cpu.decode_and_execute()
    assert cpu.r == 0x12  # one increment per opcode byte fetched
