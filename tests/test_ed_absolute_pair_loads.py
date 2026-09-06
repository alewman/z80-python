"""Red-first witnesses for ED absolute register-pair load forms."""

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
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte(cpu.pc + offset, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(f"ED absolute pair load form is not implemented: {exc}")


@pytest.mark.parametrize(
    ("opcode", "pair"),
    ((0x43, "bc"), (0x53, "de"), (0x63, "hl"), (0x73, "sp")),
)
def test_ed_store_pair_at_absolute_address(opcode: int, pair: str) -> None:
    """LD (nn),rr stores little-endian words and preserves flags."""
    cpu = MemoryCPU()
    cpu.pc, cpu.r, cpu.f.byte, cpu.q = 0x2000, 0x3E, 0xC5, 0xC5
    cpu._write_pair((opcode >> 4) & 0x03, 0xA65A)

    assert _run(cpu, bytes([0xED, opcode, 0xFF, 0xFF])) == 20

    assert cpu.read_byte(0xFFFF) == 0x5A
    assert cpu.read_byte(0x0000) == 0xA6
    assert cpu._read_pair((opcode >> 4) & 0x03) == 0xA65A
    assert (cpu.pc, cpu.r, int(cpu.f), cpu.q, cpu.wz) == (0x2004, 0x40, 0xC5, 0, 0)



@pytest.mark.parametrize(
    ("opcode", "pair"),
    ((0x4B, "bc"), (0x5B, "de"), (0x6B, "hl"), (0x7B, "sp")),
)
def test_ed_load_pair_from_absolute_address(opcode: int, pair: str) -> None:
    """LD rr,(nn) reads little-endian words across an address wraparound."""
    cpu = MemoryCPU()
    cpu.pc, cpu.r, cpu.f.byte, cpu.q = 0x2000, 0x3E, 0xC5, 0xC5
    cpu.write_byte(0xFFFF, 0x5A)
    cpu.write_byte(0x0000, 0xA6)

    assert _run(cpu, bytes([0xED, opcode, 0xFF, 0xFF])) == 20

    assert cpu._read_pair((opcode >> 4) & 0x03) == 0xA65A
    assert (cpu.pc, cpu.r, int(cpu.f), cpu.q, cpu.wz) == (0x2004, 0x40, 0xC5, 0, 0)  # noqa: W292