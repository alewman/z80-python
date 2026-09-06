"""Red-first witness for the FD indexed LD (IY+d),H form.

The DD/FD index-prefix family dispatches through ``_execute_index``, which
routes the indexed store sub-opcodes 0x70 (B), 0x71 (C), 0x72 (D), 0x73 (E),
0x75 (L) and 0x77 (A) to ``_op_ld_index_mem_r`` -- but sub-opcode 0x74 (H)
has no handler yet, so it raises ``NotImplementedError``.  This file pins
FD 74 02 with one direct deterministic unit test: PC=0x2000, IY=0x5000,
H=0x3C, F=0x01, memory[0x5002]=0x00.

When LD (IY+d),H is implemented it must store H at the effective address,
leave H and IY untouched, leave F at 0x01 (LD never writes F, so Q is
cleared), advance PC to 0x2003, latch WZ to the effective address 0x5002,
and consume 19 T-states.
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
    the FD indexed LD (IY+d),H form (0x74) has no handler in ``_execute_index``
    yet, so the instruction fails until the CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            f"FD indexed LD (IY+d),H (0x74) is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_fd_74_ld_mem_at_iy_plus_2_h() -> None:
    """FD 74 02 LD (IY+2),H: (0x5002) <- 0x3C, H/IY/F/PC/WZ/Q/T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    cpu.h = 0x3C
    cpu.f.byte = 0x01  # only the C flag set
    cpu.write_byte(0x5002, 0x00)  # addressed-memory sentinel

    tstates = _run(cpu, bytes([0xFD, 0x74, 0x02]))

    assert cpu.memory[0x5002] == 0x3C  # target memory receives H
    assert cpu.h == 0x3C  # source register unchanged
    assert cpu.iy == 0x5000  # index register unchanged
    assert int(cpu.f) == 0x01  # flags untouched
    assert cpu.q == 0  # LD does not write F, so Q is cleared
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert cpu.wz == 0x5002  # WZ (MEMPTR) latches the effective address
    assert tstates == 19
