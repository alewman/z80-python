"""Portable command-debugger behavior over text streams."""

from io import StringIO

import pytest

from examples.minimal_z80_host import MinimalZ80Host
from z80_python import CommandDebugger, CommandError, CommandResult, DebugSession


def _debugger(program: bytes = bytes((0x00, 0x00, 0x00))) -> tuple[MinimalZ80Host, CommandDebugger]:
    cpu = MinimalZ80Host()
    cpu.memory[: len(program)] = program
    session = DebugSession(cpu, peek_byte=cpu.memory.__getitem__, history_limit=16)
    return cpu, CommandDebugger(session)


def test_registers_render_complete_cpu_and_lifecycle_state() -> None:
    cpu, debugger = _debugger()
    cpu.a, cpu.f.byte, cpu.pc, cpu.sp, cpu.ix = 0x12, 0xA5, 0x3456, 0x789A, 0xBCDE
    cpu.request_maskable_interrupt(0x34)

    result = debugger.execute("regs")

    assert result.lines[0].startswith("AF=12A5 BC=0000 DE=0000 HL=0000 F=S-5--P-C")
    assert "PC=3456 SP=789A IX=BCDE" in result.lines[1]
    assert result.lines[3].endswith("RESET=0 NMI=0 IRQ=34")


def test_step_run_breakpoint_and_history_share_session_semantics() -> None:
    cpu, debugger = _debugger()

    assert "#0 0000  00" in debugger.execute("step").lines[0]
    assert debugger.execute("break 0x0002").lines == ("breakpoint added at 0002",)
    assert "stopped=breakpoint steps=1" in debugger.execute("run 10").lines[0]
    assert cpu.pc == 2
    assert debugger.execute("breakpoints").lines == ("0002",)
    assert len(debugger.execute("history 2").lines) == 2
    assert debugger.execute("delete 2").lines == ("breakpoint removed from 0002",)


def test_disassembly_and_memory_wrap_and_remain_bounded() -> None:
    cpu, debugger = _debugger(bytes((0x3E, 0x2A, 0x00)))
    cpu.memory[0xFFFF] = 0x00

    assert debugger.execute("disasm 0 2").lines == (
        "0000  3E 2A        LD A, 0x2A",
        "0002  00           NOP",
    )
    assert debugger.execute("memory 0xffff 2").lines == ("FFFF  00 3E",)
    with pytest.raises(CommandError, match=r"range 0\.\.256"):
        debugger.execute("memory 0 257")


def test_commands_requiring_peek_fail_explicitly_when_capability_is_absent() -> None:
    cpu = MinimalZ80Host()
    debugger = CommandDebugger(DebugSession(cpu))

    with pytest.raises(CommandError, match="no side-effect-free peek"):
        debugger.execute("disassemble")


@pytest.mark.parametrize(
    "command",
    ("unknown", "step 0", "step 1 2", "run", "break 0x10000", "history -1"),
)
def test_invalid_commands_raise_command_errors(command: str) -> None:
    _cpu, debugger = _debugger()

    with pytest.raises(CommandError):
        debugger.execute(command)


def test_interactive_loop_reports_errors_and_exits_portably() -> None:
    _cpu, debugger = _debugger()
    output = StringIO()

    debugger.interact(StringIO("bad\nstep\nquit\n"), output, prompt="> ")

    rendered = output.getvalue()
    assert rendered.startswith("> error: unknown command: bad\n> #0 0000")
    assert rendered.endswith("\n> ")


def test_command_result_rejects_invalid_public_values() -> None:
    with pytest.raises(ValueError, match="tuple of strings"):
        CommandResult(["line"])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="bool"):
        CommandResult(quit=1)  # type: ignore[arg-type]
