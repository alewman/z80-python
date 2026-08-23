"""Incremental comparison of deterministic processor-boundary traces."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, fields
from itertools import zip_longest

from z80_python.debug import StepRecord
from z80_python.disasm import Instruction
from z80_python.state import CPUState

TraceValue = int | bool | str | tuple[str, ...] | None
_MISSING = object()


@dataclass(frozen=True, slots=True)
class TraceDifference:
    """One unequal observation within an aligned trace position."""

    path: str
    left: TraceValue
    right: TraceValue

    def __post_init__(self) -> None:
        if type(self.path) is not str or not self.path:
            raise ValueError("path must be a non-empty string")
        if self.left == self.right:
            raise ValueError("a trace difference must contain unequal values")

    def as_dict(self) -> dict[str, TraceValue]:
        """Return a deterministic JSON-compatible representation."""

        return {"path": self.path, "left": self.left, "right": self.right}


@dataclass(frozen=True, slots=True)
class TraceDivergence:
    """All differences at one aligned processor-boundary position."""

    position: int
    left: StepRecord | None
    right: StepRecord | None
    differences: tuple[TraceDifference, ...]

    def __post_init__(self) -> None:
        if type(self.position) is not int or self.position < 0:
            raise ValueError("position must be a non-negative integer")
        if not self.differences:
            raise ValueError("differences must not be empty")

    def as_dict(self) -> dict[str, object]:
        """Return compact deterministic evidence without embedding entire states."""

        return {
            "position": self.position,
            "left_sequence": None if self.left is None else self.left.sequence,
            "right_sequence": None if self.right is None else self.right.sequence,
            "differences": [difference.as_dict() for difference in self.differences],
        }


def compare_step_records(left: StepRecord, right: StepRecord) -> tuple[TraceDifference, ...]:
    """Compare two aligned records while deliberately ignoring session sequence IDs."""

    if type(left) is not StepRecord or type(right) is not StepRecord:
        raise TypeError("left and right must be StepRecord values")

    differences: list[TraceDifference] = []
    _append(differences, "kind", left.kind.value, right.kind.value)
    _compare_instruction(differences, left.instruction, right.instruction)
    _append(differences, "t_states", left.t_states, right.t_states)
    _compare_state(differences, "before", left.before, right.before)
    _compare_state(differences, "after", left.after, right.after)
    return tuple(differences)


def iter_trace_divergences(
    left: Iterable[StepRecord], right: Iterable[StepRecord]
) -> Iterator[TraceDivergence]:
    """Yield unequal aligned positions incrementally until both traces end.

    Alignment uses iterable position rather than ``StepRecord.sequence`` because
    sequence numbers are local to a debug session. Inputs are consumed lazily and
    are never buffered as complete traces.
    """

    for position, pair in enumerate(zip_longest(left, right, fillvalue=_MISSING)):
        left_record, right_record = pair
        if left_record is _MISSING:
            if type(right_record) is not StepRecord:
                raise TypeError("right trace must contain only StepRecord values")
            difference = TraceDifference("record", None, "present")
            yield TraceDivergence(position, None, right_record, (difference,))
            continue
        if right_record is _MISSING:
            if type(left_record) is not StepRecord:
                raise TypeError("left trace must contain only StepRecord values")
            difference = TraceDifference("record", "present", None)
            yield TraceDivergence(position, left_record, None, (difference,))
            continue
        if type(left_record) is not StepRecord or type(right_record) is not StepRecord:
            raise TypeError("traces must contain only StepRecord values")
        differences = compare_step_records(left_record, right_record)
        if differences:
            yield TraceDivergence(position, left_record, right_record, differences)


def first_trace_divergence(
    left: Iterable[StepRecord], right: Iterable[StepRecord]
) -> TraceDivergence | None:
    """Return the first unequal aligned position, or ``None`` for equal traces."""

    return next(iter_trace_divergences(left, right), None)


def _append(
    differences: list[TraceDifference], path: str, left: TraceValue, right: TraceValue
) -> None:
    if left != right:
        differences.append(TraceDifference(path, left, right))


def _compare_state(
    differences: list[TraceDifference], prefix: str, left: CPUState, right: CPUState
) -> None:
    for field in fields(CPUState):
        _append(
            differences,
            f"{prefix}.{field.name}",
            getattr(left, field.name),
            getattr(right, field.name),
        )


def _compare_instruction(
    differences: list[TraceDifference],
    left: Instruction | None,
    right: Instruction | None,
) -> None:
    if left is None or right is None:
        _append(
            differences,
            "instruction",
            None if left is None else "present",
            None if right is None else "present",
        )
        return
    _append(differences, "instruction.address", left.address, right.address)
    _append(differences, "instruction.data", left.data.hex(), right.data.hex())
    _append(differences, "instruction.mnemonic", left.mnemonic, right.mnemonic)
    _append(differences, "instruction.operands", left.operands, right.operands)


__all__ = [
    "TraceDifference",
    "TraceDivergence",
    "TraceValue",
    "compare_step_records",
    "first_trace_divergence",
    "iter_trace_divergences",
]
