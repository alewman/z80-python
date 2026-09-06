"""Red-first witnesses for prefix-ignored DD/FD OR A,B/C/D/E forms."""

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
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(f"DD/FD-prefixed OR register form is not implemented: {exc}")


_CASES = (
    (0xB0, "b", 0x0F, 0xFF, 0xAC),
    (0xB1, "c", 0xF3, 0xF3, 0xA4),
    (0xB2, "d", 0xAA, 0xFA, 0xAC),
    (0xB3, "e", 0x55, 0xF5, 0xA4),
)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "register", "value", "result", "flags"), _CASES)
def test_prefixed_or_a_register_ignores_index_prefix(
    prefix: int, opcode: int, register: str, value: int, result: int, flags: int
) -> None:
    """DD/FD B0-B3 retain IX/IY and execute the ordinary 8-T-state OR form."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    cpu.a = 0xF0
    setattr(cpu, register, value)
    cpu.r = 0x3E
    cpu.f.byte = 0x01
    cpu.q = 0x01
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, opcode]))

    assert cpu.a == result
    assert int(cpu.f) == flags
    assert cpu.q == flags
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 8
