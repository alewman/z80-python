"""Red-first regression coverage for the DD/FD indexed LD (IX/IY+d),B/A forms.

The indexed store family mirrors the four indexed load forms already covered
by ``test_indexed_load_b_a.py``; it is exactly four opcode forms::

    DD 70 d  LD (IX+d),B
    DD 77 d  LD (IX+d),A
    FD 70 d  LD (IY+d),B
    FD 77 d  LD (IY+d),A

Each test is a direct deterministic unit test: it places the prefix, opcode
and one signed displacement byte in RAM, seeds the index register, the source
register (B or A) and an addressed-memory sentinel, executes exactly one
instruction, and asserts the target memory byte equals the source register,
both the index and the source register are unchanged, and the PC advances by
3 (the documented 19 T-states of LD (IX/IY+d),r are asserted too).  No
parametrization, no vector-file plumbing -- four standalone test functions,
one per opcode form.

Why this file is red by design: the CPU core (src/z80_python/) dispatches the
DD/FD index-prefix family through ``_execute_index``, but sub-opcodes 0x70
and 0x77 are not handled there yet, so all four raise
``NotImplementedError``.  Every unit test below therefore fails today,
because the family is unimplemented -- that is the regression this file
pins.  When the indexed store forms get implemented, these same tests flip
green only if the destination memory byte, the unchanged index/source
registers and the PC advance match the documented semantics exactly.
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
    the DD/FD indexed LD (IX/IY+d),B/A forms have no handler in
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
            f"DD/FD indexed LD (IX/IY+d),B/A is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_dd_70_ld_mem_at_ix_plus_d_b() -> None:
    """DD 70 d LD (IX+d),B: (IX+d) <- B, B/IX unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    cpu.b = 0x5A
    displacement = 2  # signed +2
    target = (cpu.ix + displacement) & 0xFFFF
    cpu.write_byte(target, 0x00)  # addressed-memory sentinel

    tstates = _run(cpu, bytes([0xDD, 0x70, displacement & 0xFF]))

    assert cpu.memory[target] == 0x5A  # target memory receives B
    assert cpu.ix == 0x4000  # index register unchanged
    assert cpu.b == 0x5A  # source register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19


def test_dd_77_ld_mem_at_ix_minus_d_a() -> None:
    """DD 77 d LD (IX+d),A: (IX+d) <- A, A/IX unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    cpu.a = 0xA3
    displacement = -2  # signed -2 -> 0xFE in RAM
    target = (cpu.ix + displacement) & 0xFFFF
    cpu.write_byte(target, 0x00)  # addressed-memory sentinel

    tstates = _run(cpu, bytes([0xDD, 0x77, displacement & 0xFF]))

    assert cpu.memory[target] == 0xA3  # target memory receives A
    assert cpu.ix == 0x4000  # index register unchanged
    assert cpu.a == 0xA3  # source register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19


def test_fd_70_ld_mem_at_iy_plus_d_b() -> None:
    """FD 70 d LD (IY+d),B: (IY+d) <- B, B/IY unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    cpu.b = 0x7C
    displacement = 3  # signed +3
    target = (cpu.iy + displacement) & 0xFFFF
    cpu.write_byte(target, 0x00)  # addressed-memory sentinel

    tstates = _run(cpu, bytes([0xFD, 0x70, displacement & 0xFF]))

    assert cpu.memory[target] == 0x7C  # target memory receives B
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.b == 0x7C  # source register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19


def test_fd_77_ld_mem_at_iy_minus_d_a() -> None:
    """FD 77 d LD (IY+d),A: (IY+d) <- A, A/IY unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    cpu.a = 0xE1
    displacement = -4  # signed -4 -> 0xFC in RAM
    target = (cpu.iy + displacement) & 0xFFFF
    cpu.write_byte(target, 0x00)  # addressed-memory sentinel

    tstates = _run(cpu, bytes([0xFD, 0x77, displacement & 0xFF]))

    assert cpu.memory[target] == 0xE1  # target memory receives A
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.a == 0xE1  # source register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19
