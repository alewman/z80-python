"""Red-first witness for the DD-prefixed SBC A,IXH (DD 9C) form.

The DD/FD index-prefix family dispatches through ``_execute_index``, which
handles the indexed load/ALU/POP/PUSH/JP sub-opcodes -- but sub-opcode 0x9C
(the SBC A,IXH form: the H slot of the 0x80-0xBF ALU block remapped by the
DD prefix to the high byte of IX) has no handler yet, so it raises
``NotImplementedError``.  This file pins DD 9C with one direct deterministic
unit test: PC=0x2000, IX=0x0102 (IXH=0x01 is the source, IXL=0x02 must be
ignored), A=0x00, R=0x3E, F=Q=0x01 (carry in set), WZ=0xBEEF.

When DD 9C SBC A,IXH is implemented it must behave exactly like SBC A,H with
the H slot replaced by the high byte of IX: A receives 0x00 - 0x01 - carry 1
= 0xFE with S=1 Y=1 H=1 X=1 N=1 C=1 (F=0xBB), the full IX register stays
untouched, F is written so Q latches the new F value, WZ stays unchanged, PC
advances to 0x2002 (prefix byte plus opcode byte), R is bumped twice to 0x40,
and the instruction consumes 8 T-states (4 for the prefix fetch plus 4 for
the base SBC A,H).
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
    the DD-prefixed SBC A,IXH (DD 9C) has no handler in ``_execute_index``
    yet, so the instruction fails until the CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            "DD-prefixed SBC A,IXH is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_dd_9c_prefixed_sbc_a_ixh() -> None:
    """DD 9C SBC A,IXH: A=0xFE, F=Q=0xBB, IX/WZ unchanged, PC/R advance, 8 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x0102  # IXH=0x01 is the source; IXL=0x02 must be ignored
    cpu.a = 0x00
    cpu.r = 0x3E
    cpu.f.byte = 0x01  # F (and Q) start with carry in set
    cpu.q = 0x01
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([0xDD, 0x9C]))

    assert cpu.a == 0xFE  # 0x00 - 0x01 - carry 1 = -2 -> 0xFE
    assert int(cpu.f) == 0xBB  # S=1 Y=1 H=1 X=1 N=1 C=1
    assert cpu.ix == 0x0102  # complete index register untouched
    assert cpu.pc == 0x2002  # prefix byte + opcode byte consumed
    assert cpu.r == 0x40  # refresh register bumped once per fetched byte
    assert cpu.q == 0xBB  # SBC writes F, so Q latches the new F value
    assert cpu.wz == 0xBEEF  # WZ (MEMPTR) untouched
    assert tstates == 8
