"""Incremental processor-trace comparison and first-divergence diagnosis."""

from dataclasses import fields, replace
from io import StringIO

import pytest

from examples.minimal_z80_host import MinimalZ80Host
from z80_python import (
    TRACE_SCHEMA_VERSION,
    BoundaryKind,
    DebugSession,
    StepRecord,
    TraceDifference,
    compare_step_records,
    first_session_divergence,
    first_trace_divergence,
    iter_session_steps,
    iter_trace_divergences,
    read_trace,
    step_record_from_dict,
    step_record_to_dict,
    write_trace,
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


def test_live_sessions_stop_at_first_divergence_and_retain_prior_context() -> None:
    left_cpu = MinimalZ80Host()
    right_cpu = MinimalZ80Host()
    left_cpu.memory[:3] = bytes((0x00, 0x3C, 0x00))
    right_cpu.memory[:3] = bytes((0x00, 0x3D, 0x00))
    left = DebugSession(left_cpu, peek_byte=left_cpu.memory.__getitem__, history_limit=4)
    right = DebugSession(right_cpu, peek_byte=right_cpu.memory.__getitem__, history_limit=4)

    divergence = first_session_divergence(left, right, max_steps=3)

    assert divergence is not None
    assert divergence.position == 1
    assert "instruction.data" in {item.path for item in divergence.differences}
    assert "after.a" in {item.path for item in divergence.differences}
    assert (left.total_steps, right.total_steps) == (2, 2)
    assert left.history[0] == right.history[0]


def test_live_session_iteration_requires_a_finite_positive_budget() -> None:
    cpu = MinimalZ80Host()
    session = DebugSession(cpu)

    assert len(tuple(iter_session_steps(session, max_steps=2))) == 2
    with pytest.raises(ValueError, match="max_steps"):
        tuple(iter_session_steps(session, max_steps=0))


def test_trace_values_and_records_are_validated() -> None:
    record = _history(bytes((0x00, 0x00)))[0]

    with pytest.raises(ValueError, match="unequal"):
        TraceDifference("pc", 1, 1)
    with pytest.raises(TypeError, match="StepRecord"):
        compare_step_records(record, object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="traces"):
        tuple(iter_trace_divergences((record,), (object(),)))  # type: ignore[arg-type]


def test_json_lines_round_trip_is_deterministic_and_comparable() -> None:
    records = _history(bytes((0x3E, 0x2A, 0x00)))
    first = StringIO()
    second = StringIO()

    assert write_trace(iter(records), first) == 2
    assert write_trace(iter(records), second) == 2
    assert first.getvalue() == second.getvalue()
    assert f'"version":{TRACE_SCHEMA_VERSION}' in first.getvalue()

    first.seek(0)
    restored = tuple(read_trace(first))
    assert restored == records
    assert first_trace_divergence(restored, records) is None


def test_record_dictionary_round_trip_preserves_lifecycle_and_instruction_forms() -> None:
    instruction = _history(bytes((0x3E, 0x2A, 0x00)))[0]
    lifecycle = replace(instruction, kind=BoundaryKind.RESET, instruction=None, t_states=3)

    assert step_record_from_dict(step_record_to_dict(instruction)) == instruction
    assert step_record_from_dict(step_record_to_dict(lifecycle)) == lifecycle


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.pop("version"),
        lambda value: value.__setitem__("version", 999),
        lambda value: value.__setitem__("unknown", 1),
        lambda value: value["before"].pop("pc"),
        lambda value: value["instruction"].__setitem__("data", "not hex"),
    ),
)
def test_persisted_trace_schema_rejects_missing_unknown_and_invalid_fields(mutate) -> None:
    value = step_record_to_dict(_history(bytes((0x00, 0x00)))[0])
    mutate(value)

    with pytest.raises(ValueError):
        step_record_from_dict(value)


def test_read_trace_reports_the_malformed_line_number_lazily() -> None:
    record = _history(bytes((0x00, 0x00)))[0]
    stream = StringIO()
    write_trace((record,), stream)
    stream.write("{bad json}\n")
    stream.seek(0)
    records = read_trace(stream)

    assert next(records) == record
    with pytest.raises(ValueError, match="line 2"):
        next(records)
