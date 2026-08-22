"""Red-first witnesses for prefix-ignored DD/FD conditional returns."""

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
        pytest.fail(f"DD/FD-prefixed conditional return is not implemented: {exc}")


# opcode, initial F when condition is true, initial F when condition is false
_CASES = (
    (0xC0, 0x00, 0x40),  # RET NZ
    (0xC8, 0x40, 0x00),  # RET Z
    (0xD0, 0x00, 0x01),  # RET NC
    (0xD8, 0x01, 0x00),  # RET C
    (0xE0, 0x00, 0x04),  # RET PO
    (0xE8, 0x04, 0x00),  # RET PE
    (0xF0, 0x00, 0x80),  # RET P
    (0xF8, 0x80, 0x00),  # RET M
)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "taken_flags", "untaken_flags"), _CASES)
@pytest.mark.parametrize("taken", (False, True), ids=("untaken", "taken"))
def test_prefixed_conditional_return_ignores_index_prefix(
    prefix: int, opcode: int, taken_flags: int, untaken_flags: int, taken: bool
) -> None:
    """DD/FD RET cc retains IX/IY and adds only the prefix fetch cost."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.sp = 0x4000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    cpu.r = 0x3E
    cpu.f.byte = taken_flags if taken else untaken_flags
    cpu.q = cpu.f.byte
    cpu.wz = 0xCAFE
    cpu.write_byte(0x4000, 0xEF)
    cpu.write_byte(0x4001, 0xBE)

    tstates = _run(cpu, bytes([prefix, opcode]))

    assert int(cpu.f) == (taken_flags if taken else untaken_flags)
    assert cpu.q == 0
    assert cpu.pc == (0xBEEF if taken else 0x2002)
    assert cpu.sp == (0x4002 if taken else 0x4000)
    assert cpu.wz == (0xBEEF if taken else 0xCAFE)
    assert cpu.r == 0x40
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == (15 if taken else 9)
