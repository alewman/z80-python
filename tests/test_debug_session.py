"""Dependency-free debug-session control and evidence contracts."""

from dataclasses import replace

import pytest

from examples.minimal_z80_host import MinimalZ80Host
from z80_python import BoundaryKind, DebugSession, DebugTarget, RunResult, StopReason


def _session(program: bytes, *, history_limit: int = 256) -> tuple[MinimalZ80Host, DebugSession]:
    cpu = MinimalZ80Host()
    cpu.memory[: len(program)] = program
    return cpu, DebugSession(cpu, peek_byte=cpu.memory.__getitem__, history_limit=history_limit)


def test_step_records_disassembly_state_delta_and_totals() -> None:
    cpu, session = _session(bytes((0x3E, 0x2A)))

    record = session.step()

    assert record.sequence == 0
    assert record.kind is BoundaryKind.INSTRUCTION
    assert record.instruction is not None
    assert record.instruction.text == "LD A, 0x2A"
    assert (record.before.pc, record.after.pc, record.after.a, record.t_states) == (0, 2, 0x2A, 7)
    assert (session.total_steps, session.total_instructions, session.total_t_states) == (1, 1, 7)
    assert session.history == (record,)
    assert cpu.pc == 2


def test_execute_breakpoint_stops_before_instruction_and_step_can_cross_it() -> None:
    cpu, session = _session(bytes((0x00, 0x00)))
    session.add_breakpoint(1)

    result = session.run(max_steps=10)

    assert result.reason is StopReason.BREAKPOINT
    assert (result.steps, result.instructions, result.t_states, cpu.pc) == (1, 1, 4, 1)
    assert session.step().after.pc == 2


def test_halt_stops_without_consuming_an_extra_idle_cycle() -> None:
    cpu, session = _session(bytes((0x76,)))

    result = session.run(max_steps=10)

    assert result.reason is StopReason.HALTED
    assert (result.steps, result.instructions, result.t_states) == (1, 1, 4)
    assert cpu.halted is True


def test_pending_nmi_wakes_halted_cpu_instead_of_reporting_halted() -> None:
    cpu, session = _session(bytes((0x76,)))
    session.step()
    cpu.sp = 0x8000
    cpu.request_non_maskable_interrupt()

    result = session.run(max_steps=1)

    assert result.reason is StopReason.STEP_LIMIT
    assert result.last_record is not None
    assert result.last_record.kind is BoundaryKind.NON_MASKABLE_INTERRUPT
    assert (result.instructions, result.t_states, cpu.pc, cpu.halted) == (0, 11, 0x0066, False)


def test_accepted_maskable_interrupt_is_a_lifecycle_boundary_not_an_instruction() -> None:
    cpu, session = _session(bytes((0x00,)))
    cpu.sp, cpu.im, cpu.iff1, cpu.iff2 = 0x8000, 1, True, True
    cpu.request_maskable_interrupt()

    record = session.step()

    assert record.kind is BoundaryKind.MASKABLE_INTERRUPT
    assert record.instruction is None
    assert (record.t_states, record.after.pc, session.total_instructions) == (13, 0x0038, 0)


def test_reset_and_halt_idle_boundaries_are_classified_without_disassembly() -> None:
    cpu, session = _session(bytes((0x00,)))
    cpu.request_reset()
    reset = session.step()
    cpu.clear_reset()
    cpu.halted = True
    idle = session.step()

    assert (reset.kind, reset.instruction, reset.t_states) == (BoundaryKind.RESET, None, 3)
    assert (idle.kind, idle.instruction, idle.t_states) == (BoundaryKind.HALT_IDLE, None, 4)


def test_run_can_explicitly_consume_halt_idle_boundaries() -> None:
    cpu, session = _session(bytes((0x76,)))
    session.step()

    result = session.run(max_steps=2, stop_on_halt=False)

    assert result.reason is StopReason.STEP_LIMIT
    assert (result.steps, result.instructions, result.t_states, cpu.halted) == (2, 0, 8, True)
    assert all(record.kind is BoundaryKind.HALT_IDLE for record in session.history[-2:])


def test_t_state_budget_is_checked_after_an_atomic_boundary() -> None:
    _cpu, session = _session(bytes((0x00, 0x00)))

    result = session.run(max_steps=10, max_t_states=3)

    assert result.reason is StopReason.T_STATE_LIMIT
    assert (result.steps, result.t_states) == (1, 4)


def test_history_is_bounded_clearable_and_optionally_disabled() -> None:
    _cpu, session = _session(bytes((0x00, 0x00, 0x00)), history_limit=2)
    session.run(max_steps=3)

    assert [record.sequence for record in session.history] == [1, 2]
    assert [record.sequence for record in session.iter_history(newest_first=True)] == [2, 1]
    session.clear_history()
    assert session.history == ()

    _cpu, disabled = _session(bytes((0x00,)), history_limit=0)
    record = disabled.step()
    assert (record.sequence, disabled.history, disabled.total_steps) == (0, (), 1)


def test_session_without_peek_retains_execution_control() -> None:
    cpu = MinimalZ80Host()
    cpu.memory[0] = 0x00
    session = DebugSession(cpu)

    record = session.step()

    assert record.instruction is None
    assert record.after.pc == 1


def test_debug_target_is_a_runtime_checkable_structural_protocol() -> None:
    cpu = MinimalZ80Host()

    assert isinstance(cpu, DebugTarget)
    assert not isinstance(object(), DebugTarget)


def test_public_debug_values_reject_invalid_construction() -> None:
    _cpu, session = _session(bytes((0x00,)))
    record = session.step()

    with pytest.raises(ValueError, match="sequence"):
        replace(record, sequence=-1)
    with pytest.raises(ValueError, match="lifecycle"):
        replace(record, kind=BoundaryKind.RESET)
    with pytest.raises(ValueError, match="t_states"):
        replace(record, t_states=0)
    with pytest.raises(ValueError, match="instructions cannot exceed"):
        RunResult(StopReason.STEP_LIMIT, 0, 1, 0, record.after, None)
    with pytest.raises(ValueError, match="last_record"):
        RunResult(StopReason.STEP_LIMIT, 1, 1, 4, record.after, object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"max_steps": 0}, "max_steps"),
        ({"max_steps": 1, "max_t_states": 0}, "max_t_states"),
        ({"max_steps": 1, "stop_on_halt": 1}, "stop_on_halt"),
    ],
)
def test_run_rejects_invalid_or_unbounded_limits(
    arguments: dict[str, object], message: str
) -> None:
    _cpu, session = _session(bytes((0x00,)))

    with pytest.raises(ValueError, match=message):
        session.run(**arguments)  # type: ignore[arg-type]
