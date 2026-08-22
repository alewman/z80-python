"""Red-first witness for the FD-prefixed SUB A,IYH (FD 94) form.

The DD/FD index-prefix family dispatches through ``_execute_index``, which
handles the indexed load/ALU/POP/PUSH/JP sub-opcodes -- but sub-opcode 0x94
(the SUB A,IYH form of the 0x80-0xBF ALU block) has no handler yet, so it
raises ``NotImplementedError``.  This file pins FD 94 with one direct
deterministic unit test: PC=0x2000, IY=0x0102, A=0x00, R=0x3E, F=Q=0x00,
WZ=0xBEEF.

When FD 94 SUB A,IYH is implemented it must subtract the high byte of IY
(0x01) from A: A receives 0x00 - 0x01 = 0xFF with S=1 Y=1 H=1 X=1 N=1 C=1
(F=0xBB), the complete IY register stays untouched, F is written so Q latches
the new F value, WZ stays unchanged, PC advances to 0x2002 (prefix byte plus
opcode byte), R is bumped twice to 0x40, and the instruction consumes 8
T-states (4 for the prefix fetch plus 4 for the base SUB A,IYH).
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
    the FD-prefixed SUB A,IYH (FD 94) has no handler in ``_execute_index``
    yet, so the instruction fails until the CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            "FD-prefixed SUB A,IYH is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_fd_94_prefixed_sub_a_iyh() -> None:
    """FD 94 SUB A,IYH: A=0xFF, F=Q=0xBB, IY/WZ unchanged, PC/R advance, 8 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x0102  # IYH=0x01 is the source; IYL=0x02 must be ignored
    cpu.a = 0x00
    cpu.r = 0x3E
    cpu.f.byte = 0x00  # F (and Q) start at 0x00
    cpu.q = 0x00
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([0xFD, 0x94]))

    assert cpu.a == 0xFF  # 0x00 - 0x01 wraps to 0xFF
    assert int(cpu.f) == 0xBB  # S=1 Y=1 H=1 X=1 N=1 C=1
    assert cpu.iy == 0x0102  # complete index register untouched
    assert cpu.pc == 0x2002  # prefix byte + opcode byte consumed
    assert cpu.r == 0x40  # refresh register bumped once per fetched byte
    assert cpu.q == 0xBB  # SUB writes F, so Q latches the new F value
    assert cpu.wz == 0xBEEF  # WZ (MEMPTR) untouched
    assert tstates == 8
