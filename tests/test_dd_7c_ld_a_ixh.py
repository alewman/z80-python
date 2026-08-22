"""Red-first witness for the DD-prefixed LD A,IXH (DD 7C) form.

The DD/FD index-prefix family dispatches through ``_execute_index``, which
handles the indexed load/ALU/POP/PUSH/JP sub-opcodes -- but sub-opcode 0x7C
(the LD A,IXH form: the H slot of the 0x40-0x7F block remapped by the DD
prefix to the high byte of IX) has no handler yet, so it raises
``NotImplementedError``.  This file pins DD 7C with one direct deterministic
unit test: PC=0x2000, IX=0xA5C3, H=0x34, A=0x12, R=0x3E, F=Q=0xA5, WZ=0xBEEF.

When DD 7C LD A,IXH is implemented it must copy the high byte of IX into A
(0xA5), leave H and the index register untouched, leave F untouched (so Q is
cleared), keep WZ unchanged, advance PC to 0x2002 (prefix byte plus opcode
byte), bump R twice to 0x40, and consume 8 T-states (4 for the ignored
prefix fetch plus 4 for the base LD A,H).
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
    the DD-prefixed LD A,IXH (DD 7C) has no handler in ``_execute_index``
    yet, so the instruction fails until the CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            "DD-prefixed LD A,IXH is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_dd_7c_ld_a_ixh() -> None:
    """DD 7C LD A,IXH: A <- IXH, H/IX/F/WZ unchanged, PC=0x2002, R=0x40, Q=0, 8 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0xA5C3
    cpu.h = 0x34
    cpu.a = 0x12
    cpu.r = 0x3E
    cpu.f.byte = 0xA5  # F (and Q) start at 0xA5
    cpu.q = 0xA5
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([0xDD, 0x7C]))

    assert cpu.a == 0xA5  # LD A,IXH copies the high byte of IX into A
    assert cpu.h == 0x34  # H is untouched by the prefixed form
    assert cpu.ix == 0xA5C3  # index register untouched
    assert cpu.pc == 0x2002  # prefix byte + opcode byte consumed
    assert cpu.r == 0x40  # refresh register bumped once per fetched byte
    assert int(cpu.f) == 0xA5  # LD A,IXH leaves F untouched
    assert cpu.q == 0  # LD A,IXH does not write F, so Q is cleared
    assert cpu.wz == 0xBEEF  # WZ (MEMPTR) untouched
    assert tstates == 8
