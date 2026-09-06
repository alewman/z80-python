"""Unit tests for the Z80 ED block transfer and search group (src/z80_python/).

The authoritative check for this group is the per-opcode SingleStepTests/z80
vector suite run by ``tests/test_z80.py`` (ed a0.json/ed a1.json/ed a8.json/
ed a9.json/ed b0.json/ed b1.json/ed b8.json/ed b9.json, 1000 cases each,
covering LDI/LDD/CPI/CPD and their repeated LDIR/LDDR/CPIR/CPDR variants).
The tests here are a fast, readable complement that pins down the documented
semantics -- BC as the byte counter, HL/DE as the pointers, the flag recipe
(H/N/P/V plus the block group's unusual X/Y sources), the WZ (MEMPTR)
updates, the PC rewind that makes the repeated variants interruptible, the
T-state counts and the Q latching -- so a regression is visible in a single
test name instead of a 1000-case vector diff.

Repeated mode: LDIR/LDDR/CPIR/CPDR do *not* loop inside one
``decode_and_execute`` call.  Each call performs one step and rewinds PC to
the instruction when the loop must continue, so the emulator's instruction
loop can service an interrupt (or a HALT) between iterations and then resume
the transfer exactly where it left off -- see
``test_ldir_loop_can_be_interrupted_between_iterations``.
"""

from __future__ import annotations

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


def _set_de(cpu: MemoryCPU, value: int) -> None:
    cpu.d = (value >> 8) & 0xFF
    cpu.e = value & 0xFF


def _set_bc(cpu: MemoryCPU, value: int) -> None:
    cpu.b = (value >> 8) & 0xFF
    cpu.c = value & 0xFF


# --- LDI / LDD (one step, 16 T-states) ------------------------------------


def test_ldi_copies_byte_and_steps_pointers_and_counter() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x2000)
    _set_de(cpu, 0x3000)
    _set_bc(cpu, 0x0003)
    cpu.write_byte(0x2000, 0x5A)
    cpu.wz = 0xABCD
    _program(cpu, 0x1000, 0xED, 0xA0)  # LDI
    assert cpu.decode_and_execute() == 16
    assert cpu.read_byte(0x3000) == 0x5A  # (DE) <- (HL)
    assert (cpu.h, cpu.l) == (0x20, 0x01)  # HL++
    assert (cpu.d, cpu.e) == (0x30, 0x01)  # DE++
    assert (cpu.b, cpu.c) == (0x00, 0x02)  # BC--
    assert cpu.f.n == 0
    assert cpu.f.h == 0
    assert cpu.f.pv == 1  # BC - 1 != 0
    assert cpu.wz == 0xABCD  # LDI does not touch WZ
    assert cpu.pc == 0x1002  # one step leaves PC past the instruction
    assert cpu.q == cpu.f.byte  # F was written -> Q latched


def test_ldi_xy_flags_come_from_a_plus_data() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x02
    _set_hl(cpu, 0x2000)
    _set_de(cpu, 0x3000)
    _set_bc(cpu, 0x0001)
    cpu.write_byte(0x2000, 0x00)
    _program(cpu, 0x1000, 0xED, 0xA0)  # LDI
    cpu.decode_and_execute()
    # A + data = 0x02: X copies sum bit 3 (0), Y copies sum bit 1 (1).
    assert cpu.f.x == 0
    assert cpu.f.y == 1


def test_ldi_preserves_s_z_c_and_sets_pv_zero_on_last_byte() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x2000)
    _set_de(cpu, 0x3000)
    _set_bc(cpu, 0x0001)
    cpu.write_byte(0x2000, 0x01)
    cpu.f.byte = 0x55  # S=0 Z=1 Y=1 H=0 X=1 PV=1 N=0 C=1
    _program(cpu, 0x1000, 0xED, 0xA0)  # LDI
    cpu.decode_and_execute()
    assert (cpu.b, cpu.c) == (0x00, 0x00)
    assert cpu.f.pv == 0  # BC - 1 == 0
    assert cpu.f.s == 0  # preserved
    assert cpu.f.z == 1  # preserved
    assert cpu.f.c == 1  # preserved
    # X/Y recomputed from A + data = 0x01 (both clear); N/H cleared.
    assert cpu.f.byte == 0x41


