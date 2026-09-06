"""Red-first witness for the DD-prefixed SBC A,A (DD 9F) form."""

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
    """Place the instruction at PC and execute the intended DD 9F form."""
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(f"DD-prefixed SBC A,A is not implemented: {exc}")


def test_dd_9f_prefixed_sbc_a_a() -> None:
    """DD 9F ignores DD: SBC A,A preserves IX/IY and costs 8 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    cpu.a = 0x00
    cpu.r = 0x3E
    cpu.f.byte = 0x01
    cpu.q = 0x01
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([0xDD, 0x9F]))

    assert cpu.a == 0xFF
    assert int(cpu.f) == 0xBB
    assert cpu.q == 0xBB
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 8
