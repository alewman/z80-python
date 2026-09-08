"""Headless runner for FUSE's Z80 core test set (``z80/tests/tests.in``).

FUSE, the Free Unix Spectrum Emulator, ships 1,356 single-instruction
cases whose expected results come from its own core, so this is an
emulator-derived oracle: a tier below SingleStepTests (hardware-corrected)
and z80test (hardware-captured), and useful mainly for the handful of
sequences those two do not cover (a prefix run, ``ddfd00``, is one).

The format and the harness conventions are those of FUSE's ``coretest.c``:

* A case names the instruction, then gives AF BC DE HL AF' BC' DE' HL' IX
  IY SP PC MEMPTR, then I R IFF1 IFF2 IM halted and the number of T-states
  to run, then memory to place (``address byte byte ... -1``) ending with a
  lone ``-1``.
* Memory is first filled with the repeating pattern ``DE AD BE EF``, and a
  port read returns the high byte of the port address.
* The core runs whole instructions until at least the requested T-states
  have elapsed; the expected total is the sum actually consumed.
* The expected file lists bus events (``MC``/``MR``/``MW``/``PR``/``PW``/
  ``PC`` with their cycle) before the final registers and changed memory.
  This core models instruction totals, not bus cycles, so the events are
  parsed and ignored; registers, MEMPTR, I, R, IFF1, IFF2, IM, the halted
  flag, the T-state total, and every listed memory byte are compared.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from z80_python.cpu import Z80CPU

REGISTER_NAMES = (
    "AF",
    "BC",
    "DE",
    "HL",
    "AF'",
    "BC'",
    "DE'",
    "HL'",
    "IX",
    "IY",
    "SP",
    "PC",
    "MEMPTR",
)


@dataclass(frozen=True)
class FuseCase:
    """One entry of ``tests.in``: the machine before the instruction."""

    name: str
    registers: tuple[int, ...]
    i: int
    r: int
    iff1: int
    iff2: int
    im: int
    halted: int
    t_states: int
    memory: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class FuseExpected:
    """One entry of ``tests.expected``: the machine after the instruction."""

    name: str
    registers: tuple[int, ...]
    i: int
    r: int
    iff1: int
    iff2: int
    im: int
    halted: int
    t_states: int
    memory: tuple[tuple[int, int], ...]
    events: tuple[tuple[str, ...], ...] = field(default=())


def _memory_lines(lines: list[str], index: int) -> tuple[list[tuple[int, int]], int]:
    """Parse ``address byte ... -1`` lines up to the terminating lone ``-1``."""
    memory: list[tuple[int, int]] = []
    while index < len(lines) and lines[index].strip() and lines[index].strip() != "-1":
        parts = lines[index].split()
        address = int(parts[0], 16)
        for item in parts[1:]:
            if item == "-1":
                break
            memory.append((address, int(item, 16)))
            address = (address + 1) & 0xFFFF
        index += 1
    return memory, index


def parse_tests_in(text: str) -> list[FuseCase]:
    """Parse a ``tests.in`` file."""
    lines = text.split("\n")
    cases: list[FuseCase] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        name = lines[index].strip()
        registers = tuple(int(item, 16) for item in lines[index + 1].split())
        misc = lines[index + 2].split()
        memory, index = _memory_lines(lines, index + 3)
        index += 1  # the lone -1
        cases.append(
            FuseCase(
                name,
                registers,
                int(misc[0], 16),
                int(misc[1], 16),
                int(misc[2]),
                int(misc[3]),
                int(misc[4]),
                int(misc[5]),
                int(misc[6]),
                tuple(memory),
            )
        )
    return cases


def parse_tests_expected(text: str) -> dict[str, FuseExpected]:
    """Parse a ``tests.expected`` file into a mapping by case name."""
    lines = text.split("\n")
    expected: dict[str, FuseExpected] = {}
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        name = lines[index].strip()
        index += 1
        events: list[tuple[str, ...]] = []
        while lines[index].startswith(" "):
            events.append(tuple(lines[index].split()))
            index += 1
        registers = tuple(int(item, 16) for item in lines[index].split())
        misc = lines[index + 1].split()
        memory, index = _memory_lines(lines, index + 2)
        expected[name] = FuseExpected(
            name,
            registers,
            int(misc[0], 16),
            int(misc[1], 16),
            int(misc[2]),
            int(misc[3]),
            int(misc[4]),
            int(misc[5]),
            int(misc[6]),
            tuple(memory),
            tuple(events),
        )
    return expected


class _FuseHostCPU(Z80CPU):
    """coretest.c's machine: patterned RAM, ports that read back their high byte."""

    def __init__(self) -> None:
        super().__init__()
        self.memory = bytearray(b"\xde\xad\xbe\xef" * 0x4000)

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        return (addr >> 8) & 0xFF

    def write_port(self, addr: int, value: int) -> None:
        pass