def test_ldd_decrements_pointers() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x2000)
    _set_de(cpu, 0x3000)
    _set_bc(cpu, 0x0002)
    cpu.write_byte(0x2000, 0x7B)
    _program(cpu, 0x1000, 0xED, 0xA8)  # LDD
    assert cpu.decode_and_execute() == 16
    assert cpu.read_byte(0x3000) == 0x7B
    assert (cpu.h, cpu.l) == (0x1F, 0xFF)  # HL--
    assert (cpu.d, cpu.e) == (0x2F, 0xFF)  # DE--
    assert (cpu.b, cpu.c) == (0x00, 0x01)
    assert cpu.f.pv == 1
    assert cpu.pc == 0x1002


# --- CPI / CPD (one step, 16 T-states) ------------------------------------


def test_cpi_compares_and_steps_wz_hl_bc() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x10
    _set_hl(cpu, 0x2000)
    _set_bc(cpu, 0x0003)
    cpu.write_byte(0x2000, 0x05)
    cpu.f.c = 1  # C must be preserved
    cpu.wz = 0x1234
    _program(cpu, 0x1000, 0xED, 0xA1)  # CPI
    assert cpu.decode_and_execute() == 16
    assert cpu.wz == 0x1235  # WZ++
    assert (cpu.h, cpu.l) == (0x20, 0x01)  # HL++
    assert (cpu.b, cpu.c) == (0x00, 0x02)  # BC--
    assert cpu.f.n == 1
    assert cpu.f.pv == 1  # BC - 1 != 0
    assert cpu.f.c == 1  # C preserved
    # A - (HL) = 0x10 - 0x05 = 0x0B: S/Z from the result, H from the
    # bit-3 borrow, X/Y from (result - H) with the block group's shuffle.
    assert cpu.f.s == 0
    assert cpu.f.z == 0
    assert cpu.f.h == 1
    assert cpu.f.x == 1
    assert cpu.f.y == 1
    assert cpu.pc == 0x1002
    assert cpu.q == cpu.f.byte


def test_cpi_equal_sets_zero_and_pv_zero_on_last_byte() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x42
    _set_hl(cpu, 0x2000)
    _set_bc(cpu, 0x0001)
    cpu.write_byte(0x2000, 0x42)
    _program(cpu, 0x1000, 0xED, 0xA1)  # CPI
    cpu.decode_and_execute()
    assert cpu.f.z == 1
    assert cpu.f.pv == 0  # BC reached zero
    assert (cpu.b, cpu.c) == (0x00, 0x00)


def test_cpd_decrements_wz_and_hl() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x10
    _set_hl(cpu, 0x2000)
    _set_bc(cpu, 0x0003)
    cpu.write_byte(0x2000, 0x05)
    cpu.wz = 0x1234
    _program(cpu, 0x1000, 0xED, 0xA9)  # CPD
    assert cpu.decode_and_execute() == 16
    assert cpu.wz == 0x1233  # WZ--
    assert (cpu.h, cpu.l) == (0x1F, 0xFF)  # HL--
    assert (cpu.b, cpu.c) == (0x00, 0x02)
    assert cpu.f.n == 1


# --- LDIR / LDDR (repeated, 21 T-states per step, 16 on the last) ---------


def test_ldir_rewinds_pc_and_sets_wz_and_xy_from_pc_on_repeat() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x2000)
    _set_de(cpu, 0x3000)
    _set_bc(cpu, 0x0003)
    cpu.write_byte(0x2000, 0x11)
    _program(cpu, 0x1000, 0xED, 0xB0)  # LDIR
    assert cpu.decode_and_execute() == 21
    assert cpu.pc == 0x1000  # rewound to re-execute the instruction
    assert cpu.wz == 0x1001  # rewound PC + 1
    assert cpu.f.x == (0x1000 >> 11) & 1  # X/Y from PC bits 11/13
    assert cpu.f.y == (0x1000 >> 13) & 1
    assert (cpu.b, cpu.c) == (0x00, 0x02)
    assert (cpu.h, cpu.l) == (0x20, 0x01)
    assert (cpu.d, cpu.e) == (0x30, 0x01)
    assert cpu.read_byte(0x3000) == 0x11


