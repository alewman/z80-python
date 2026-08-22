"""Red-first witnesses for ordinary setup and HL absolute load forms."""

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
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte(cpu.pc + offset, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(f"base setup or HL load form is not implemented: {exc}")


@pytest.mark.parametrize(
    ("opcode", "pair"), ((0x01, "bc"), (0x11, "de"), (0x21, "hl"), (0x31, "sp"))
)
def test_immediate_word_loads(opcode: int, pair: str) -> None:
    """LD BC/DE/HL/SP,nn loads a little-endian word without changing flags."""
    cpu = MemoryCPU()
    cpu.pc, cpu.r, cpu.f.byte, cpu.q, cpu.wz = 0x2000, 0x3E, 0xC5, 0xC5, 0xBEEF

    tstates = _run(cpu, bytes([opcode, 0x34, 0x12]))

    value = {
        "bc": (cpu.b << 8) | cpu.c,
        "de": (cpu.d << 8) | cpu.e,
        "hl": (cpu.h << 8) | cpu.l,
        "sp": cpu.sp,
    }[pair]
    assert value == 0x1234
    assert int(cpu.f) == 0xC5
    assert cpu.q == 0
    assert cpu.pc == 0x2003
    assert cpu.r == 0x3F
    assert tstates == 10


@pytest.mark.parametrize("opcode", (0x22, 0x2A), ids=("store", "load"))
def test_absolute_hl_transfers(opcode: int) -> None:
    """LD (nn),HL and LD HL,(nn) transfer a word across an address wraparound."""
    cpu = MemoryCPU()
    cpu.pc, cpu.r, cpu.f.byte, cpu.q = 0x2000, 0x3E, 0xC5, 0xC5
    cpu.h, cpu.l = 0xA6, 0x5A
    cpu.write_byte(0xFFFF, 0x12)
    cpu.write_byte(0x0000, 0x34)

    tstates = _run(cpu, bytes([opcode, 0xFF, 0xFF]))

    assert (cpu.h, cpu.l) == ((0x34, 0x12) if opcode == 0x2A else (0xA6, 0x5A))
    assert cpu.read_byte(0xFFFF) == (0x12 if opcode == 0x2A else 0x5A)
    assert cpu.read_byte(0x0000) == (0x34 if opcode == 0x2A else 0xA6)
    assert int(cpu.f) == 0xC5
    assert cpu.q == 0
    assert cpu.pc == 0x2003
    assert cpu.r == 0x3F
    assert cpu.wz == 0x0000
    assert tstates == 16


def test_nop_exchange_af_and_djnz() -> None:
    """Ordinary setup/control forms preserve their independent state contracts."""
    cpu = MemoryCPU()
    cpu.pc, cpu.r, cpu.f.byte, cpu.q, cpu.wz = 0x2000, 0x3E, 0xC5, 0xC5, 0xBEEF
    assert _run(cpu, bytes([0x00])) == 4
    assert (cpu.pc, cpu.r, cpu.q, cpu.wz) == (0x2001, 0x3F, 0, 0xBEEF)

    cpu.pc, cpu.r, cpu.a, cpu.f.byte, cpu.af_ = 0x2000, 0x3E, 0xA6, 0x5A, 0x1234
    assert _run(cpu, bytes([0x08])) == 4
    assert (cpu.a, int(cpu.f), cpu.af_) == (0x12, 0x34, 0xA65A)

    cpu.pc, cpu.r, cpu.b, cpu.f.byte, cpu.q, cpu.wz = 0x2000, 0x3E, 2, 0xC5, 0xC5, 0xBEEF
    assert _run(cpu, bytes([0x10, 0xFD])) == 13
    assert (cpu.b, cpu.pc, cpu.r, int(cpu.f), cpu.q, cpu.wz) == (1, 0x1FFF, 0x3F, 0xC5, 0, 0x1FFF)
