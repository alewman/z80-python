"""Red-first witness for the FD-prefixed ADC A,A (FD 8F) form.

The DD/FD index-prefix family dispatches through ``_execute_index``, which
handles the indexed load/ALU/POP/PUSH/JP sub-opcodes -- but sub-opcode 0x8F
(the ADC A,A form of the 0x80-0xBF ALU block) has no handler yet, so it
raises ``NotImplementedError``.  This file pins FD 8F with one direct
deterministic unit test: PC=0x2000, IY=0x5000, A=0xFF, R=0x3E, F=Q=0x01,
WZ=0xBEEF.

When FD 8F ADC A,A is implemented it must behave exactly like the plain 0x8F
ADC A,A (the prefix is ignored because neither operand is H/L or (HL)): with
the carry flag set, A receives 0xFF + 0xFF + 1 = 0xFF with S=1 Z=0 H=1 C=1
(F=0xB9), the index register stays untouched, F is written so Q latches the
new F value, WZ stays unchanged, PC advances to 0x2002 (prefix byte plus
opcode byte), R is bumped twice to 0x40, and the instruction consumes 8
T-states (4 for the ignored prefix fetch plus 4 for the base ADC A,A).
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
    the FD-prefixed ADC A,A (FD 8F) has no handler in ``_execute_index`` yet,
    so the instruction fails until the CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            "FD-prefixed ADC A,A is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_fd_8f_prefixed_adc_a_a() -> None:
    """FD 8F ADC A,A: A=0xFF, F=Q=0xB9, IY/WZ unchanged, PC/R advance, 8 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    cpu.a = 0xFF
    cpu.r = 0x3E
    cpu.f.byte = 0x01  # F (and Q) start with the carry flag set
    cpu.q = 0x01
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([0xFD, 0x8F]))

    assert cpu.a == 0xFF  # 0xFF + 0xFF + 1 wraps to 0xFF (carry out)
    assert int(cpu.f) == 0xB9  # S=1 Z=0 Y=1 H=1 X=1 PV=0 N=0 C=1
    assert cpu.iy == 0x5000  # index register untouched
    assert cpu.pc == 0x2002  # prefix byte + opcode byte consumed
    assert cpu.r == 0x40  # refresh register bumped once per fetched byte
    assert cpu.q == 0xB9  # ADC writes F, so Q latches the new F value
    assert cpu.wz == 0xBEEF  # WZ (MEMPTR) untouched
    assert tstates == 8