def test_ldir_last_iteration_does_not_rewind() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x2000)
    _set_de(cpu, 0x3000)
    _set_bc(cpu, 0x0001)
    cpu.write_byte(0x2000, 0x11)
    cpu.wz = 0xABCD
    _program(cpu, 0x1000, 0xED, 0xB0)  # LDIR
    assert cpu.decode_and_execute() == 16
    assert cpu.pc == 0x1002  # loop done: PC stays past the instruction
    assert cpu.wz == 0xABCD  # WZ untouched on the final step
    assert (cpu.b, cpu.c) == (0x00, 0x00)
    assert cpu.f.pv == 0


def test_ldir_full_loop_copies_whole_block() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x2000)
    _set_de(cpu, 0x3000)
    _set_bc(cpu, 0x0003)
    for offset in range(3):
        cpu.write_byte(0x2000 + offset, 0x10 + offset)
    _program(cpu, 0x1000, 0xED, 0xB0)  # LDIR
    total = 0
    while (cpu.b, cpu.c) != (0x00, 0x00):
        total += cpu.decode_and_execute()
    assert total == 21 + 21 + 16  # two repeats + one final step
    assert (cpu.b, cpu.c) == (0x00, 0x00)
    assert cpu.pc == 0x1002
    assert cpu.read_byte(0x3000) == 0x10
    assert cpu.read_byte(0x3001) == 0x11
    assert cpu.read_byte(0x3002) == 0x12


def test_ldir_loop_can_be_interrupted_between_iterations() -> None:
    """Repeated mode is resumable: an interrupt can run between iterations.

    LDIR leaves PC rewound at the instruction after every non-final step, so
    the emulator can service an interrupt (or HALT) between iterations and
    then resume the transfer with BC/HL/DE exactly as the hardware left them.
    """
    cpu = MemoryCPU()
    _set_hl(cpu, 0x2000)
    _set_de(cpu, 0x3000)
    _set_bc(cpu, 0x0003)
    for offset in range(3):
        cpu.write_byte(0x2000 + offset, 0x10 + offset)
    _program(cpu, 0x1000, 0xED, 0xB0)  # LDIR
    # First iteration: one byte copied, PC rewound to the LDIR.
    assert cpu.decode_and_execute() == 21
    assert cpu.pc == 0x1000
    assert (cpu.b, cpu.c) == (0x00, 0x02)
    # Interrupt handler runs between iterations (a register-preserving body).
    _program(cpu, 0x0000, 0x3E, 0x99)  # LD A,0x99
    cpu.decode_and_execute()
    assert cpu.a == 0x99
    assert (cpu.b, cpu.c) == (0x00, 0x02)  # loop state untouched by handler
    assert (cpu.h, cpu.l) == (0x20, 0x01)
    assert (cpu.d, cpu.e) == (0x30, 0x01)
    # Resume the transfer; the remaining two iterations finish the block.
    cpu.pc = 0x1000
    assert cpu.decode_and_execute() == 21
    assert cpu.decode_and_execute() == 16  # final step
    assert (cpu.b, cpu.c) == (0x00, 0x00)
    assert cpu.pc == 0x1002
    assert cpu.read_byte(0x3000) == 0x10
    assert cpu.read_byte(0x3001) == 0x11
    assert cpu.read_byte(0x3002) == 0x12


def test_ldir_with_bc_zero_wraps_counter_and_keeps_repeating() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x2000)
    _set_de(cpu, 0x3000)
    _set_bc(cpu, 0x0000)
    cpu.write_byte(0x2000, 0x5A)
    _program(cpu, 0x1000, 0xED, 0xB0)  # LDIR
    assert cpu.decode_and_execute() == 21  # still repeats (65536 iterations)
    assert (cpu.b, cpu.c) == (0xFF, 0xFF)  # counter wrapped
    assert cpu.f.pv == 1
    assert cpu.pc == 0x1000


