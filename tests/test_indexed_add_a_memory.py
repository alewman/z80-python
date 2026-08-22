"""Red-first regression coverage for the DD/FD indexed ADD A,(IX/IY+d) forms.

audit-indexed-add-a-contract established the indexed ADD A memory family as
exactly two opcode forms::

    DD 86 d  ADD A,(IX+d)
    FD 86 d  ADD A,(IY+d)

Each test is a direct deterministic unit test: it places the prefix, opcode
and one signed displacement byte in RAM, seeds A, the index register and the
addressed memory byte, executes exactly one instruction, and asserts the
invariants the audit established:

* A receives the sum from the existing ADD helper (``_add(A, source, 0)``):
  the masked result with S/Z/X/Y from the result, N cleared, C from the
  unmasked sum, and the signed-overflow and half-carry formulas.
* the index register is unchanged.
* the PC advances by 3 (prefix + opcode + the single displacement byte).
* WZ (MEMPTR) latches the effective address, exactly as the indexed memory
  seam ``_index_displacement_addr`` does for every (IX+d)/(IY+d) operand.
* the instruction consumes 19 T-states, the audited indexed-memory family
  count (same as LD r,(IX/IY+d) and LD (IX/IY+d),n).
* Q latches the new F value, because ADD writes the F register.

Across the pair, one test exercises a normal sum (A=0x10 + (0x4002)=0x20)
and the other an arithmetic edge case (A=0x7F + (0x4FFD)=0x01, the signed
overflow into the sign bit that sets S/H/P/V).  No parametrization, no
vector-file plumbing -- two standalone test functions, one per opcode form.

Why this file is red by design: the CPU core (src/z80/cpu.py) dispatches the
DD/FD index-prefix family through ``_execute_index``, but sub-opcode 0x86 is
not handled there yet, so both forms raise ``NotImplementedError``.  Every
unit test below therefore fails today, because the family is unimplemented --
that is the regression this file pins.  When the indexed ADD A memory forms
get implemented, these same tests flip green only if the accumulator, the
full flag register, the unchanged index register, the PC advance, the WZ
latch, the Q latch and the T-state count match the documented semantics
exactly.
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
    the DD/FD indexed ADD A memory forms have no handler in
    ``_execute_index`` yet, so every instruction in this module fails until
    the CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            f"DD/FD indexed ADD A,(IX/IY+d) is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_dd_86_add_a_mem_at_ix_plus_d() -> None:
    """DD 86 d ADD A,(IX+d): normal sum 0x10 + 0x20 = 0x30, IX/WZ/PC/Q."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    cpu.a = 0x10
    displacement = 2  # signed +2
    target = (cpu.ix + displacement) & 0xFFFF
    cpu.write_byte(target, 0x20)  # addressed memory operand

    tstates = _run(cpu, bytes([0xDD, 0x86, displacement & 0xFF]))

    # Normal sum: 0x30 -> S=0 Z=0 Y=1 H=0 X=0 PV=0 N=0 C=0 (F = 0x20).
    assert cpu.a == 0x30
    assert int(cpu.f) == 0x20
    assert cpu.f.s == 0
    assert cpu.f.z == 0
    assert cpu.f.y == 1
    assert cpu.f.h == 0
    assert cpu.f.x == 0
    assert cpu.f.pv == 0
    assert cpu.f.n == 0
    assert cpu.f.c == 0
    assert cpu.ix == 0x4000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert cpu.wz == target  # WZ (MEMPTR) latches the effective address
    assert cpu.q == int(cpu.f)  # Q latches the new F (ADD writes F)
    assert tstates == 19


def test_fd_86_add_a_mem_at_iy_minus_d() -> None:
    """FD 86 d ADD A,(IY+d): signed overflow edge case 0x7F + 0x01 = 0x80."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    cpu.a = 0x7F
    displacement = -3  # signed -3 -> 0xFD in RAM
    target = (cpu.iy + displacement) & 0xFFFF
    cpu.write_byte(target, 0x01)  # addressed memory operand

    tstates = _run(cpu, bytes([0xFD, 0x86, displacement & 0xFF]))

    # 0x7F + 0x01 overflows into the sign bit: A=0x80, S=1, H=1, PV=1,
    # Z=0, Y=0, X=0, N=0, C=0 (F = 0x80 | 0x10 | 0x04 = 0x94).
    assert cpu.a == 0x80
    assert int(cpu.f) == 0x94
    assert cpu.f.s == 1
    assert cpu.f.z == 0
    assert cpu.f.y == 0
    assert cpu.f.h == 1
    assert cpu.f.x == 0
    assert cpu.f.pv == 1
    assert cpu.f.n == 0
    assert cpu.f.c == 0
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert cpu.wz == target  # WZ (MEMPTR) latches the effective address
    assert cpu.q == int(cpu.f)  # Q latches the new F (ADD writes F)
    assert tstates == 19
