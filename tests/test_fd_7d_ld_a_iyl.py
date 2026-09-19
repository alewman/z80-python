"""Red-first witness for the FD-prefixed LD A,IYL (FD 7D) form.

The DD/FD index-prefix family dispatches through ``_execute_index``, which
handles the indexed load/ALU/POP/PUSH/JP sub-opcodes -- but sub-opcode 0x7D
(the LD A,IYL form: the L slot of the 0x40-0x7F block remapped by the FD
prefix to the low byte of IY) has no handler yet, so it raises
``NotImplementedError``.  This file pins FD 7D with one direct deterministic
unit test: PC=0x2000, IY=0x5A3C, H=0xA7, A=0x12, R=0x3E, F=Q=0x3C, WZ=0xBEEF.

When FD 7D LD A,IYL is implemented it must copy the low byte of IY into A
(0x3C), leave H and the index register untouched, leave F untouched (so Q is
cleared), keep WZ unchanged, advance PC to 0x2002 (prefix byte plus opcode
byte), bump R twice to 0x40, and consume 8 T-states (4 for the ignored
prefix fetch plus 4 for the base LD A,L).
"""

from __future__ import annotations

import pytest
from conftest import MemoryCPU


def _run(cpu: MemoryCPU, opcode_bytes: bytes) -> int:
    """Place ``opcode_bytes`` at ``pc``, execute, and return the T-state count.

    A ``NotImplementedError`` here is the whole point of the red regression:
    the FD-prefixed LD A,IYL (FD 7D) has no handler in ``_execute_index``
    yet, so the instruction fails until the CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            "FD-prefixed LD A,IYL is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_fd_7d_ld_a_iyl() -> None:
    """FD 7D LD A,IYL: A <- IYL, H/IY/F/WZ unchanged, PC=0x2002, R=0x40, Q=0, 8 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5A3C
    cpu.h = 0xA7
    cpu.a = 0x12
    cpu.r = 0x3E
    cpu.f.byte = 0x3C  # F (and Q) start at 0x3C
    cpu.q = 0x3C
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([0xFD, 0x7D]))

    assert cpu.a == 0x3C  # LD A,IYL copies the low byte of IY into A
    assert cpu.h == 0xA7  # H is untouched by the prefixed form
    assert cpu.iy == 0x5A3C  # index register untouched
    assert cpu.pc == 0x2002  # prefix byte + opcode byte consumed
    assert cpu.r == 0x40  # refresh register bumped once per fetched byte
    assert int(cpu.f) == 0x3C  # LD A,IYL leaves F untouched
    assert cpu.q == 0  # LD A,IYL does not write F, so Q is cleared
    assert cpu.wz == 0xBEEF  # WZ (MEMPTR) untouched
    assert tstates == 8
