"""Red-first witnesses for prefix-ignored DD/FD absolute jumps."""

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
        pytest.fail(f"DD/FD-prefixed absolute jump is not implemented: {exc}")


# opcode, initial F when condition is true, initial F when condition is false
_CONDITIONAL_CASES = (
    (0xC2, 0x00, 0x40),  # JP NZ,nn
    (0xCA, 0x40, 0x00),  # JP Z,nn
    (0xD2, 0x00, 0x01),  # JP NC,nn
    (0xDA, 0x01, 0x00),  # JP C,nn
    (0xE2, 0x00, 0x04),  # JP PO,nn
    (0xEA, 0x04, 0x00),  # JP PE,nn
    (0xF2, 0x00, 0x80),  # JP P,nn
    (0xFA, 0x80, 0x00),  # JP M,nn
)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "taken_flags", "untaken_flags"), _CONDITIONAL_CASES)
@pytest.mark.parametrize("taken", (False, True), ids=("untaken", "taken"))
def test_prefixed_conditional_jump_ignores_index_prefix(
    prefix: int, opcode: int, taken_flags: int, untaken_flags: int, taken: bool
) -> None:
    """DD/FD JP cc,nn keeps IX/IY and adds only the prefix fetch cost."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    cpu.r = 0x3E
    cpu.f.byte = taken_flags if taken else untaken_flags
    cpu.q = cpu.f.byte

    tstates = _run(cpu, bytes([prefix, opcode, 0xEF, 0xBE]))

    assert int(cpu.f) == (taken_flags if taken else untaken_flags)
    assert cpu.q == 0
    assert cpu.pc == (0xBEEF if taken else 0x2004)
    assert cpu.wz == 0xBEEF
    assert cpu.r == 0x40
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 14


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
def test_prefixed_unconditional_jump_ignores_index_prefix(prefix: int) -> None:
    """DD/FD C3 is the ordinary absolute jump, not an index-specific form."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    cpu.r = 0x3E
    cpu.f.byte = 0xA5
    cpu.q = 0xA5

    tstates = _run(cpu, bytes([prefix, 0xC3, 0xEF, 0xBE]))

    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0xBEEF
    assert cpu.wz == 0xBEEF
    assert cpu.r == 0x40
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 14
