"""Red-first witnesses for DD/FD INC/DEC index-high/index-low."""

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
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(f"DD/FD INC/DEC index byte is not implemented: {exc}")


# opcode, initial index value, final index value, expected flags
_CASES = (
    (0x24, 0x7FF3, 0x80F3, 0x95),  # INC index-high: overflow
    (0x25, 0x00F3, 0xFFF3, 0xBB),  # DEC index-high: underflow
    (0x2C, 0x0F7F, 0x0F80, 0x95),  # INC index-low: overflow
    (0x2D, 0x0F00, 0x0FFF, 0xBB),  # DEC index-low: underflow
)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "initial", "expected", "flags"), _CASES)
def test_prefixed_inc_dec_index_byte(
    prefix: int, opcode: int, initial: int, expected: int, flags: int
) -> None:
    """DD/FD 24-2D changes only the selected index byte and preserves carry."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    if prefix == 0xDD:
        cpu.ix = initial
    else:
        cpu.iy = initial
    cpu.r = 0x3E
    cpu.f.byte = 0x01
    cpu.q = 0x01
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, opcode]))

    assert cpu.ix == (expected if prefix == 0xDD else 0x1234)
    assert cpu.iy == (expected if prefix == 0xFD else 0x5678)
    assert int(cpu.f) == flags
    assert cpu.q == flags
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert tstates == 8
