"""Red-first witness for the DD-prefixed HALT (DD 76) form.

The DD/FD index-prefix family dispatches through ``_execute_index``, which
handles the indexed load/ALU/POP/PUSH/JP sub-opcodes -- but sub-opcode 0x76
(HALT) has no handler yet, so it raises ``NotImplementedError``.  This file
pins DD 76 with one direct deterministic unit test: PC=0x2000, IX=0x4000,
R=0x3E, F=Q=0xA5, WZ=0xBEEF.

When DD 76 HALT is implemented it must behave exactly like the plain 0x76
HALT: set the ``halted`` state flag, leave F and every register untouched
(so Q is cleared), keep WZ unchanged, advance PC to 0x2002 (prefix byte plus
HALT byte), bump R twice to 0x40, and consume 8 T-states.
"""

from __future__ import annotations

import pytest
from conftest import MemoryCPU


def _run(cpu: MemoryCPU, opcode_bytes: bytes) -> int:
    """Place ``opcode_bytes`` at ``pc``, execute, and return the T-state count.

    A ``NotImplementedError`` here is the whole point of the red regression:
    the DD-prefixed HALT (DD 76) has no handler in ``_execute_index`` yet, so
    the instruction fails until the CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            f"DD-prefixed HALT is not implemented (opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_dd_76_prefixed_halt() -> None:
    """DD 76 HALT: halted=True, PC=0x2002, R=0x40, F/WZ/IX unchanged, Q=0, 8 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    cpu.r = 0x3E
    cpu.f.byte = 0xA5  # F (and Q) start at 0xA5
    cpu.q = 0xA5
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([0xDD, 0x76]))

    assert cpu.halted is True  # HALT sets the halted state flag
    assert cpu.pc == 0x2002  # prefix byte + HALT byte consumed
    assert cpu.r == 0x40  # refresh register bumped once per fetched byte
    assert int(cpu.f) == 0xA5  # HALT leaves F untouched
    assert cpu.q == 0  # HALT does not write F, so Q is cleared
    assert cpu.wz == 0xBEEF  # WZ (MEMPTR) untouched
    assert cpu.ix == 0x4000  # index register untouched
    assert tstates == 8
