"""Red-first witness for the DD-prefixed ADC A,E (DD 8B) form.

The DD/FD index-prefix family dispatches through ``_execute_index``, which
handles the indexed load/ALU/POP/PUSH/JP sub-opcodes -- but sub-opcode 0x8B
(the ADC A,E form of the 0x80-0xBF ALU block) has no handler yet, so it
raises ``NotImplementedError``.  This file pins DD 8B with one direct
deterministic unit test: PC=0x2000, IX=0x4000, A=0xFF, E=0x01, R=0x3E,
F=Q=0x01 (carry in set), WZ=0xBEEF.

When DD 8B ADC A,E is implemented it must behave exactly like the plain 0x8B
ADC A,E (the prefix is ignored because neither operand is H/L or (HL)): A
receives 0xFF + 0x01 + carry 1 = 0x101, masked to 0x01, with S=0 Z=0 H=1 C=1
(F=0x11), E and the index register stay untouched, F is written so Q latches
the new F value, WZ stays unchanged, PC advances to 0x2002 (prefix byte plus
opcode byte), R is bumped twice to 0x40, and the instruction consumes 8
T-states (4 for the ignored prefix fetch plus 4 for the base ADC A,E).
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
    the DD-prefixed ADC A,E (DD 8B) has no handler in ``_execute_index`` yet,
    so the instruction fails until the CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            "DD-prefixed ADC A,E is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def test_dd_8b_prefixed_adc_a_e() -> None:
    """DD 8B ADC A,E: A=0x01, F=Q=0x11, E/IX/WZ unchanged, PC/R advance, 8 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x4000
    cpu.a = 0xFF
    cpu.e = 0x01
    cpu.r = 0x3E
    cpu.f.byte = 0x01  # F (and Q) start with carry in set
    cpu.q = 0x01
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([0xDD, 0x8B]))

    assert cpu.a == 0x01  # 0xFF + 0x01 + carry 1 = 0x101 -> 0x01
    assert int(cpu.f) == 0x11  # S=0 Z=0 Y=0 H=1 X=0 PV=0 N=0 C=1
    assert cpu.e == 0x01  # source E untouched
    assert cpu.ix == 0x4000  # index register untouched
    assert cpu.pc == 0x2002  # prefix byte + opcode byte consumed
    assert cpu.r == 0x40  # refresh register bumped once per fetched byte
    assert cpu.q == 0x11  # ADC writes F, so Q latches the new F value
    assert cpu.wz == 0xBEEF  # WZ (MEMPTR) untouched
    assert tstates == 8
