"""Focused tests for the documented consumer-facing Z80 API."""

from dataclasses import FrozenInstanceError, asdict, replace

import pytest

from examples.minimal_z80_host import MinimalZ80Host
from z80_python import Z80CPU, CPUState, Flags
from z80_python.cpu import Z80CPU as CpuModuleZ80CPU
from z80_python.cpu import CPUState as CpuModuleCPUState
from z80_python.cpu import Flags as CpuModuleFlags


def test_root_and_historical_module_exports_are_compatible() -> None:
    assert Z80CPU is CpuModuleZ80CPU
    assert Flags is CpuModuleFlags
    assert CPUState is CpuModuleCPUState


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


def test_cpu_state_is_immutable_comparable_and_serializable() -> None:
    state = CPUState(a=0x12, f=0xA5, pc=0x3456, halted=True)

    assert state == CPUState(a=0x12, f=0xA5, pc=0x3456, halted=True)
    assert asdict(state)["pc"] == 0x3456
    with pytest.raises(FrozenInstanceError):
        state.pc = 0  # type: ignore[misc]


def test_capture_and_restore_cover_complete_cpu_owned_state_without_touching_host() -> None:
    cpu = MinimalZ80Host()
    cpu.a, cpu.f.byte, cpu.b, cpu.c = 1, 2, 3, 4
    cpu.d, cpu.e, cpu.h, cpu.l = 5, 6, 7, 8
    cpu.ix, cpu.iy, cpu.sp, cpu.pc, cpu.wz = 0x1111, 0x2222, 0x3333, 0x4444, 0x5555
    cpu.i, cpu.r, cpu.iff1, cpu.iff2, cpu.im = 9, 0x8A, True, False, 2
    cpu.af_, cpu.bc_, cpu.de_, cpu.hl_ = 0x6666, 0x7777, 0x8888, 0x9999
    cpu.q, cpu.halted, cpu._ei_delay = 0xA5, True, 1
    cpu.request_reset()
    cpu.request_maskable_interrupt(0x34)
    cpu.request_non_maskable_interrupt()
    cpu.memory[0x1234] = 0x56
    cpu.ports[0x1234] = 0x78
    flags_object = cpu.f

    state = cpu.capture_state()
    cpu.restore_state(CPUState())
    cpu.restore_state(state)

    assert cpu.capture_state() == state
    assert cpu.f is flags_object
    assert cpu.memory[0x1234] == 0x56
    assert cpu.ports[0x1234] == 0x78


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("a", -1),
        ("f", 0x100),
        ("pc", 0x1_0000),
        ("im", 3),
        ("ei_delay", 2),
        ("halted", 1),
        ("maskable_interrupt_vector", 0x100),
    ],
)
def test_cpu_state_rejects_values_outside_its_contract(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        replace(CPUState(), **{field: value})


def test_restore_requires_a_cpu_state() -> None:
    cpu = MinimalZ80Host()

    with pytest.raises(TypeError, match="CPUState"):
        cpu.restore_state({})  # type: ignore[arg-type]


def test_restored_ei_delay_and_pending_interrupt_continue_deterministically() -> None:
    cpu = MinimalZ80Host()
    cpu.memory[:2] = bytes((0xFB, 0x00))  # EI; NOP
    cpu.sp = 0x4000

    assert cpu.step() == 4
    cpu.request_maskable_interrupt()
    state = cpu.capture_state()
    memory = bytes(cpu.memory)

    first_run = (cpu.step(), cpu.step(), cpu.capture_state())
    cpu.memory[:] = memory
    cpu.restore_state(state)
    second_run = (cpu.step(), cpu.step(), cpu.capture_state())

    assert second_run == first_run
