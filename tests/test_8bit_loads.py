"""Unit tests for the Z80 8-bit load group (src/z80/cpu.py).

The authoritative check for this group is the per-opcode SingleStepTests/z80
vector suite run by ``tests/test_z80.py`` (81 vector files, 1000 cases each:
LD r,r' / LD r,(HL) / LD (HL),r 0x40-0x7F minus HALT, LD r,n / LD (HL),n,
LD A,(BC)/(DE), LD (BC)/(DE),A, LD A,(nn), LD (nn),A, and the ED-prefixed
LD I,A / LD R,A / LD A,I / LD A,R).  The tests here are a fast, readable
complement that pins down the documented semantics -- WZ (MEMPTR) updates,
Q tracking (plain loads clear Q, LD A,I/LD A,R latch it), the LD A,I / LD A,R
flag behaviour (S/Z/X/Y from the source, P/V from IFF2, N/H cleared, C
preserved), the T-state counts, and the fact that all memory traffic goes
through ``read_byte``/``write_byte`` -- so a regression is visible in a single
test name instead of a 1000-case vector diff.
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


# --- LD r,r' (0x40-0x7F, excluding HALT 0x76) -------------------------------


def test_ld_a_b_copies_register_and_leaves_state_alone() -> None:
    cpu = MemoryCPU()
    cpu.b = 0x5A
    cpu.f.byte = 0xD7  # distinctive F: all documented flags set, no X/Y
    cpu.wz = 0x1234
    _program(cpu, 0x1000, 0x78)  # LD A,B
    assert cpu.decode_and_execute() == 4
    assert cpu.a == 0x5A
    assert cpu.b == 0x5A  # source untouched
    assert cpu.f.byte == 0xD7  # LD does not affect flags
    assert cpu.q == 0  # flags not modified -> Q cleared
    assert cpu.wz == 0x1234  # WZ untouched
    assert cpu.pc == 0x1001
    assert cpu.r == 1  # one opcode byte fetched


@pytest.mark.parametrize(
    ("opcode", "dest", "src"),
    [
        (0x40, "b", "b"),
        (0x47, "b", "a"),
        (0x4F, "c", "a"),
        (0x6F, "l", "a"),
        (0x67, "h", "a"),
        (0x7F, "a", "a"),
    ],
)
def test_ld_r_r_register_decode(opcode: int, dest: str, src: str) -> None:
    cpu = MemoryCPU()
    setattr(cpu, dest, 0x11)
    setattr(cpu, src, 0x93)
    _program(cpu, 0x0000, opcode)
    assert cpu.decode_and_execute() == 4
    assert getattr(cpu, dest) == 0x93
    assert getattr(cpu, src) == 0x93


def test_ld_a_hl_reads_through_memory_bus() -> None:
    cpu = MemoryCPU()
    cpu.h = 0x22
    cpu.l = 0x11
    cpu.write_byte(0x2211, 0x6B)  # (HL) = 0x6B
    cpu.wz = 0xABCD
    _program(cpu, 0x0000, 0x7E)  # LD A,(HL)
    assert cpu.decode_and_execute() == 7
    assert cpu.a == 0x6B
    assert cpu.wz == 0xABCD  # LD r,(HL) does not touch WZ
    assert cpu.q == 0
    assert cpu.f.byte == 0x00  # flags untouched


def test_ld_hl_b_writes_through_memory_bus() -> None:
    cpu = MemoryCPU()
    cpu.h = 0x22
    cpu.l = 0x11
    cpu.b = 0x9C
    cpu.wz = 0xABCD
    _program(cpu, 0x0000, 0x70)  # LD (HL),B
    assert cpu.decode_and_execute() == 7
    assert cpu.read_byte(0x2211) == 0x9C
    assert cpu.wz == 0xABCD  # LD (HL),r does not touch WZ
    assert cpu.q == 0
    assert cpu.f.byte == 0x00  # flags untouched


def test_halt_76_is_not_a_load() -> None:
    cpu = MemoryCPU()
    cpu.h = 0x22
    cpu.l = 0x11
    cpu.f.byte = 0x01
    _program(cpu, 0x0000, 0x76)  # HALT is not LD (HL),(HL)
    assert cpu.decode_and_execute() == 4
    assert cpu.halted is True
    assert cpu.read_byte(0x2211) == 0x00  # no memory write to (HL)
    assert cpu.f.byte == 0x01  # flags untouched
    assert cpu.q == 0  # Q cleared (F not written)


# --- LD r,n / LD (HL),n -----------------------------------------------------


def test_ld_a_n_immediate() -> None:
    cpu = MemoryCPU()
    cpu.f.byte = 0xD7
    _program(cpu, 0x1000, 0x3E, 0x42)  # LD A,0x42
    assert cpu.decode_and_execute() == 7
    assert cpu.a == 0x42
    assert cpu.f.byte == 0xD7
    assert cpu.q == 0
    assert cpu.pc == 0x1002
    assert cpu.r == 1  # immediate operand does not bump R


def test_ld_hl_n_immediate() -> None:
    cpu = MemoryCPU()
    cpu.h = 0x22
    cpu.l = 0x11
    _program(cpu, 0x0000, 0x36, 0x99)  # LD (HL),0x99
    assert cpu.decode_and_execute() == 10
    assert cpu.read_byte(0x2211) == 0x99
    assert cpu.pc == 0x0002
    assert cpu.q == 0


# --- LD A,(BC)/(DE) and LD (BC)/(DE),A --------------------------------------


def test_ld_a_bc_sets_wz_then_increments() -> None:
    cpu = MemoryCPU()
    cpu.b = 0x12
    cpu.c = 0x34
    cpu.write_byte(0x1234, 0xAB)
    cpu.wz = 0xFFFF  # must be overwritten by the instruction
    _program(cpu, 0x0000, 0x0A)  # LD A,(BC)
    assert cpu.decode_and_execute() == 7
    assert cpu.a == 0xAB
    assert cpu.wz == 0x1235  # WZ <- BC, then WZ++
    assert cpu.q == 0
    assert cpu.pc == 0x0001


def test_ld_a_de_sets_wz_then_increments() -> None:
    cpu = MemoryCPU()
    cpu.d = 0x56
    cpu.e = 0x78
    cpu.write_byte(0x5678, 0xCD)
    _program(cpu, 0x0000, 0x1A)  # LD A,(DE)
    assert cpu.decode_and_execute() == 7
    assert cpu.a == 0xCD
    assert cpu.wz == 0x5679
    assert cpu.q == 0


def test_ld_bc_a_sets_wz_to_a_high_byte() -> None:
    cpu = MemoryCPU()
    cpu.b = 0x8A
    cpu.c = 0x1E
    cpu.a = 0xA2
    cpu.wz = 0xA045  # must be overwritten by the instruction
    _program(cpu, 0x0000, 0x02)  # LD (BC),A
    assert cpu.decode_and_execute() == 7
    assert cpu.read_byte(0x8A1E) == 0xA2
    # WZ <- BC, then WZ <- A:(WZ+1)L  (0x8A1F low byte 0x1F, A high byte)
    assert cpu.wz == 0xA21F
    assert cpu.q == 0
    assert cpu.pc == 0x0001


def test_ld_de_a_sets_wz_to_a_high_byte() -> None:
    cpu = MemoryCPU()
    cpu.d = 0x0C
    cpu.e = 0x81
    cpu.a = 0x4B
    _program(cpu, 0x0000, 0x12)  # LD (DE),A
    assert cpu.decode_and_execute() == 7
    assert cpu.read_byte(0x0C81) == 0x4B
    assert cpu.wz == 0x4B82  # (0x0C82 low byte 0x82, A high byte)
    assert cpu.q == 0


# --- LD A,(nn) and LD (nn),A ------------------------------------------------


def test_ld_a_nn_sets_wz_then_increments() -> None:
    cpu = MemoryCPU()
    cpu.write_byte(0x3456, 0xDC)
    cpu.wz = 0x0000
    _program(cpu, 0x1000, 0x3A, 0x56, 0x34)  # LD A,(0x3456)
    assert cpu.decode_and_execute() == 13
    assert cpu.a == 0xDC
    assert cpu.wz == 0x3457  # WZ <- nn, then WZ++
    assert cpu.q == 0
    assert cpu.pc == 0x1003
    assert cpu.r == 1  # two operand bytes do not bump R


def test_ld_nn_a_sets_wz_to_a_high_byte() -> None:
    cpu = MemoryCPU()
    cpu.a = 0xCD
    cpu.wz = 0x0000
    _program(cpu, 0x1000, 0x32, 0x56, 0x34)  # LD (0x3456),A
    assert cpu.decode_and_execute() == 13
    assert cpu.read_byte(0x3456) == 0xCD
    assert cpu.wz == 0xCD57  # (0x3457 low byte 0x57, A high byte)
    assert cpu.q == 0
    assert cpu.pc == 0x1003


# --- LD I,A / LD R,A (ED-prefixed, no flags affected) -----------------------


def test_ld_i_a() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x33
    cpu.f.byte = 0xD7
    _program(cpu, 0x0000, 0xED, 0x47)  # LD I,A
    assert cpu.decode_and_execute() == 9
    assert cpu.i == 0x33
    assert cpu.f.byte == 0xD7  # no flags affected
    assert cpu.q == 0
    assert cpu.pc == 0x0002
    assert cpu.r == 2  # ED prefix + sub-opcode, both fetched


def test_ld_r_a() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x44
    cpu.f.byte = 0xD7
    _program(cpu, 0x0000, 0xED, 0x4F)  # LD R,A
    assert cpu.decode_and_execute() == 9
    assert cpu.r == 0x44
    assert cpu.f.byte == 0xD7
    assert cpu.q == 0
    assert cpu.pc == 0x0002


# --- LD A,I / LD A,R (ED-prefixed, flags affected) --------------------------


def test_ld_a_i_sets_flags_from_i_and_iff2() -> None:
    cpu = MemoryCPU()
    cpu.i = 0x80
    cpu.iff2 = True
    cpu.f.byte = FLAG_C  # C must be preserved; N/H cleared
    _program(cpu, 0x0000, 0xED, 0x57)  # LD A,I
    assert cpu.decode_and_execute() == 9
    assert cpu.a == 0x80
    assert cpu.f.s == 1
    assert cpu.f.z == 0
    assert cpu.f.pv == 1  # P/V <- IFF2
    assert cpu.f.h == 0
    assert cpu.f.n == 0
    assert cpu.f.c == 1  # C preserved
    assert cpu.f.x == 0  # X/Y from I (0x80: bits 3/5 clear)
    assert cpu.f.y == 0
    assert cpu.f.byte == FLAG_S | FLAG_PV | FLAG_C
    assert cpu.q == cpu.f.byte  # flags modified -> Q latched


def test_ld_a_i_zero_sets_z_and_xy() -> None:
    cpu = MemoryCPU()
    cpu.i = 0x2A  # 0010 1010: bits 3 and 5 set
    cpu.iff2 = False
    cpu.f.byte = 0x00
    _program(cpu, 0x0000, 0xED, 0x57)  # LD A,I
    assert cpu.decode_and_execute() == 9
    assert cpu.a == 0x2A
    assert cpu.f.s == 0
    assert cpu.f.z == 0
    assert cpu.f.pv == 0
    assert cpu.f.x == 1  # bit 3 of I
    assert cpu.f.y == 1  # bit 5 of I
    assert cpu.f.h == 0
    assert cpu.f.n == 0
    assert cpu.f.c == 0
    assert cpu.f.byte == FLAG_X | FLAG_Y
    assert cpu.q == cpu.f.byte


def test_ld_a_r_reads_post_fetch_r_and_sets_flags() -> None:
    cpu = MemoryCPU()
    cpu.r = 0x00
    cpu.iff2 = True
    cpu.f.byte = 0x00
    _program(cpu, 0x0000, 0xED, 0x5F)  # LD A,R
    assert cpu.decode_and_execute() == 9
    # R is incremented once per opcode byte fetched (ED, then 0x5F).
    assert cpu.r == 0x02
    assert cpu.a == 0x02
    assert cpu.f.s == 0
    assert cpu.f.z == 0
    assert cpu.f.pv == 1  # P/V <- IFF2
    assert cpu.f.h == 0
    assert cpu.f.n == 0
    assert cpu.f.c == 0
    assert cpu.f.x == 0
    assert cpu.f.y == 0
    assert cpu.f.byte == FLAG_PV
    assert cpu.q == cpu.f.byte
