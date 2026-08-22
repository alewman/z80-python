"""Focused tests for the documented consumer-facing Z80 API."""

from examples.minimal_z80_host import MinimalZ80Host
from z80_python import Z80CPU, Flags
from z80_python.cpu import Z80CPU as CpuModuleZ80CPU
from z80_python.cpu import Flags as CpuModuleFlags


def test_root_and_historical_module_exports_are_compatible() -> None:
    assert Z80CPU is CpuModuleZ80CPU
    assert Flags is CpuModuleFlags


def test_minimal_host_masks_memory_and_io_boundaries() -> None:
    cpu = MinimalZ80Host()

    cpu.write_byte(0x1_2345, 0x1AB)
    cpu.write_port(0x1_FEDC, 0x155)

    assert cpu.read_byte(0x2345) == 0xAB
    assert cpu.read_port(0xFEDC) == 0x55


def test_step_executes_one_instruction_and_preserves_historical_name() -> None:
    cpu = MinimalZ80Host()
    cpu.memory[:3] = bytes((0x3E, 0x2A, 0x3C))  # LD A,2Ah; INC A

    assert cpu.step() == 7
    assert (cpu.pc, cpu.a) == (2, 0x2A)
    assert cpu.decode_and_execute() == 4
    assert (cpu.pc, cpu.a) == (3, 0x2B)
