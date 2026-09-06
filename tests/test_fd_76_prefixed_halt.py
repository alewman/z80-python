"""Red-first witness for the FD-prefixed HALT (FD 76) form.

The DD/FD index-prefix family dispatches through ``_execute_index``, which
handles the indexed load/ALU/POP/PUSH/JP sub-opcodes -- but sub-opcode 0x76
(HALT) has no handler yet, so it raises ``NotImplementedError``.  This file
pins FD 76 with one direct deterministic unit test: PC=0x2000, IY=0x5000,
R=0x3E, F=Q=0x3C, WZ=0xBEEF.

When FD 76 HALT is implemented it must behave exactly like the plain 0x76
HALT: set the ``halted`` state flag, leave F and every register untouched
(so Q is cleared), keep WZ unchanged, advance PC to 0x2002 (prefix byte plus
HALT byte), bump R twice to 0x40, and consume 8 T-states.
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
    the FD-prefixed HALT (FD 76) has no handler in ``_execute_index`` yet, so
    the instruction fails until the CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            f"FD-prefixed HALT is not implemented (opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_fd_76_prefixed_halt() -> None:
    """FD 76 HALT: halted=True, PC=0x2002, R=0x40, F/WZ/IY unchanged, Q=0, 8 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    cpu.r = 0x3E
    cpu.f.byte = 0x3C  # F (and Q) start at 0x3C
    cpu.q = 0x3C
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([0xFD, 0x76]))

    assert cpu.halted is True  # HALT sets the halted state flag
    assert cpu.pc == 0x2002  # prefix byte + HALT byte consumed
    assert cpu.r == 0x40  # refresh register bumped once per fetched byte
    assert int(cpu.f) == 0x3C  # HALT leaves F untouched
    assert cpu.q == 0  # HALT does not write F, so Q is cleared
    assert cpu.wz == 0xBEEF  # WZ (MEMPTR) untouched
    assert cpu.iy == 0x5000  # index register untouched
    assert tstates == 8
