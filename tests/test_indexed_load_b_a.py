"""Red-first regression coverage for the DD/FD indexed LD B/A,(IX/IY+d) forms.

audit-indexed-load-seam diagnosed the smallest indexed memory load family as
exactly four opcode forms::

    DD 46 d  LD B,(IX+d)
    DD 7E d  LD A,(IX+d)
    FD 46 d  LD B,(IY+d)
    FD 7E d  LD A,(IY+d)

That is the exact four-opcode family this module covers, and nothing else.
Each test is a direct deterministic unit test: it places the prefix, opcode
and one signed displacement byte in RAM, seeds the index register and the
addressed memory byte, executes exactly one instruction, and asserts the
destination B or A receives that byte, the index register is unchanged and
the PC advances by 3 (the documented 19 T-states of LD r,(IX/IY+d) are
asserted too).  No parametrization, no vector-file plumbing -- four
standalone test functions, one per opcode form.

Why this file is red by design: the CPU core (src/z80/cpu.py) dispatches the
DD/FD index-prefix family through ``_execute_index``, but sub-opcodes 0x46
and 0x7E are not handled there yet, so all four raise
``NotImplementedError``.  Every unit test below therefore fails today,
because the family is unimplemented -- that is the regression this file
pins.  When the indexed load forms get implemented, these same tests flip
green only if the destination register, the unchanged index register and the
PC advance match the documented semantics exactly.
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
    the DD/FD indexed LD B/A,(IX/IY+d) forms have no handler in
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
            f"DD/FD indexed LD B/A,(IX/IY+d) is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_dd_46_ld_b_mem_at_ix_plus_d() -> None:
    """DD 46 d LD B,(IX+d): B <- (IX+d), IX unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    displacement = 2  # signed +2
    target = (cpu.ix + displacement) & 0xFFFF
    cpu.write_byte(target, 0x5A)

    tstates = _run(cpu, bytes([0xDD, 0x46, displacement & 0xFF]))

    assert cpu.b == 0x5A  # destination B receives the effective-address byte
    assert cpu.ix == 0x4000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19


def test_dd_7e_ld_a_mem_at_ix_minus_d() -> None:
    """DD 7E d LD A,(IX+d): A <- (IX-d), IX unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    displacement = -2  # signed -2 -> 0xFE in RAM
    target = (cpu.ix + displacement) & 0xFFFF
    cpu.write_byte(target, 0xA3)

    tstates = _run(cpu, bytes([0xDD, 0x7E, displacement & 0xFF]))

    assert cpu.a == 0xA3  # destination A receives the effective-address byte
    assert cpu.ix == 0x4000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19


def test_fd_46_ld_b_mem_at_iy_plus_d() -> None:
    """FD 46 d LD B,(IY+d): B <- (IY+d), IY unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    displacement = 3  # signed +3
    target = (cpu.iy + displacement) & 0xFFFF
    cpu.write_byte(target, 0x7C)

    tstates = _run(cpu, bytes([0xFD, 0x46, displacement & 0xFF]))

    assert cpu.b == 0x7C  # destination B receives the effective-address byte
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19


def test_fd_7e_ld_a_mem_at_iy_minus_d() -> None:
    """FD 7E d LD A,(IY+d): A <- (IY-d), IY unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    displacement = -4  # signed -4 -> 0xFC in RAM
    target = (cpu.iy + displacement) & 0xFFFF
    cpu.write_byte(target, 0xE1)

    tstates = _run(cpu, bytes([0xFD, 0x7E, displacement & 0xFF]))

    assert cpu.a == 0xE1  # destination A receives the effective-address byte
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19
