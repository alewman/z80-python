"""Focused tests for the documented consumer-facing Z80 API."""

from dataclasses import FrozenInstanceError, asdict, replace

import pytest
from conftest import MemoryCPU

from z80_python import Z80CPU, CPUState, Flags
from z80_python.cpu import Z80CPU as CpuModuleZ80CPU
from z80_python.cpu import CPUState as CpuModuleCPUState
from z80_python.cpu import Flags as CpuModuleFlags


def test_root_and_historical_module_exports_are_compatible() -> None:
    assert Z80CPU is CpuModuleZ80CPU
    assert Flags is CpuModuleFlags
    assert CPUState is CpuModuleCPUState


def test_two_callables_are_a_complete_host_with_an_unconnected_io_bus() -> None:
    memory = bytearray(0x10000)
    cpu = Z80CPU(memory.__getitem__, memory.__setitem__)
    memory[:4] = bytes((0xDB, 0x12, 0xD3, 0x34))  # IN A,(12h); OUT (34h),A

    assert cpu.step() == 11
    assert cpu.a == 0xFF  # nothing drives the data bus
    assert cpu.step() == 11  # and the write goes nowhere
    assert memory[:4] == bytes((0xDB, 0x12, 0xD3, 0x34))


def test_bus_callables_are_validated_and_replaceable() -> None:
    memory = bytearray(0x10000)
    with pytest.raises(TypeError, match="write_byte must be callable"):
        Z80CPU(memory.__getitem__, memory)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="read_port must be callable"):
        Z80CPU(memory.__getitem__, memory.__setitem__, read_port=0xFF)  # type: ignore[arg-type]

    cpu = Z80CPU(memory.__getitem__, memory.__setitem__)
    reads: list[int] = []
    cpu.read_byte = lambda address: reads.append(address) or memory[address]
    cpu.step()  # NOP
    assert reads == [0x0000]


def test_subclass_defining_the_old_bus_methods_is_refused_with_the_new_form() -> None:
    with pytest.raises(TypeError, match=r"Z80CPU\(read_byte, write_byte, \*, read_port=None"):

        class OldHost(Z80CPU):
            def read_byte(self, addr: int) -> int:
                return 0


def test_step_executes_one_instruction_and_preserves_historical_name() -> None:
    cpu = MemoryCPU()
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
    cpu = MemoryCPU()
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
    cpu = MemoryCPU()

    with pytest.raises(TypeError, match="CPUState"):
        cpu.restore_state({})  # type: ignore[arg-type]


def test_restored_ei_delay_and_pending_interrupt_continue_deterministically() -> None:
    cpu = MemoryCPU()
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
