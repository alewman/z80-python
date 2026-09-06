"""Red-first regression coverage for the DD/FD indexed LD (IX/IY+d),n forms.

audit-indexed-immediate-store established the indexed immediate store family
as exactly two opcode forms::

    DD 36 d n  LD (IX+d),n
    FD 36 d n  LD (IY+d),n

Each test is a direct deterministic unit test: it places the prefix, opcode,
one signed displacement byte and the immediate value byte in RAM, seeds the
index register and an addressed-memory sentinel, executes exactly one
instruction, and asserts the invariants the audit established: the target
memory byte receives the immediate value ``n``, the index register is
unchanged, the PC advances by 4 (prefix + opcode + displacement + immediate),
the F register is untouched, WZ (MEMPTR) latches the effective address, the
undocumented Q flag is cleared (the instruction does not modify F) and the
instruction consumes 19 T-states.  No parametrization, no vector-file
plumbing -- two standalone test functions, one per opcode form.

Why this file is red by design: the CPU core (src/z80_python/) dispatches the
DD/FD index-prefix family through ``_execute_index``, but sub-opcode 0x36 is
not handled there yet, so both forms raise ``NotImplementedError``.  Every
unit test below therefore fails today, because the family is unimplemented --
that is the regression this file pins.  When the indexed immediate store
forms get implemented, these same tests flip green only if the destination
memory byte, the unchanged index register, the PC advance, the untouched
flags, the WZ latch, the cleared Q flag and the T-state count match the
documented semantics exactly.
"""

from __future__ import annotations

import pytest

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


def _run(cpu: MemoryCPU, opcode_bytes: bytes) -> int:
    """Place ``opcode_bytes`` at ``pc``, execute, and return the T-state count.

    A ``NotImplementedError`` here is the whole point of the red regression:
    the DD/FD indexed LD (IX/IY+d),n forms have no handler in
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
            f"DD/FD indexed LD (IX/IY+d),n is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_dd_36_ld_mem_at_ix_plus_d_n() -> None:
    """DD 36 d n LD (IX+d),n: (IX+d) <- n, IX/WZ/PC/F/Q semantics."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    displacement = 2  # signed +2
    immediate = 0x5A
    target = (cpu.ix + displacement) & 0xFFFF
    cpu.write_byte(target, 0x00)  # addressed-memory sentinel
    flags_before = int(cpu.f)

    tstates = _run(cpu, bytes([0xDD, 0x36, displacement & 0xFF, immediate]))

    assert cpu.memory[target] == immediate  # target memory receives n
    assert cpu.ix == 0x4000  # index register unchanged
    assert cpu.pc == 0x2004  # prefix + opcode + displacement + immediate
    assert int(cpu.f) == flags_before  # instruction does not modify F
    assert cpu.wz == target  # WZ (MEMPTR) latches the effective address
    assert cpu.q == 0  # Q cleared: F was not modified
    assert tstates == 19


def test_fd_36_ld_mem_at_iy_minus_d_n() -> None:
    """FD 36 d n LD (IY+d),n: (IY+d) <- n, IY/WZ/PC/F/Q semantics."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    displacement = -3  # signed -3 -> 0xFD in RAM
    immediate = 0xA3
    target = (cpu.iy + displacement) & 0xFFFF
    cpu.write_byte(target, 0x00)  # addressed-memory sentinel
    flags_before = int(cpu.f)

    tstates = _run(cpu, bytes([0xFD, 0x36, displacement & 0xFF, immediate]))

    assert cpu.memory[target] == immediate  # target memory receives n
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.pc == 0x2004  # prefix + opcode + displacement + immediate
    assert int(cpu.f) == flags_before  # instruction does not modify F
    assert cpu.wz == target  # WZ (MEMPTR) latches the effective address
    assert cpu.q == 0  # Q cleared: F was not modified
    assert tstates == 19
