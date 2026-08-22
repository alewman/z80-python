"""Deterministic regression coverage for the FD indexed SUB A,(IY+d) form.

``_execute_index`` routes sub-opcode 0x96 for both DD/FD prefixes to
``_op_sub_a_index_mem``, which consumes the signed displacement via
``_index_displacement_addr`` (latching the effective address into WZ) and
feeds the addressed byte to the ordinary SUB helper (``_alu_a`` group 2,
i.e. ``_sub(A, value, 0)``):

    FD 96 d  SUB A,(IY+d)

This file pins the FD 96 form with one direct deterministic unit test: it
places the prefix, opcode and displacement byte (FD 96 02) in RAM at PC,
seeds A, IY and the addressed memory byte, executes exactly one instruction,
and asserts:

* A receives the difference from the existing SUB helper (``_sub(A, source, 0)``).
* IY is unchanged.
* the PC advances by 3 (prefix + opcode + the single displacement byte).
* WZ (MEMPTR) latches the effective address 0x5002.
* Q latches the new F value, because SUB writes the F register.
* the instruction consumes 19 T-states, the audited indexed-memory family
  count.
"""

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


def test_fd_96_sub_a_mem_at_iy_plus_d() -> None:
    """FD 96 02 SUB A,(IY+2): 0x50 - 0x20 = 0x30, F/WZ/PC/Q/T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    cpu.a = 0x50
    cpu.write_byte(0x2000, 0xFD)
    cpu.write_byte(0x2001, 0x96)
    cpu.write_byte(0x2002, 0x02)
    cpu.write_byte(0x5002, 0x20)  # addressed memory operand

    tstates = cpu.decode_and_execute()

    # 0x50 - 0x20 = 0x30 -> S=0 Z=0 Y=1 H=0 X=0 PV=0 N=1 C=0 (F = 0x22).
    assert cpu.a == 0x30
    assert int(cpu.f) == 0x22
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert cpu.wz == 0x5002  # WZ (MEMPTR) latches the effective address
    assert cpu.q == 0x22  # Q latches the new F value (SUB writes F)
    assert tstates == 19
