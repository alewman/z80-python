"""Unit tests for the Z80 exchange group (src/z80/cpu.py), opcode 0xEB.

The authoritative check for this group is the per-opcode SingleStepTests/z80
vector suite run by ``tests/test_z80.py`` (``eb.json`` for EX DE,HL, 1000
cases).  The vector runner, however, counts an unimplemented opcode as a
skip, so a missing handler can hide behind a green suite.  The tests here are
a fast, deterministic complement that pins down the documented semantics of
EX DE,HL (0xEB) directly -- the register swap, the single fetched-byte PC
advance, the one refresh-register increment, the untouched F/WZ, the cleared
Q flag, the 4-T-state timing and the untouched memory -- so a regression is
visible as a real failure instead of a skip.

Diagnosed defect (audit-z80-correctness-defect): the CPU dispatcher contract
documents 0xEB as implemented, but ``_execute_main`` has no dispatch branch
or handler for it, so execution reaches the ``NotImplementedError`` fallback.
Until that is fixed, the tests in this module fail with that exact error,
which is the intended regression signal.
"""

from __future__ import annotations

from z80.cpu import Z80CPU


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


# --- EX DE,HL (0xEB) ---------------------------------------------------------


def test_ex_de_hl_swaps_de_and_hl() -> None:
    cpu = MemoryCPU()
    _set_de(cpu, 0x1234)
    _set_hl(cpu, 0xABCD)
    _program(cpu, 0x0000, 0xEB)  # EX DE,HL
    cpu.decode_and_execute()
    assert cpu._de() == 0xABCD
    assert cpu._hl() == 0x1234


def test_ex_de_hl_pc_advances_by_one_fetched_opcode() -> None:
    cpu = MemoryCPU()
    _set_de(cpu, 0x1234)
    _set_hl(cpu, 0xABCD)
    _program(cpu, 0x1000, 0xEB, 0x00)  # EX DE,HL followed by a NOP
    cpu.decode_and_execute()
    assert cpu.pc == 0x1001  # only the single opcode byte was fetched


def test_ex_de_hl_increments_r_exactly_once() -> None:
    cpu = MemoryCPU()
    _set_de(cpu, 0x1234)
    _set_hl(cpu, 0xABCD)
    cpu.r = 0x41
    _program(cpu, 0x0000, 0xEB)
    cpu.decode_and_execute()
    assert cpu.r == 0x42  # one opcode fetch -> one refresh increment


def test_ex_de_hl_preserves_f_and_wz_and_clears_q() -> None:
    cpu = MemoryCPU()
    _set_de(cpu, 0x1234)
    _set_hl(cpu, 0xABCD)
    cpu.f.byte = 0xD7  # S=1 Z=1 Y=1 H=0 X=1 PV=1 N=1 C=1
    cpu.wz = 0x4321
    cpu.q = 0xD7
    _program(cpu, 0x0000, 0xEB)
    cpu.decode_and_execute()
    assert cpu.f.byte == 0xD7  # F untouched
    assert cpu.wz == 0x4321  # WZ (MEMPTR) untouched
    assert cpu.q == 0  # exchange does not write F, so Q is cleared


def test_ex_de_hl_takes_four_t_states() -> None:
    cpu = MemoryCPU()
    _set_de(cpu, 0x1234)
    _set_hl(cpu, 0xABCD)
    _program(cpu, 0x0000, 0xEB)
    assert cpu.decode_and_execute() == 4


def test_ex_de_hl_swaps_boundary_values_and_touches_no_memory() -> None:
    cpu = MemoryCPU()
    _set_de(cpu, 0xFFFF)
    _set_hl(cpu, 0x0000)
    cpu.f.byte = 0x00
    _program(cpu, 0x7FFF, 0xEB)  # exercise a non-zero, non-page-aligned PC
    cpu.decode_and_execute()
    assert cpu._de() == 0x0000
    assert cpu._hl() == 0xFFFF
    # A pure register exchange produces no carry/half-carry and no flags at all.
    assert cpu.f.byte == 0x00
    # And it must not touch memory (the opcode byte stays in place).
    assert cpu.read_byte(0x7FFF) == 0xEB
