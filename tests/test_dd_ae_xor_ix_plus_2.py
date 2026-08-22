"""Red-first regression coverage for the DD indexed XOR A,(IX+d) form.

confirm-dd-ae-seams established that DD AE can reuse
``_index_displacement_addr(prefix)`` for the signed IX/IY displacement and WZ
update, and ordinary XOR dispatch uses ``_alu_a`` with group 5 (which invokes
``_xor``) for the full S/Z/H/PV/N/C/X/Y flag set::

    DD AE d  XOR A,(IX+d)
    FD AE d  XOR A,(IY+d)

This file pins the DD AE form with one direct deterministic unit test: it
places the prefix, opcode and one signed displacement byte in RAM, seeds A,
the index register and the addressed memory byte, executes exactly one
instruction, and asserts the invariants:

* A receives the bitwise XOR from the existing XOR helper (``_xor(A, source)``).
* the index register is unchanged.
* the PC advances by 3 (prefix + opcode + the single displacement byte).
* WZ (MEMPTR) latches the effective address, exactly as the indexed memory
  seam ``_index_displacement_addr`` does for every (IX+d)/(IY+d) operand.
* Q latches the new F value, because XOR writes the F register.
* the instruction consumes 19 T-states, the audited indexed-memory family
  count (same as LD r,(IX/IY+d) and LD (IX/IY+d),n).

Why this file is red by design: the CPU core (src/z80/cpu.py) dispatches the
DD/FD index-prefix family through ``_execute_index``, but sub-opcode 0xAE is
not handled there yet, so it raises ``NotImplementedError``.  The unit test
below therefore fails today, because the family is unimplemented -- that is
the regression this file pins.  When the indexed XOR A memory form gets
implemented, this test flips green only if the accumulator, the full flag
register, the unchanged index register, the PC advance, the WZ latch, the Q
latch and the T-state count match the documented semantics exactly.
"""

from __future__ import annotations

import pytest

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


def _run(cpu: MemoryCPU, opcode_bytes: bytes) -> int:
    """Place ``opcode_bytes`` at ``pc``, execute, and return the T-state count.

    A ``NotImplementedError`` here is the whole point of the red regression:
    the DD/FD indexed XOR A memory form has no handler in ``_execute_index``
    yet, so the instruction fails until the CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            f"DD/FD indexed XOR A,(IX/IY+d) is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_dd_ae_xor_a_mem_at_ix_plus_d() -> None:
    """DD AE 02 XOR A,(IX+2): 0xFF ^ 0x00 = 0xFF, F/WZ/PC/Q/T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    cpu.a = 0xFF
    displacement = 2  # signed +2
    target = (cpu.ix + displacement) & 0xFFFF
    cpu.write_byte(target, 0x00)  # addressed memory operand

    tstates = _run(cpu, bytes([0xDD, 0xAE, displacement & 0xFF]))

    # 0xFF ^ 0x00 = 0xFF -> S=1 Z=0 Y=1 H=0 X=1 PV=1 N=0 C=0 (F = 0xAC).
    assert cpu.a == 0xFF
    assert int(cpu.f) == 0xAC
    assert cpu.ix == 0x4000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert cpu.wz == target  # WZ (MEMPTR) latches the effective address
    assert cpu.q == int(cpu.f)  # Q latches the new F (XOR writes F)
    assert tstates == 19
