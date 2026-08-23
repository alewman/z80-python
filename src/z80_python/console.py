"""Portable command debugger built as a thin frontend over DebugSession."""

import shlex
from dataclasses import dataclass
from typing import TextIO

from z80_python.debug import DebugSession, RunResult, StepRecord
from z80_python.disasm import ByteReader, Instruction, disassemble
from z80_python.state import CPUState


class CommandError(ValueError):
    """A malformed or unsupported debugger command."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Rendered lines and control state returned by one debugger command."""

    lines: tuple[str, ...] = ()
    quit: bool = False

    def __post_init__(self) -> None:
        if type(self.lines) is not tuple or not all(type(line) is str for line in self.lines):
            raise ValueError("lines must be a tuple of strings")
        if type(self.quit) is not bool:
            raise ValueError("quit must be a bool")


_HELP = (
    "help                         Show this command summary",
    "registers | regs             Show CPU registers and lifecycle state",
    "step [COUNT]                 Execute one or more boundaries",
    "run STEPS [T_STATES]         Run with finite step and optional timing limits",
    "break ADDRESS                Add an execute breakpoint",
    "delete ADDRESS               Remove an execute breakpoint",
    "breakpoints                  List execute breakpoints",
    "disassemble [ADDRESS] [COUNT] Decode instructions without side effects",
    "memory ADDRESS [LENGTH]      Display up to 256 bytes",
    "history [COUNT]              Show retained step records",
    "quit | exit                  Leave the command loop",
)


def _number(text: str, name: str, *, maximum: int | None = None) -> int:
    try:
        value = int(text, 0)
    except ValueError as exc:
        raise CommandError(f"{name} must be an integer") from exc
    if value < 0 or (maximum is not None and value > maximum):
        suffix = f" in range 0..{maximum}" if maximum is not None else " non-negative"
        raise CommandError(f"{name} must be{suffix}")
    return value


def _positive(text: str, name: str, *, maximum: int | None = None) -> int:
    value = _number(text, name, maximum=maximum)
    if value == 0:
        raise CommandError(f"{name} must be positive")
    return value


def _flags(value: int) -> str:
    labels = "SZ5H3PNC"
    return "".join(label if value & (0x80 >> index) else "-" for index, label in enumerate(labels))


def _format_state(state: CPUState) -> tuple[str, ...]:
    vector = state.maskable_interrupt_vector
    irq = "--" if vector is None else f"{vector:02X}"
    return (
        f"AF={state.a:02X}{state.f:02X} BC={state.b:02X}{state.c:02X} "
        f"DE={state.d:02X}{state.e:02X} HL={state.h:02X}{state.l:02X} F={_flags(state.f)}",
        f"PC={state.pc:04X} SP={state.sp:04X} IX={state.ix:04X} IY={state.iy:04X} "
        f"WZ={state.wz:04X} I={state.i:02X} R={state.r:02X}",
        f"AF'={state.af_alt:04X} BC'={state.bc_alt:04X} "
        f"DE'={state.de_alt:04X} HL'={state.hl_alt:04X} Q={state.q:02X}",
        f"IM={state.im} IFF1={int(state.iff1)} IFF2={int(state.iff2)} "
        f"HALT={int(state.halted)} EI_DELAY={state.ei_delay} "
        f"RESET={int(state.reset_pending)} NMI={int(state.non_maskable_interrupt_pending)} "
        f"IRQ={irq}",
    )


def _format_instruction(instruction: Instruction) -> str:
    encoded = " ".join(f"{value:02X}" for value in instruction.data)
    return f"{instruction.address:04X}  {encoded:<11}  {instruction.text}"


def _format_record(record: StepRecord) -> str:
    if record.instruction is not None:
        work = _format_instruction(record.instruction)
    else:
        work = f"{record.before.pc:04X}  {record.kind.value}"
    return f"#{record.sequence} {work} -> PC={record.after.pc:04X} +{record.t_states}T"


def _format_run(result: RunResult) -> str:
    return (
        f"stopped={result.reason.value} steps={result.steps} "
        f"instructions={result.instructions} t_states={result.t_states} PC={result.state.pc:04X}"
    )


