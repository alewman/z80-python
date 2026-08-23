"""Dependency-free execution control and structured debugging records."""

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from z80_python.disasm import ByteReader, Instruction, disassemble
from z80_python.state import CPUState


class DebugTarget(Protocol):
    """Minimum processor interface consumed by :class:`DebugSession`."""

    def step(self) -> int:
        """Advance one instruction or lifecycle boundary and return T-states."""

    def capture_state(self) -> CPUState:
        """Capture the current CPU-owned state."""


class BoundaryKind(Enum):
    """Kind of work performed by one target ``step()`` call."""

    INSTRUCTION = "instruction"
    HALT_IDLE = "halt_idle"
    RESET = "reset"
    NON_MASKABLE_INTERRUPT = "non_maskable_interrupt"
    MASKABLE_INTERRUPT = "maskable_interrupt"


class StopReason(Enum):
    """Why a bounded debug-session run returned control."""

    BREAKPOINT = "breakpoint"
    HALTED = "halted"
    STEP_LIMIT = "step_limit"
    T_STATE_LIMIT = "t_state_limit"


@dataclass(frozen=True, slots=True)
class StepRecord:
    """Immutable before/after evidence for one processor boundary."""

    sequence: int
    kind: BoundaryKind
    before: CPUState
    after: CPUState
    t_states: int
    instruction: Instruction | None


@dataclass(frozen=True, slots=True)
class RunResult:
    """Summary of one bounded run operation."""

    reason: StopReason
    steps: int
    instructions: int
    t_states: int
    state: CPUState
    last_record: StepRecord | None


def _boundary_kind(state: CPUState) -> BoundaryKind:
    """Classify the next boundary from valid CPU state and lifecycle requests."""

    if state.reset_pending:
        return BoundaryKind.RESET
    if state.non_maskable_interrupt_pending:
        return BoundaryKind.NON_MASKABLE_INTERRUPT
    if (
        state.maskable_interrupt_vector is not None
        and state.iff1
        and state.ei_delay == 0
    ):
        return BoundaryKind.MASKABLE_INTERRUPT
    if state.halted:
        return BoundaryKind.HALT_IDLE
    return BoundaryKind.INSTRUCTION


class DebugSession:
    """Control an existing CPU host without modifying its execution core.

    ``peek_byte`` must be side-effect-free. If it is omitted, stepping and
    breakpoints still work but step records do not contain disassembly.
    """

    def __init__(
        self,
        target: DebugTarget,
        *,
        peek_byte: ByteReader | None = None,
        history_limit: int = 256,
    ) -> None:
        if not callable(getattr(target, "step", None)) or not callable(
            getattr(target, "capture_state", None)
        ):
            raise TypeError("target must provide step() and capture_state()")
        if peek_byte is not None and not callable(peek_byte):
            raise TypeError("peek_byte must be callable or None")
        if type(history_limit) is not int or history_limit < 0:
            raise ValueError("history_limit must be a non-negative integer")

        self.target = target
        self.peek_byte = peek_byte
        self.history_limit = history_limit
        self.breakpoints: set[int] = set()
        self.total_steps = 0
        self.total_instructions = 0
        self.total_t_states = 0
        self._history: deque[StepRecord] = deque(maxlen=history_limit or 1)

    @property
    def history(self) -> tuple[StepRecord, ...]:
        """Bounded immutable view of the retained step records."""

        return tuple(self._history)

    def clear_history(self) -> None:
        """Discard retained records without changing execution totals."""

        self._history.clear()

    def add_breakpoint(self, address: int) -> None:
        """Stop before executing the instruction at a 16-bit address."""

        self.breakpoints.add(self._validate_address(address))

    def remove_breakpoint(self, address: int) -> None:
        """Remove an execute breakpoint if it exists."""

        self.breakpoints.discard(self._validate_address(address))

    def step(self) -> StepRecord:
        """Advance exactly one boundary, ignoring execute breakpoints."""

        before = self.target.capture_state()
        kind = _boundary_kind(before)
        instruction = None
        if kind is BoundaryKind.INSTRUCTION and self.peek_byte is not None:
            instruction = disassemble(self.peek_byte, before.pc)

        t_states = self.target.step()
        if type(t_states) is not int or t_states <= 0:
            raise ValueError("target step() must return a positive integer T-state count")
        after = self.target.capture_state()
        record = StepRecord(
            sequence=self.total_steps,
            kind=kind,
            before=before,
            after=after,
            t_states=t_states,
            instruction=instruction,
        )
        self.total_steps += 1
        self.total_t_states += t_states
        if kind is BoundaryKind.INSTRUCTION:
            self.total_instructions += 1
        if self.history_limit:
            self._history.append(record)
        return record

    def run(
        self,
        *,
        max_steps: int,
        max_t_states: int | None = None,
        stop_on_halt: bool = True,
    ) -> RunResult:
        """Run until a stop condition or mandatory finite step budget is reached.

        A T-state limit is checked after each atomic boundary and may therefore be
        exceeded by that boundary's cost. Execute breakpoints stop before execution.
        """

        if type(max_steps) is not int or max_steps <= 0:
            raise ValueError("max_steps must be a positive integer")
        if max_t_states is not None and (
            type(max_t_states) is not int or max_t_states <= 0
        ):
            raise ValueError("max_t_states must be a positive integer or None")
        if type(stop_on_halt) is not bool:
            raise ValueError("stop_on_halt must be a bool")

        steps = 0
        instructions = 0
        t_states = 0
        last_record = None
        while steps < max_steps:
            state = self.target.capture_state()
            kind = _boundary_kind(state)
            if kind is BoundaryKind.INSTRUCTION and state.pc in self.breakpoints:
                return RunResult(
                    StopReason.BREAKPOINT,
                    steps,
                    instructions,
                    t_states,
                    state,
                    last_record,
                )
            if stop_on_halt and kind is BoundaryKind.HALT_IDLE:
                return RunResult(
                    StopReason.HALTED,
                    steps,
                    instructions,
                    t_states,
                    state,
                    last_record,
                )

            last_record = self.step()
            steps += 1
            t_states += last_record.t_states
            if last_record.kind is BoundaryKind.INSTRUCTION:
                instructions += 1
            if max_t_states is not None and t_states >= max_t_states:
                return RunResult(
                    StopReason.T_STATE_LIMIT,
                    steps,
                    instructions,
                    t_states,
                    last_record.after,
                    last_record,
                )

        state = last_record.after if last_record is not None else self.target.capture_state()
        return RunResult(
            StopReason.STEP_LIMIT,
            steps,
            instructions,
            t_states,
            state,
            last_record,
        )

    def iter_history(self, *, newest_first: bool = False) -> Iterator[StepRecord]:
        """Iterate retained records without exposing the mutable history buffer."""

        return reversed(self._history) if newest_first else iter(self._history)

    @staticmethod
    def _validate_address(address: int) -> int:
        if type(address) is not int or not 0 <= address <= 0xFFFF:
            raise ValueError("address must be an integer in range 0x0000..0xFFFF")
        return address


__all__ = [
    "BoundaryKind",
    "DebugSession",
    "DebugTarget",
    "RunResult",
    "StepRecord",
    "StopReason",
]
