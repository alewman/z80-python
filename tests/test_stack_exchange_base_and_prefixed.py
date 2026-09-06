"""Red-first witnesses for ordinary and prefix-ignored stack/exchange forms."""

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
        pytest.fail(f"stack or exchange form is not implemented: {exc}")


@pytest.mark.parametrize(
    ("prefix", "opcode", "pair"),
    (
        (None, 0xC1, "bc"),
        (None, 0xD1, "de"),
        (None, 0xE1, "hl"),
        (None, 0xF1, "af"),
        (0xDD, 0xC1, "bc"),
        (0xFD, 0xC1, "bc"),
        (0xDD, 0xD1, "de"),
        (0xFD, 0xD1, "de"),
        (0xDD, 0xF1, "af"),
        (0xFD, 0xF1, "af"),
    ),
)
def test_pop_pairs_and_af(prefix: int | None, opcode: int, pair: str) -> None:
    """Base POP and DD/FD prefix-ignored POP forms preserve index registers."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.sp = 0x4000
    cpu.ix, cpu.iy = 0x1234, 0x5678
    cpu.r = 0x3E
    cpu.q = 0xA5
    cpu.write_byte(cpu.sp, 0x12)
    cpu.write_byte(cpu.sp + 1, 0x34)

    tstates = _run(cpu, bytes(([prefix] if prefix is not None else []) + [opcode]))

    if pair == "bc":
        assert (cpu.b, cpu.c) == (0x34, 0x12)
    elif pair == "de":
        assert (cpu.d, cpu.e) == (0x34, 0x12)
    elif pair == "hl":
        assert (cpu.h, cpu.l) == (0x34, 0x12)
    else:
        assert (cpu.a, int(cpu.f)) == (0x34, 0x12)
    assert cpu.sp == 0x4002
    assert cpu.q == 0
    assert cpu.pc == 0x2000 + (2 if prefix is not None else 1)
    assert cpu.r == 0x3E + (2 if prefix is not None else 1)
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 10 + (4 if prefix is not None else 0)


@pytest.mark.parametrize(
    ("prefix", "opcode", "value"),
    (
        (None, 0xC5, 0xA65A),
        (None, 0xD5, 0xB34C),
        (None, 0xE5, 0xD27E),
        (None, 0xF5, 0xE19D),
        (0xDD, 0xC5, 0xA65A),
        (0xFD, 0xC5, 0xA65A),
        (0xDD, 0xD5, 0xB34C),
        (0xFD, 0xD5, 0xB34C),
        (0xDD, 0xF5, 0xE19D),
        (0xFD, 0xF5, 0xE19D),
    ),
)
def test_push_pairs_and_af(prefix: int | None, opcode: int, value: int) -> None:
    """Base PUSH and DD/FD prefix-ignored PUSH forms preserve index registers."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.sp = 0x4000
    cpu.ix, cpu.iy = 0x1234, 0x5678
    cpu.b, cpu.c = 0xA6, 0x5A
    cpu.d, cpu.e = 0xB3, 0x4C
    cpu.h, cpu.l = 0xD2, 0x7E
    cpu.a, cpu.f.byte = 0xE1, 0x9D
    cpu.r = 0x3E
    cpu.q = 0xA5

    tstates = _run(cpu, bytes(([prefix] if prefix is not None else []) + [opcode]))

    assert cpu.read_byte(0x3FFE) == (value & 0xFF)
    assert cpu.read_byte(0x3FFF) == (value >> 8)
    assert cpu.sp == 0x3FFE
    assert cpu.q == 0
    assert cpu.pc == 0x2000 + (2 if prefix is not None else 1)
    assert cpu.r == 0x3E + (2 if prefix is not None else 1)
    assert cpu.ix == 0x1234
    assert cpu.iy == 0x5678
    assert tstates == 11 + (4 if prefix is not None else 0)


@pytest.mark.parametrize("prefix", (None, 0xDD, 0xFD), ids=("base", "dd", "fd"))
def test_exx_is_prefix_ignored(prefix: int | None) -> None:
    """EXX swaps BC/DE/HL register sets and leaves flags, WZ, and index pairs alone."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.ix, cpu.iy = 0x1234, 0x5678
    cpu.b, cpu.c, cpu.d, cpu.e, cpu.h, cpu.l = 0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC
    cpu.bc_, cpu.de_, cpu.hl_ = 0xDEF0, 0x1357, 0x2468
    cpu.r, cpu.wz, cpu.f.byte, cpu.q = 0x3E, 0xBEEF, 0xC5, 0xC5

    tstates = _run(cpu, bytes(([prefix] if prefix is not None else []) + [0xD9]))

    assert (cpu.b, cpu.c, cpu.d, cpu.e, cpu.h, cpu.l) == (0xDE, 0xF0, 0x13, 0x57, 0x24, 0x68)
    assert (cpu.bc_, cpu.de_, cpu.hl_) == (0x1234, 0x5678, 0x9ABC)
    assert int(cpu.f) == 0xC5
    assert cpu.q == 0
    assert cpu.wz == 0xBEEF
    assert cpu.pc == 0x2000 + (2 if prefix is not None else 1)
    assert cpu.r == 0x3E + (2 if prefix is not None else 1)
    assert tstates == 4 + (4 if prefix is not None else 0)


@pytest.mark.parametrize("prefix", (None, 0xDD, 0xFD), ids=("base", "dd", "fd"))
def test_exchange_stack_with_hl_or_selected_index(prefix: int | None) -> None:
    """EX (SP),HL is ordinary base behavior; DD/FD select IX/IY instead."""
    cpu = MemoryCPU()
    cpu.pc, cpu.sp = 0x2000, 0x4000
    cpu.ix, cpu.iy = 0x1234, 0x5678
    cpu.h, cpu.l = 0x9A, 0xBC
    cpu.r, cpu.wz, cpu.f.byte, cpu.q = 0x3E, 0xBEEF, 0xC5, 0xC5
    cpu.write_byte(cpu.sp, 0x12)
    cpu.write_byte(cpu.sp + 1, 0x34)

    tstates = _run(cpu, bytes(([prefix] if prefix is not None else []) + [0xE3]))

    assert (cpu.h, cpu.l) == ((0x34, 0x12) if prefix is None else (0x9A, 0xBC))
    assert cpu.ix == (0x3412 if prefix == 0xDD else 0x1234)
    assert cpu.iy == (0x3412 if prefix == 0xFD else 0x5678)
    outgoing = 0x9ABC if prefix is None else (0x1234 if prefix == 0xDD else 0x5678)
    assert cpu.read_byte(cpu.sp) == (outgoing & 0xFF)
    assert cpu.read_byte(cpu.sp + 1) == (outgoing >> 8)
    assert cpu.wz == 0x3412
    assert cpu.q == 0
    assert cpu.pc == 0x2000 + (2 if prefix is not None else 1)
    assert cpu.r == 0x3E + (2 if prefix is not None else 1)
    assert tstates == (23 if prefix is not None else 19)