def test_lddr_full_loop_copies_block_backwards() -> None:
    cpu = MemoryCPU()
    _set_hl(cpu, 0x2002)
    _set_de(cpu, 0x3002)
    _set_bc(cpu, 0x0003)
    for offset in range(3):
        cpu.write_byte(0x2000 + offset, 0xA0 + offset)
    _program(cpu, 0x1000, 0xED, 0xB8)  # LDDR
    total = 0
    while (cpu.b, cpu.c) != (0x00, 0x00):
        total += cpu.decode_and_execute()
    assert total == 21 + 21 + 16
    assert (cpu.b, cpu.c) == (0x00, 0x00)
    assert cpu.pc == 0x1002
    assert (cpu.h, cpu.l) == (0x1F, 0xFF)  # stepped down past the block
    assert (cpu.d, cpu.e) == (0x2F, 0xFF)
    assert cpu.read_byte(0x3000) == 0xA0
    assert cpu.read_byte(0x3001) == 0xA1
    assert cpu.read_byte(0x3002) == 0xA2


# --- CPIR / CPDR (repeated, 21 T-states per step, 16 on the last) ---------


def test_cpir_repeats_until_match_found() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x11
    _set_hl(cpu, 0x2000)
    _set_bc(cpu, 0x0004)
    for offset, value in enumerate((0x01, 0x02, 0x11, 0x04)):
        cpu.write_byte(0x2000 + offset, value)
    cpu.wz = 0x5000
    _program(cpu, 0x1000, 0xED, 0xB1)  # CPIR
    total = 0
    while cpu.f.z == 0 and (cpu.b, cpu.c) != (0x00, 0x00):
        total += cpu.decode_and_execute()
    # Three comparisons (0x01, 0x02, then 0x11 matches); the matching step
    # is the final one and costs 16 T-states.  Each repeat cycle clobbers WZ
    # with the rewound PC + 1 (0x1001), so the final CPI step leaves WZ at
    # 0x1002 rather than at the pre-loop 0x5000 + 3.
    assert total == 21 + 21 + 16
    assert cpu.f.z == 1
    assert (cpu.b, cpu.c) == (0x00, 0x01)  # 4 - 3
    assert (cpu.h, cpu.l) == (0x20, 0x03)
    assert cpu.wz == 0x1002  # final CPI step: 0x1001 + 1
    assert cpu.pc == 0x1002  # match found: no rewind


def test_cpir_stops_when_bc_reaches_zero_without_match() -> None:
    cpu = MemoryCPU()
    cpu.a = 0xFF
    _set_hl(cpu, 0x2000)
    _set_bc(cpu, 0x0002)
    cpu.write_byte(0x2000, 0x01)
    cpu.write_byte(0x2001, 0x02)
    _program(cpu, 0x1000, 0xED, 0xB1)  # CPIR
    total = 0
    while cpu.f.z == 0 and (cpu.b, cpu.c) != (0x00, 0x00):
        total += cpu.decode_and_execute()
    assert total == 21 + 16
    assert cpu.f.z == 0
    assert cpu.f.pv == 0  # BC exhausted
    assert (cpu.b, cpu.c) == (0x00, 0x00)
    assert cpu.pc == 0x1002


def test_cpdr_repeats_backwards_until_match() -> None:
    cpu = MemoryCPU()
    cpu.a = 0x02
    _set_hl(cpu, 0x2003)
    _set_bc(cpu, 0x0004)
    for offset, value in enumerate((0x01, 0x02, 0x03, 0x04)):
        cpu.write_byte(0x2000 + offset, value)
    cpu.wz = 0x6000
    _program(cpu, 0x1000, 0xED, 0xB9)  # CPDR
    total = 0
    while cpu.f.z == 0 and (cpu.b, cpu.c) != (0x00, 0x00):
        total += cpu.decode_and_execute()
    # Backwards: 0x04 (no), 0x03 (no), 0x02 (match).  Each repeat cycle
    # clobbers WZ with the rewound PC + 1 (0x1001), so the final CPD step
    # leaves WZ at 0x1000 rather than at the pre-loop 0x6000 - 3.
    assert total == 21 + 21 + 16
    assert cpu.f.z == 1
    assert (cpu.b, cpu.c) == (0x00, 0x01)
    assert (cpu.h, cpu.l) == (0x20, 0x00)  # 0x2003 - 3
    assert cpu.wz == 0x1000  # final CPD step: 0x1001 - 1
    assert cpu.pc == 0x1002
