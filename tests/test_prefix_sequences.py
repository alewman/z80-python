"""Runs of DD/FD prefixes, and DD/FD before ED.

A DD or FD is a flag ("use IX or IY instead of HL") for the opcode that
follows, not an instruction. Sean Young, *The Undocumented Z80 Documented*
v0.91, section 3.7: "In a large sequence of DD and FD bytes, it is the last
one that counts. Also any other byte (or instruction) resets this flag."
Section 6.1: "Just a stray DD or FD increases the R by one." Chapter 5: no
interrupt is accepted inside such a run. The only vector any test set holds
for this is FUSE's ``ddfd00`` (emulator-derived), replayed below; the
SingleStepTests corpus has no files for these sequences.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from z80_python import Z80CPU, disassemble_bytes, read_trace
from z80_python.conformance import diff_manifest, load_manifest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "conformance"


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


def _cpu(program: bytes, **registers: int) -> MemoryCPU:
    cpu = MemoryCPU()
    cpu.memory[: len(program)] = program
    for name, value in registers.items():
        setattr(cpu, name, value)
    return cpu


def test_a_stray_prefix_is_one_m1_and_nothing_else() -> None:
    cpu = _cpu(bytes((0xDD, 0xDD, 0x00)), a=0x5A, ix=0x1234, iy=0x5678, wz=0xBEEF)
    before = cpu.capture_state()

    assert cpu.step() == 12  # DD (4) + DD (4) + NOP (4)

    assert cpu.capture_state() == replace(before, pc=3, r=3)


def test_fuse_ddfd00_case() -> None:
    """FUSE's ``ddfd00``: DD FD 00 00 from a zeroed CPU is 16 T-states, PC 4, R 4."""
    cpu = _cpu(bytes((0xDD, 0xFD, 0x00, 0x00)))

    assert cpu.step() + cpu.step() == 16

    assert (cpu.pc, cpu.r) == (0x0004, 0x04)


@pytest.mark.parametrize(
    ("program", "ix", "iy"),
    (
        (bytes((0xFD, 0xDD, 0x21, 0x00, 0x10)), 0x1000, 0),
        (bytes((0xDD, 0xFD, 0x21, 0x00, 0x10)), 0, 0x1000),
        (bytes((0xDD, 0xDD, 0xDD, 0xFD, 0x21, 0x00, 0x10)), 0, 0x1000),
    ),
)
def test_the_last_prefix_decides_the_index_register(program: bytes, ix: int, iy: int) -> None:
    cpu = _cpu(program)
    prefixes = len(program) - 3

    # LD IX/IY,nn is 14 with its own prefix; every earlier prefix is a 4-T-state stray.
    assert cpu.step() == 4 * (prefixes - 1) + 14

    assert (cpu.ix, cpu.iy, cpu.pc, cpu.r) == (ix, iy, len(program), prefixes + 1)


def test_youngs_example_any_other_byte_resets_the_flag() -> None:
    """Young 3.7: ``FD DD 00 21 00 10`` is NOP NOP NOP LD HL,1000h."""
    cpu = _cpu(bytes((0xFD, 0xDD, 0x00, 0x21, 0x00, 0x10)))

    assert cpu.step() == 12
    assert cpu.step() == 10

    assert (cpu._hl(), cpu.ix, cpu.iy, cpu.pc, cpu.r) == (0x1000, 0, 0, 6, 4)


def test_ed_after_an_index_prefix_runs_the_ed_instruction_unchanged() -> None:
    cpu = _cpu(bytes((0xDD, 0xED, 0x44)), a=0x01)  # NEG

    assert cpu.step() == 4 + 8

    assert (cpu.a, cpu.f.n, cpu.f.c, cpu.pc, cpu.r) == (0xFF, 1, 1, 3, 3)


def test_ld_a_r_after_a_stray_prefix_sees_all_three_m1_increments() -> None:
    cpu = _cpu(bytes((0xFD, 0xED, 0x5F)))  # LD A,R

    assert cpu.step() == 4 + 9

    assert (cpu.a, cpu.r) == (3, 3)


def test_stray_prefix_before_ddcb_keeps_ddcb_r_accounting() -> None:
    cpu = _cpu(bytes((0xDD, 0xDD, 0xCB, 0x05, 0x46)), ix=0x2000)  # BIT 0,(IX+5)
    cpu.memory[0x2005] = 0x01

    assert cpu.step() == 4 + 20

    assert (cpu.f.z, cpu.pc, cpu.r) == (0, 5, 3)  # DD, DD, CB are M1s; d and op are not


def test_a_long_run_wraps_r_in_its_low_seven_bits() -> None:
    cpu = _cpu(bytes([0xDD] * 200) + bytes((0x21, 0x34, 0x12)), r=0x80)

    assert cpu.step() == 4 * 199 + 14

    # 200 prefix M1s plus the opcode's: 201 increments in the low seven bits, bit 7 kept.
    assert (cpu.ix, cpu.pc, cpu.r) == (0x1234, 203, 0x80 | (201 & 0x7F))


def test_no_interrupt_is_accepted_inside_a_prefix_run() -> None:
    """Young, chapter 5: a run of DDs holds interrupts off like a run of EIs."""
    cpu = _cpu(bytes((0xFB, 0xDD, 0xDD, 0xDD, 0x21, 0x00, 0x10)), sp=0xFFFF, im=1)

    cpu.step()  # EI
    cpu.request_maskable_interrupt(0xFF)
    assert cpu.step() == 8 + 14  # the whole run (two strays, then LD IX,nn), EI delay or not
    assert cpu.step() == 13  # accepted only now

    assert (cpu.ix, cpu.pc) == (0x1000, 0x0038)
    assert (cpu.memory[0xFFFD], cpu.memory[0xFFFE]) == (0x07, 0x00)


@pytest.mark.parametrize(
    ("encoded", "text"),
    (
        (bytes((0xDD, 0xDD, 0x00)), "NOP"),
        (bytes((0xFD, 0xDD, 0x21, 0x00, 0x10)), "LD IX, 0x1000"),
        (bytes((0xDD, 0xFD, 0x7C)), "LD A, IYH"),
        (bytes((0xDD, 0xED, 0x44)), "NEG"),
        (bytes((0xFD, 0xED, 0x4B, 0x34, 0x12)), "LD BC, (0x1234)"),
        (bytes((0xDD, 0xDD, 0xCB, 0x05, 0x46)), "BIT 0, (IX+0x05)"),
    ),
)
def test_disassembler_treats_the_run_as_one_instruction(encoded: bytes, text: str) -> None:
    instruction = disassemble_bytes(encoded, 0x1000)

    assert instruction.text == text
    assert instruction.data == encoded
    assert instruction.next_address == 0x1000 + len(encoded)


def test_committed_reference_trace_matches_a_fresh_run() -> None:
    manifest = load_manifest(EXAMPLES / "prefix-sequences.json")
    with (EXAMPLES / "prefix-sequences.jsonl").open(encoding="utf-8") as handle:
        assert diff_manifest(manifest, read_trace(handle)) is None
