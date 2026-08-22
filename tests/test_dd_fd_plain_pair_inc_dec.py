"""Red-first witnesses for prefix-ignored DD/FD INC/DEC BC/DE/SP."""

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
        pytest.fail(f"DD/FD-prefixed ordinary pair INC/DEC is not implemented: {exc}")


_CASES = (
    (0x03, "bc", 0xFFFF, 0x0000),
    (0x13, "de", 0xFFFF, 0x0000),
    (0x33, "sp", 0xFFFF, 0x0000),
    (0x0B, "bc", 0x0000, 0xFFFF),
    (0x1B, "de", 0x0000, 0xFFFF),
    (0x3B, "sp", 0x0000, 0xFFFF),
)


def _set_pair(cpu: MemoryCPU, pair: str, value: int) -> None:
    if pair == "bc":
        cpu.b, cpu.c = value >> 8, value & 0xFF
    elif pair == "de":
        cpu.d, cpu.e = value >> 8, value & 0xFF
    else:
        cpu.sp = value


def _get_pair(cpu: MemoryCPU, pair: str) -> int:
    if pair == "bc":
        return (cpu.b << 8) | cpu.c
    if pair == "de":
        return (cpu.d << 8) | cpu.e
    return cpu.sp


@pytest.mark.parametrize("prefix", (0xDD, 0xFD), ids=("dd", "fd"))
@pytest.mark.parametrize(("opcode", "pair", "initial", "expected"), _CASES)
def test_prefixed_plain_pair_inc_dec_ignores_index_prefix(
    prefix: int, opcode: int, pair: str, initial: int, expected: int
) -> None:
    """DD/FD INC/DEC BC/DE/SP retains IX/IY and adds the prefix fetch cost."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix = 0x1234
    cpu.iy = 0x5678
    _set_pair(cpu, pair, initial)
    cpu.r = 0x3E
    cpu.f.byte = 0xA5
    cpu.q = 0xA5
    cpu.wz = 0xBEEF

    tstates = _run(cpu, bytes([prefix, opcode]))

    assert _get_pair(cpu, pair) == expected
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert int(cpu.f) == 0xA5
    assert cpu.q == 0
    assert cpu.pc == 0x2002
    assert cpu.r == 0x40
    assert cpu.wz == 0xBEEF
    assert tstates == 10
