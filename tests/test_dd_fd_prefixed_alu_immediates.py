"""Red-first witnesses for prefix-ignored DD/FD immediate ALU forms."""

from __future__ import annotations

import pytest
from conftest import MemoryCPU


def _run(cpu: MemoryCPU, opcode_bytes: bytes) -> int:
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(f"DD/FD-prefixed immediate ALU form is not implemented: {exc}")


# opcode, initial carry, result A, F after operation
_CASES = (
    (0xC6, 0, 0xFF, 0xA8),  # ADD A,0x0F
    (0xCE, 1, 0x00, 0x51),  # ADC A,0x0F
    (0xD6, 0, 0xE1, 0xB2),  # SUB 0x0F
    (0xDE, 1, 0xE0, 0xB2),  # SBC A,0x0F
    (0xE6, 0, 0x00, 0x54),  # AND 0x0F
    (0xEE, 0, 0xFF, 0xAC),  # XOR 0x0F
    (0xF6, 0, 0xFF, 0xAC),  # OR 0x0F
    (0xFE, 0, 0xF0, 0x9A),  # CP 0x0F
)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "carry", "result", "flags"), _CASES)
def test_prefixed_alu_immediate_ignores_index_prefix(
    prefix: int, opcode: int, carry: int, result: int, flags: int
) -> None:
    """DD/FD immediate ALU forms retain IX/IY and execute in 11 T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    cpu.a = 0xF0
    cpu.r = 0x3E
    cpu.f.byte = carry
    cpu.q = carry
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, opcode, 0x0F]))

    assert cpu.a == result
    assert int(cpu.f) == flags
    assert cpu.q == flags
    assert cpu.pc == 0x2003
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 11
