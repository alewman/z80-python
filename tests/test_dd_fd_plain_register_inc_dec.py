"""Red-first witnesses for prefix-ignored DD/FD INC/DEC B/C/D/E/A."""

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
        pytest.fail(f"DD/FD-prefixed ordinary register INC/DEC is not implemented: {exc}")


_CASES = (
    (0x04, "b", 0x7F, 0x80, 0x95),
    (0x0C, "c", 0x7F, 0x80, 0x95),
    (0x14, "d", 0x7F, 0x80, 0x95),
    (0x1C, "e", 0x7F, 0x80, 0x95),
    (0x3C, "a", 0x7F, 0x80, 0x95),
    (0x05, "b", 0x00, 0xFF, 0xBB),
    (0x0D, "c", 0x00, 0xFF, 0xBB),
    (0x15, "d", 0x00, 0xFF, 0xBB),
    (0x1D, "e", 0x00, 0xFF, 0xBB),
    (0x3D, "a", 0x00, 0xFF, 0xBB),
)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "register", "initial", "expected", "flags"), _CASES)
def test_prefixed_plain_register_inc_dec_ignores_index_prefix(
    prefix: int, opcode: int, register: str, initial: int, expected: int, flags: int
) -> None:
    """DD/FD INC/DEC B/C/D/E/A retains IX/IY and adds the prefix fetch cost."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    setattr(cpu, register, initial)
    cpu.r = 0x3E
    cpu.f.byte = 0x01
    cpu.q = 0x01
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, opcode]))

    assert getattr(cpu, register) == expected
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert int(cpu.f) == flags
    assert cpu.q == flags
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert tstates == 8
