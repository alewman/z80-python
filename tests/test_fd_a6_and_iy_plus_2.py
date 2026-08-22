"""Deterministic regression coverage for the FD indexed AND A,(IY+d) form.

``_execute_index`` routes sub-opcode 0xA6 for both DD/FD prefixes to
``_op_and_a_index_mem``, which consumes the signed displacement via
``_index_displacement_addr`` (latching the effective address into WZ) and
feeds the addressed byte to the ordinary AND helper (``_alu_a`` group 4,
i.e. ``_and(A, value)``):

    FD A6 d  AND A,(IY+d)

This file pins the FD A6 form with one direct deterministic unit test: it
places the prefix, opcode and displacement byte (FD A6 02) in RAM at PC,
seeds A, IY and the addressed memory byte, executes exactly one instruction,
and asserts:

* A receives the bitwise AND from the existing AND helper (``_and(A, source)``).
* IY is unchanged.
* the PC advances by 3 (prefix + opcode + the single displacement byte).
* WZ (MEMPTR) latches the effective address 0x5002.
* Q latches the new F value, because AND writes the F register.
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


def test_fd_a6_and_a_mem_at_iy_plus_d() -> None:
    """FD A6 02 AND A,(IY+2): 0xF0 & 0x0F = 0x00, F/WZ/PC/Q/T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    cpu.a = 0xF0
    cpu.write_byte(0x2000, 0xFD)
    cpu.write_byte(0x2001, 0xA6)
    cpu.write_byte(0x2002, 0x02)
    cpu.write_byte(0x5002, 0x0F)  # addressed memory operand

    tstates = cpu.decode_and_execute()

    # 0xF0 & 0x0F = 0x00 -> S=0 Z=1 Y=0 H=1 X=0 PV=1 N=0 C=0 (F = 0x54).
    assert cpu.a == 0x00
    assert int(cpu.f) == 0x54
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert cpu.wz == 0x5002  # WZ (MEMPTR) latches the effective address
    assert cpu.q == 0x54  # Q latches the new F value (AND writes F)
    assert tstates == 19
