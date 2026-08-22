"""Red-first regression coverage for the DD/FD indexed memory INC/DEC forms.

audit-indexed-inc-dec-seam diagnosed the smallest indexed memory INC/DEC
family as exactly four opcode forms::

    DD 34 d  INC (IX+d)
    DD 35 d  DEC (IX+d)
    FD 34 d  INC (IY+d)
    FD 35 d  DEC (IY+d)

That is the exact four-opcode family this module covers, and nothing else.
Each test is a direct deterministic unit test: it places the prefix, opcode
and one signed displacement byte in RAM, seeds the index register and the
addressed memory byte, executes exactly one instruction, and asserts the
resulting target memory value, the unchanged index register and the PC
advance.  No parametrization, no vector-file plumbing -- four standalone
test functions, one per opcode form.

Why this file is red by design: the CPU core (src/z80/cpu.py) dispatches the
DD/FD index-prefix family through ``_execute_index``, but sub-opcodes 0x34
and 0x35 are not handled there yet, so both raise ``NotImplementedError``.
Every unit test below therefore fails today, because the family is
unimplemented -- that is the regression this file pins.  When the indexed
INC/DEC forms get implemented, these same tests flip green only if the
target memory byte, the index register and the PC advance match the
documented semantics exactly.
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
    the DD/FD indexed INC/DEC forms have no handler in ``_execute_index``
    yet, so every instruction in this module fails until the CPU implements
    it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            f"DD/FD indexed INC/DEC is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_dd_34_inc_mem_at_ix_plus_d() -> None:
    """DD 34 d INC (IX+d): target byte +1, IX unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    displacement = 2  # signed +2
    target = (cpu.ix + displacement) & 0xFFFF
    cpu.write_byte(target, 0x05)

    tstates = _run(cpu, bytes([0xDD, 0x34, displacement & 0xFF]))

    assert cpu.read_byte(target) == 0x06  # 0x05 + 1
    assert cpu.ix == 0x4000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 23


def test_dd_35_dec_mem_at_ix_minus_d() -> None:
    """DD 35 d DEC (IX+d): target byte -1, IX unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    displacement = -2  # signed -2 -> 0xFE in RAM
    target = (cpu.ix + displacement) & 0xFFFF
    cpu.write_byte(target, 0x05)

    tstates = _run(cpu, bytes([0xDD, 0x35, displacement & 0xFF]))

    assert cpu.read_byte(target) == 0x04  # 0x05 - 1
    assert cpu.ix == 0x4000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 23


def test_fd_34_inc_mem_at_iy_plus_d() -> None:
    """FD 34 d INC (IY+d): target byte +1 (overflow 0x7F->0x80), IY unchanged."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x4000
    displacement = 3  # signed +3
    target = (cpu.iy + displacement) & 0xFFFF
    cpu.write_byte(target, 0x7F)

    tstates = _run(cpu, bytes([0xFD, 0x34, displacement & 0xFF]))

    assert cpu.read_byte(target) == 0x80  # 0x7F + 1
    assert cpu.iy == 0x4000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 23


def test_fd_35_dec_mem_at_iy_minus_d() -> None:
    """FD 35 d DEC (IY+d): target byte -1 (wrap 0x00->0xFF), IY unchanged."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x4000
    displacement = -4  # signed -4 -> 0xFC in RAM
    target = (cpu.iy + displacement) & 0xFFFF
    cpu.write_byte(target, 0x00)

    tstates = _run(cpu, bytes([0xFD, 0x35, displacement & 0xFF]))

    assert cpu.read_byte(target) == 0xFF  # 0x00 - 1, wrapping
    assert cpu.iy == 0x4000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 23
