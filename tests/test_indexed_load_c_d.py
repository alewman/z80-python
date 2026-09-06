"""Red-first regression coverage for the DD/FD indexed LD C/D,(IX/IY+d) forms.

The indexed C/D load family is the exact four-opcode sibling of the B/A
indexed loads already covered by ``test_indexed_load_b_a.py``::

    DD 4E d  LD C,(IX+d)
    DD 56 d  LD D,(IX+d)
    FD 4E d  LD C,(IY+d)
    FD 56 d  LD D,(IY+d)

Each test is a direct deterministic unit test: it places the prefix, opcode
and one signed displacement byte in RAM, seeds the index register and the
addressed memory byte, executes exactly one instruction, and asserts the
destination C or D receives that byte, the index register is unchanged and
the PC advances by 3 (the documented 19 T-states of LD r,(IX/IY+d) are
asserted too).  No parametrization, no vector-file plumbing -- four
standalone test functions, one per opcode form.

Why this file is red by design: the CPU core (src/z80_python/) dispatches the
DD/FD index-prefix family through ``_execute_index``, which currently routes
only sub-opcodes 0x46 (B) and 0x7E (A) to ``_op_ld_r_index_mem``; sub-opcodes
0x4E (C) and 0x56 (D) are not handled there yet, so all four raise
``NotImplementedError``.  Every unit test below therefore fails today,
because the family is unimplemented -- that is the regression this file
pins.  When the indexed C/D load forms get implemented, these same tests flip
green only if the destination register, the unchanged index register and the
PC advance match the documented semantics exactly.
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
    the DD/FD indexed LD C/D,(IX/IY+d) forms have no handler in
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
            f"DD/FD indexed LD C/D,(IX/IY+d) is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_dd_4e_ld_c_mem_at_ix_plus_d() -> None:
    """DD 4E d LD C,(IX+d): C <- (IX+d), IX unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    displacement = 2  # signed +2
    target = (cpu.ix + displacement) & 0xFFFF
    cpu.write_byte(target, 0x6B)

    tstates = _run(cpu, bytes([0xDD, 0x4E, displacement & 0xFF]))

    assert cpu.c == 0x6B  # destination C receives the effective-address byte
    assert cpu.ix == 0x4000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19


def test_dd_56_ld_d_mem_at_ix_minus_d() -> None:
    """DD 56 d LD D,(IX+d): D <- (IX-d), IX unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    displacement = -2  # signed -2 -> 0xFE in RAM
    target = (cpu.ix + displacement) & 0xFFFF
    cpu.write_byte(target, 0x9D)

    tstates = _run(cpu, bytes([0xDD, 0x56, displacement & 0xFF]))

    assert cpu.d == 0x9D  # destination D receives the effective-address byte
    assert cpu.ix == 0x4000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19


def test_fd_4e_ld_c_mem_at_iy_plus_d() -> None:
    """FD 4E d LD C,(IY+d): C <- (IY+d), IY unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    displacement = 3  # signed +3
    target = (cpu.iy + displacement) & 0xFFFF
    cpu.write_byte(target, 0x3C)

    tstates = _run(cpu, bytes([0xFD, 0x4E, displacement & 0xFF]))

    assert cpu.c == 0x3C  # destination C receives the effective-address byte
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19


def test_fd_56_ld_d_mem_at_iy_minus_d() -> None:
    """FD 56 d LD D,(IY+d): D <- (IY-d), IY unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    displacement = -4  # signed -4 -> 0xFC in RAM
    target = (cpu.iy + displacement) & 0xFFFF
    cpu.write_byte(target, 0xD7)

    tstates = _run(cpu, bytes([0xFD, 0x56, displacement & 0xFF]))

    assert cpu.d == 0xD7  # destination D receives the effective-address byte
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19
