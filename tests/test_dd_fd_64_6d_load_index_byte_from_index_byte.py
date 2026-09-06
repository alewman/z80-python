"""Red-first witnesses for DD/FD IXH/IXL and IYH/IYL self-transfers."""

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
        pytest.fail(f"DD/FD index-byte self-transfer is not implemented: {exc}")


_CASES = (
    (0x64, 0x0FF3),  # LD index-high,index-high
    (0x65, 0xF3F3),  # LD index-high,index-low
    (0x6C, 0x0F0F),  # LD index-low,index-high
    (0x6D, 0x0FF3),  # LD index-low,index-low
)


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "expected"), _CASES)
def test_prefixed_load_index_byte_from_index_byte(prefix: int, opcode: int, expected: int) -> None:
    """DD/FD 64-6D reads and writes only the selected IX/IY byte slots."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x0FF3
    cpu.iy = 0x0FF3
    cpu.r = 0x3E
    cpu.f.byte = 0xA5
    cpu.q = 0xA5
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, opcode]))

    assert cpu.ix == (expected if prefix == 0xDD else 0x0FF3)
    assert cpu.iy == (expected if prefix == 0xFD else 0x0FF3)
    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert tstates == 8