class CommandDebugger:
    """Parse and execute portable debugger commands against a DebugSession."""

    def __init__(self, session: DebugSession) -> None:
        if type(session) is not DebugSession:
            raise TypeError("session must be a DebugSession")
        self.session = session

    def execute(self, command: str) -> CommandResult:
        """Execute one command and return deterministic printable lines."""

        if type(command) is not str:
            raise TypeError("command must be a string")
        try:
            words = shlex.split(command)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if not words:
            return CommandResult()

        name, *arguments = words
        name = name.lower()
        if name in ("quit", "exit"):
            self._arity(name, arguments, 0)
            return CommandResult(quit=True)
        if name == "help":
            self._arity(name, arguments, 0)
            return CommandResult(_HELP)
        if name in ("registers", "regs"):
            self._arity(name, arguments, 0)
            return CommandResult(_format_state(self.session.target.capture_state()))
        if name == "step":
            return self._step(arguments)
        if name == "run":
            return self._run(arguments)
        if name == "break":
            self._arity(name, arguments, 1)
            address = _number(arguments[0], "address", maximum=0xFFFF)
            self.session.add_breakpoint(address)
            return CommandResult((f"breakpoint added at {address:04X}",))
        if name == "delete":
            self._arity(name, arguments, 1)
            address = _number(arguments[0], "address", maximum=0xFFFF)
            self.session.remove_breakpoint(address)
            return CommandResult((f"breakpoint removed from {address:04X}",))
        if name == "breakpoints":
            self._arity(name, arguments, 0)
            lines = tuple(f"{address:04X}" for address in sorted(self.session.breakpoints))
            return CommandResult(lines or ("no breakpoints",))
        if name in ("disassemble", "disasm"):
            return self._disassemble(arguments)
        if name == "memory":
            return self._memory(arguments)
        if name == "history":
            return self._history(arguments)
        raise CommandError(f"unknown command: {name}")

    def interact(
        self,
        input_stream: TextIO,
        output_stream: TextIO,
        *,
        prompt: str = "z80> ",
    ) -> None:
        """Run a line-oriented debugger loop over supplied text streams."""

        while True:
            output_stream.write(prompt)
            output_stream.flush()
            line = input_stream.readline()
            if line == "":
                return
            try:
                result = self.execute(line)
            except CommandError as exc:
                output_stream.write(f"error: {exc}\n")
                continue
            for rendered in result.lines:
                output_stream.write(f"{rendered}\n")
            if result.quit:
                return

    def _step(self, arguments: list[str]) -> CommandResult:
        self._arity("step", arguments, 0, 1)
        count = _positive(arguments[0], "count", maximum=10_000) if arguments else 1
        records = tuple(self.session.step() for _ in range(count))
        return CommandResult(tuple(_format_record(record) for record in records))

    def _run(self, arguments: list[str]) -> CommandResult:
        self._arity("run", arguments, 1, 2)
        steps = _positive(arguments[0], "steps")
        t_states = _positive(arguments[1], "t_states") if len(arguments) == 2 else None
        result = self.session.run(max_steps=steps, max_t_states=t_states)
        return CommandResult((_format_run(result),))

    def _disassemble(self, arguments: list[str]) -> CommandResult:
        self._arity("disassemble", arguments, 0, 2)
        peek = self._require_peek()
        state = self.session.target.capture_state()
        address = _number(arguments[0], "address", maximum=0xFFFF) if arguments else state.pc
        count = _positive(arguments[1], "count", maximum=256) if len(arguments) == 2 else 8
        instructions = []
        for _ in range(count):
            instruction = disassemble(peek, address)
            instructions.append(instruction)
            address = instruction.next_address
        return CommandResult(tuple(_format_instruction(item) for item in instructions))

    def _memory(self, arguments: list[str]) -> CommandResult:
        self._arity("memory", arguments, 1, 2)
        peek = self._require_peek()
        address = _number(arguments[0], "address", maximum=0xFFFF)
        length = _positive(arguments[1], "length", maximum=256) if len(arguments) == 2 else 16
        lines = []
        for offset in range(0, length, 16):
            row_address = (address + offset) & 0xFFFF
            row_length = min(16, length - offset)
            values = [
                self._read_peek(peek, (row_address + column) & 0xFFFF)
                for column in range(row_length)
            ]
            lines.append(f"{row_address:04X}  {' '.join(f'{value:02X}' for value in values)}")
        return CommandResult(tuple(lines))

    def _history(self, arguments: list[str]) -> CommandResult:
        self._arity("history", arguments, 0, 1)
        count = _positive(arguments[0], "count", maximum=10_000) if arguments else 16
        records = self.session.history[-count:]
        lines = tuple(_format_record(record) for record in records)
        return CommandResult(lines or ("history empty",))

    def _require_peek(self) -> ByteReader:
        if self.session.peek_byte is None:
            raise CommandError("this session has no side-effect-free peek capability")
        return self.session.peek_byte

    @staticmethod
    def _read_peek(peek: ByteReader, address: int) -> int:
        value = peek(address)
        if type(value) is not int or not 0 <= value <= 0xFF:
            raise CommandError(f"peek returned a non-byte value at {address:04X}")
        return value

    @staticmethod
    def _arity(name: str, arguments: list[str], minimum: int, maximum: int | None = None) -> None:
        maximum = minimum if maximum is None else maximum
        if not minimum <= len(arguments) <= maximum:
            expected = str(minimum) if minimum == maximum else f"{minimum}..{maximum}"
            raise CommandError(f"{name} expects {expected} argument(s)")


__all__ = ["CommandDebugger", "CommandError", "CommandResult"]
