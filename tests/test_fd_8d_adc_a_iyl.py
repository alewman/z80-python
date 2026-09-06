"""Red-first witness for the FD-prefixed ADC A,IYL (FD 8D) form.

The DD/FD index-prefix family dispatches through ``_execute_index``, which
handles the indexed load/ALU/POP/PUSH/JP sub-opcodes -- but sub-opcode 0x8D
(the ADC A,IYL form: the L slot of the 0x80-0xBF ALU block remapped by the
FD prefix to the low byte of IY) has no handler yet, so it raises
``NotImplementedError``.  This file pins FD 8D with one direct deterministic
unit test: PC=0x2000, IY=0x0001, A=0xFF, R=0x3E, F=Q=0x01 (carry set),
WZ=0xBEEF.

When FD 8D ADC A,IYL is implemented it must behave exactly like ADC A,L with
the L slot replaced by the low byte of IY: A receives 0xFF + 0x01 + C(1) =
0x01 with S=0 Z=0 H=1 C=1 (F=0x11), the full IY register stays untouched, F
is written so Q latches the new F value, WZ stays unchanged, PC advances to
0x2002 (prefix byte plus opcode byte), R is bumped twice to 0x40, and the
instruction consumes 8 T-states (4 for the ignored prefix fetch plus 4 for
the base ADC A,L).
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
    the FD-prefixed ADC A,IYL (FD 8D) has no handler in ``_execute_index``
    yet, so the instruction fails until the CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            "FD-prefixed ADC A,IYL is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_fd_8d_adc_a_iyl() -> None:
    """FD 8D ADC A,IYL: A=0x01, F=Q=0x11, IY/WZ unchanged, PC=0x2002, R=0x40, 8 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x0001  # IYH = 0x00, IYL = 0x01
    cpu.a = 0xFF
    cpu.r = 0x3E
    cpu.f.byte = 0x01  # F (and Q) start with the carry flag set
    cpu.q = 0x01
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([0xFD, 0x8D]))

    assert cpu.a == 0x01  # 0xFF + IYL (0x01) + C (0x01) wraps to 0x01
    assert int(cpu.f) == 0x11  # S=0 Z=0 Y=0 H=1 X=0 PV=0 N=0 C=1
    assert cpu.iy == 0x0001  # full index register untouched
    assert cpu.pc == 0x2002  # prefix byte + opcode byte consumed
    assert cpu.r == 0x40  # refresh register bumped once per fetched byte
    assert cpu.q == 0x11  # ADC writes F, so Q latches the new F value
    assert cpu.wz == 0xBEEF  # WZ (MEMPTR) untouched
    assert tstates == 8
