"""Red-first regression coverage for the DD/FD indexed LD L,(IX/IY+d) forms.

The indexed L memory family is the exact four-opcode sibling of the B/A, C/D
and E/H indexed loads/stores already covered by the other
``test_indexed_load_*`` / ``test_indexed_store_*`` modules::

    DD 6E d  LD L,(IX+d)
    FD 6E d  LD L,(IY+d)
    DD 75 d  LD (IX+d),L
    FD 75 d  LD (IY+d),L

Each test is a direct deterministic unit test: it places the prefix, opcode
and one signed displacement byte in RAM, seeds the index register, the
addressed memory byte and (for the store forms) the source L register, executes
exactly one instruction, and asserts the load/store semantics -- the
destination L receives the effective-address byte (loads), the target memory
byte receives L (stores), the index register is unchanged, and the PC advances
by 3 (the documented 19 T-states of LD r,(IX/IY+d) / LD (IX/IY+d),r are
asserted too).  No parametrization, no vector-file plumbing -- four standalone
test functions, one per opcode form.

Why this file is red by design: the CPU core (src/z80/cpu.py) dispatches the
DD/FD index-prefix family through ``_execute_index``, which routes only
sub-opcodes 0x46/0x4E/0x56/0x5E/0x66/0x7E to ``_op_ld_r_index_mem`` and only
0x70/0x77 to ``_op_ld_index_mem_r``; sub-opcodes 0x6E (L load) and 0x75
(L store) are not handled there yet, so all four raise ``NotImplementedError``.
Every unit test below therefore fails today, because the family is
unimplemented -- that is the regression this file pins.  When the indexed L
memory forms get implemented, these same tests flip green only if the
destination/source L register, the unchanged index register and the PC advance
match the documented semantics exactly.
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
    the DD/FD indexed LD L,(IX/IY+d) / LD (IX/IY+d),L forms have no handler in
    ``_execute_index`` yet, so every instruction in this module fails until the
    CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            f"DD/FD indexed LD L,(IX/IY+d) / LD (IX/IY+d),L is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_dd_6e_ld_l_mem_at_ix_plus_d() -> None:
    """DD 6E d LD L,(IX+d): L <- (IX+d), IX unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    cpu.l = 0x00  # distinct pre-load value so the overwrite is observable
    displacement = 2  # signed +2
    target = (cpu.ix + displacement) & 0xFFFF
    cpu.write_byte(target, 0x4B)

    tstates = _run(cpu, bytes([0xDD, 0x6E, displacement & 0xFF]))

    assert cpu.l == 0x4B  # destination L receives the effective-address byte
    assert cpu.ix == 0x4000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19


def test_dd_75_ld_mem_at_ix_minus_d_l() -> None:
    """DD 75 d LD (IX+d),L: (IX+d) <- L, L/IX unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    cpu.l = 0x5A
    displacement = -2  # signed -2 -> 0xFE in RAM
    target = (cpu.ix + displacement) & 0xFFFF
    cpu.write_byte(target, 0x00)  # addressed-memory sentinel, distinct from L

    tstates = _run(cpu, bytes([0xDD, 0x75, displacement & 0xFF]))

    assert cpu.memory[target] == 0x5A  # target memory receives L
    assert cpu.l == 0x5A  # source register unchanged
    assert cpu.ix == 0x4000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19


def test_fd_6e_ld_l_mem_at_iy_minus_d() -> None:
    """FD 6E d LD L,(IY+d): L <- (IY-d), IY unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    cpu.l = 0x00  # distinct pre-load value so the overwrite is observable
    displacement = -3  # signed -3 -> 0xFD in RAM
    target = (cpu.iy + displacement) & 0xFFFF
    cpu.write_byte(target, 0x8C)

    tstates = _run(cpu, bytes([0xFD, 0x6E, displacement & 0xFF]))

    assert cpu.l == 0x8C  # destination L receives the effective-address byte
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19


def test_fd_75_ld_mem_at_iy_plus_d_l() -> None:
    """FD 75 d LD (IY+d),L: (IY+d) <- L, L/IY unchanged, PC += 3."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    cpu.l = 0xE1
    displacement = 3  # signed +3
    target = (cpu.iy + displacement) & 0xFFFF
    cpu.write_byte(target, 0x00)  # addressed-memory sentinel, distinct from L

    tstates = _run(cpu, bytes([0xFD, 0x75, displacement & 0xFF]))

    assert cpu.memory[target] == 0xE1  # target memory receives L
    assert cpu.l == 0xE1  # source register unchanged
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert tstates == 19
