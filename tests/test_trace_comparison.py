"""Incremental processor-trace comparison and first-divergence diagnosis."""

from dataclasses import fields, replace

import pytest

from examples.minimal_z80_host import MinimalZ80Host
from z80_python import (
    BoundaryKind,
    DebugSession,
    StepRecord,
    TraceDifference,
    compare_step_records,
    first_trace_divergence,
    iter_trace_divergences,
)


def _history(program: bytes, *, a: int = 0) -> tuple[StepRecord, ...]:
    cpu = MinimalZ80Host()
    cpu.memory[: len(program)] = program
    cpu.a = a
    session = DebugSession(cpu, peek_byte=cpu.memory.__getitem__)
    session.run(max_steps=2)
    return session.history


def test_equal_traces_ignore_session_local_sequence_numbers() -> None:
    left = _history(bytes((0x3C, 0x00)))
    right = tuple(replace(record, sequence=record.sequence + 100) for record in left)

    assert compare_step_records(left[0], right[0]) == ()
    assert first_trace_divergence(left, right) is None
    assert tuple(iter_trace_divergences(left, right)) == ()


def test_first_divergence_reports_instruction_and_state_fields() -> None:
    left = _history(bytes((0x3C, 0x00)), a=0)
    right = _history(bytes((0x3D, 0x00)), a=0)

    divergence = first_trace_divergence(left, right)

    assert divergence is not None
    assert divergence.position == 0
    differences = {item.path: (item.left, item.right) for item in divergence.differences}
    assert differences["instruction.data"] == ("3c", "3d")
    assert differences["instruction.mnemonic"] == ("INC", "DEC")
    assert differences["after.a"] == (1, 0xFF)
    assert divergence.as_dict()["position"] == 0


def test_comparison_reports_boundary_timing_and_each_cpu_state_side() -> None:
    record = _history(bytes((0x00, 0x00)))[0]
    changed = replace(
        record,
        kind=BoundaryKind.HALT_IDLE,
        t_states=7,
        before=replace(record.before, pc=0x1234),
        after=replace(record.after, iff1=True),
        instruction=None,
    )

    paths = {item.path for item in compare_step_records(record, changed)}

    assert paths == {
        "kind",
        "instruction",
        "t_states",
        "before.pc",
        "after.iff1",
    }


def test_every_cpu_state_field_participates_in_before_and_after_comparison() -> None:
    record = _history(bytes((0x00, 0x00)))[0]

    for field in fields(record.before):
        current = getattr(record.before, field.name)
        if type(current) is bool:
            changed_value = not current
        elif current is None:
            changed_value = 0xFF
        elif field.name == "im":
            changed_value = (current + 1) % 3
        elif field.name == "ei_delay":
            changed_value = 1 - current
        else:
            changed_value = current ^ 1

        changed = replace(record, before=replace(record.before, **{field.name: changed_value}))

        assert [item.path for item in compare_step_records(record, changed)] == [
            f"before.{field.name}"
        ]


def test_one_sided_exhaustion_is_explicit_and_continues_incrementally() -> None:
    records = _history(bytes((0x00, 0x00)))

    divergences = tuple(iter_trace_divergences(records[:1], records))

    assert len(divergences) == 1
    assert divergences[0].position == 1
    assert divergences[0].left is None
    assert divergences[0].right == records[1]
    assert divergences[0].differences == (TraceDifference("record", None, "present"),)


def test_first_divergence_stops_consuming_after_the_unequal_pair() -> None:
    records = _history(bytes((0x00, 0x00)))
    consumed: list[int] = []

    def right_trace():
        consumed.append(0)
        yield replace(records[0], t_states=5)
        consumed.append(1)
        yield records[1]

    assert first_trace_divergence(records, right_trace()) is not None
    assert consumed == [0]


def test_trace_values_and_records_are_validated() -> None:
    record = _history(bytes((0x00, 0x00)))[0]

    with pytest.raises(ValueError, match="unequal"):
        TraceDifference("pc", 1, 1)
    with pytest.raises(TypeError, match="StepRecord"):
        compare_step_records(record, object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="traces"):
        tuple(iter_trace_divergences((record,), (object(),)))  # type: ignore[arg-type]