def run_case(case: FuseCase, expected: FuseExpected) -> list[str]:
    """Run one case and return the differences from ``expected`` (empty means pass)."""
    cpu = _FuseHostCPU()
    af, bc, de, hl, af_, bc_, de_, hl_, ix, iy, sp, pc, wz = case.registers
    cpu.a, cpu.f.byte = af >> 8, af & 0xFF
    cpu.b, cpu.c, cpu.d, cpu.e = bc >> 8, bc & 0xFF, de >> 8, de & 0xFF
    cpu.h, cpu.l = hl >> 8, hl & 0xFF
    cpu.af_, cpu.bc_, cpu.de_, cpu.hl_ = af_, bc_, de_, hl_
    cpu.ix, cpu.iy, cpu.sp, cpu.pc, cpu.wz = ix, iy, sp, pc, wz
    cpu.i, cpu.r, cpu.im = case.i, case.r, case.im
    cpu.iff1, cpu.iff2, cpu.halted = bool(case.iff1), bool(case.iff2), bool(case.halted)
    for address, value in case.memory:
        cpu.memory[address] = value

    total = 0
    while total < case.t_states:
        total += cpu.step()

    actual = (
        (cpu.a << 8) | cpu.f.byte,
        cpu._bc(),
        cpu._de(),
        cpu._hl(),
        cpu.af_,
        cpu.bc_,
        cpu.de_,
        cpu.hl_,
        cpu.ix,
        cpu.iy,
        cpu.sp,
        cpu.pc,
        cpu.wz,
    )
    differences = [
        f"{name}: got {got:04X}, expected {want:04X}"
        for name, got, want in zip(REGISTER_NAMES, actual, expected.registers, strict=True)
        if got != want
    ]
    for name, got, want in (
        ("I", cpu.i, expected.i),
        ("R", cpu.r, expected.r),
        ("IFF1", int(cpu.iff1), expected.iff1),
        ("IFF2", int(cpu.iff2), expected.iff2),
        ("IM", cpu.im, expected.im),
        ("halted", int(cpu.halted), expected.halted),
        ("T-states", total, expected.t_states),
    ):
        if got != want:
            differences.append(f"{name}: got {got}, expected {want}")
    for address, value in expected.memory:
        if cpu.memory[address] != value:
            differences.append(
                f"memory[{address:04X}]: got {cpu.memory[address]:02X}, expected {value:02X}"
            )
    return differences


def load_suite(directory: Path | str) -> list[tuple[FuseCase, FuseExpected]]:
    """Load ``tests.in`` and ``tests.expected`` from ``directory``, paired by name."""
    directory = Path(directory)
    cases = parse_tests_in((directory / "tests.in").read_text(encoding="utf-8"))
    expected = parse_tests_expected((directory / "tests.expected").read_text(encoding="utf-8"))
    missing = [case.name for case in cases if case.name not in expected]
    if missing:
        raise ValueError(f"tests.expected lacks entries for {missing[:5]}")
    return [(case, expected[case.name]) for case in cases]


__all__ = [
    "REGISTER_NAMES",
    "FuseCase",
    "FuseExpected",
    "load_suite",
    "parse_tests_expected",
    "parse_tests_in",
    "run_case",
]
