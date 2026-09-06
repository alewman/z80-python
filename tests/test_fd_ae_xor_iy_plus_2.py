"""Deterministic regression coverage for the FD indexed XOR A,(IY+d) form.

The dispatch inspection (inspect-fd-ae-shared-dispatch) confirmed that
``execute()`` routes the FD prefix to ``_execute_index(0xFD, sub-opcode)`` and
that sub-opcode 0xAE is dispatched to ``_op_xor_a_index_mem(prefix)``.  That
helper consumes the signed displacement via ``_index_displacement_addr``
(latching the effective address into WZ, using ``_get_index`` which returns
IY for every non-DD prefix) and feeds the addressed byte to the ordinary XOR
helper (``_alu_a`` group 5, i.e. ``_xor(A, value)``):

    FD AE d  XOR A,(IY+d)

This file pins the FD AE form with one direct deterministic unit test: it
places the prefix, opcode and displacement byte (FD AE 02) in RAM at PC,
seeds A, IY and the addressed memory byte, executes exactly one instruction,
and asserts:

* A receives the bitwise XOR from the existing XOR helper (``_xor(A, source)``).
* IY is unchanged.
* the PC advances by 3 (prefix + opcode + the single displacement byte).
* WZ (MEMPTR) latches the effective address 0x5002.
* Q latches the new F value, because XOR writes the F register.
* the instruction consumes 19 T-states, the audited indexed-memory family
  count.
"""

from __future__ import annotations

from z80_python import Z80CPU


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


def test_fd_ae_xor_a_mem_at_iy_plus_d() -> None:
    """FD AE 02 XOR A,(IY+2): 0xF0 ^ 0x0F = 0xFF, F/WZ/PC/Q/T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    cpu.a = 0xF0
    cpu.write_byte(0x2000, 0xFD)
    cpu.write_byte(0x2001, 0xAE)
    cpu.write_byte(0x2002, 0x02)
    cpu.write_byte(0x5002, 0x0F)  # addressed memory operand

    tstates = cpu.decode_and_execute()

    # 0xF0 ^ 0x0F = 0xFF -> S=1 Z=0 Y=1 H=0 X=1 PV=1 N=0 C=0 (F = 0xAC).
    assert cpu.a == 0xFF
    assert int(cpu.f) == 0xAC
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert cpu.wz == 0x5002  # WZ (MEMPTR) latches the effective address
    assert cpu.q == 0xAC  # Q latches the new F value (XOR writes F)
    assert tstates == 19
