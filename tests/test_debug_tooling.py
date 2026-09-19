"""Access tracking, watchpoints, the new console commands and ``python -m z80_python``.

The 0.4.0 tooling added to match m6800-python: every bus access a step makes
(memory and ports) recorded on its StepRecord, watchpoints that stop a run
after the step that touched a byte, the trace schema's optional ``accesses``,
and a command line that steps a binary without a host.
"""

import io
from contextlib import redirect_stdout

import pytest
from conftest import MemoryCPU

from z80_python import (
    BoundaryKind,
    CommandDebugger,
    CommandError,
    DebugSession,
    StopReason,
    compare_step_records,
    next_boundary,
    read_trace,
    step_record_from_dict,
    step_record_to_dict,
    write_trace,
)
from z80_python.__main__ import main

# LD HL,4000h; LD (HL),55h; LD A,(HL); OUT (12h),A; IN A,(34h); HALT
PROGRAM = bytes((0x21, 0x00, 0x40, 0x36, 0x55, 0x7E, 0xD3, 0x12, 0xDB, 0x34, 0x76))


def _session(**options) -> tuple[MemoryCPU, DebugSession]:
    cpu = MemoryCPU()
    cpu.memory[: len(PROGRAM)] = PROGRAM
    cpu.ports[0x5534] = 0x99  # IN A,(34h) reads port A:34h with A = 55h
    return cpu, DebugSession(cpu, peek_byte=cpu.memory.__getitem__, **options)


def test_tracked_steps_record_every_bus_access_in_order() -> None:
    _, session = _session(track_accesses=True)
    records = [session.step() for _ in range(5)]
    assert [record.accesses for record in records] == [
        (("r", 0x0000, 0x21), ("r", 0x0001, 0x00), ("r", 0x0002, 0x40)),
        (("r", 0x0003, 0x36), ("r", 0x0004, 0x55), ("w", 0x4000, 0x55)),
        (("r", 0x0005, 0x7E), ("r", 0x4000, 0x55)),
        (("r", 0x0006, 0xD3), ("r", 0x0007, 0x12), ("out", 0x5512, 0x55)),
        (("r", 0x0008, 0xDB), ("r", 0x0009, 0x34), ("in", 0x5534, 0x99)),
    ]


def test_untracked_steps_carry_no_accesses() -> None:
    _, session = _session()
    assert session.step().accesses is None
    assert not session.tracking


def test_close_gives_the_cpu_its_own_bus_back() -> None:
    cpu = MemoryCPU()
    originals = (cpu.read_byte, cpu.write_byte, cpu.read_port, cpu.write_port)
    session = DebugSession(cpu, track_accesses=True)
    assert cpu.read_byte is not originals[0]
    session.close()
    assert (cpu.read_byte, cpu.write_byte, cpu.read_port, cpu.write_port) == originals
    assert session.step().accesses is None


@pytest.mark.parametrize(
    ("kind", "stops_after"),
    [("w", 2), ("r", 3), ("rw", 2)],
)
def test_watchpoint_stops_after_the_step_that_touches_the_byte(kind: str, stops_after: int) -> None:
    _, session = _session(track_accesses=True)
    session.add_watchpoint(0x4000, kind)
    result = session.run(max_steps=100)
    assert result.reason is StopReason.WATCHPOINT
    assert result.steps == stops_after
    expected_access = ("w", 0x4000, 0x55) if stops_after == 2 else ("r", 0x4000, 0x55)
    assert result.hits == (expected_access,)


def test_watchpoints_need_tracking_and_a_valid_kind() -> None:
    _, session = _session()
    with pytest.raises(ValueError, match="track_accesses"):
        session.add_watchpoint(0x4000)
    _, tracked = _session(track_accesses=True)
    with pytest.raises(ValueError, match="kind"):
        tracked.add_watchpoint(0x4000, "x")
    tracked.add_watchpoint(0x4000)
    tracked.remove_watchpoint(0x4000)
    assert tracked.run(max_steps=100).reason is StopReason.HALTED


def test_next_boundary_is_public_and_matches_step() -> None:
    cpu, session = _session()
    assert next_boundary(cpu.capture_state()) is BoundaryKind.INSTRUCTION
    cpu.request_non_maskable_interrupt()
    assert next_boundary(cpu.capture_state()) is BoundaryKind.NON_MASKABLE_INTERRUPT
    assert session.step().kind is BoundaryKind.NON_MASKABLE_INTERRUPT


def test_trace_round_trips_accesses_and_omits_them_when_untracked() -> None:
    _, tracked = _session(track_accesses=True)
    _, plain = _session()
    with_accesses = tracked.step()
    without = plain.step()
    assert step_record_to_dict(with_accesses)["accesses"] == [
        ["r", 0, 0x21],
        ["r", 1, 0x00],
        ["r", 2, 0x40],
    ]
    assert "accesses" not in step_record_to_dict(without)
    stream = io.StringIO()
    write_trace([with_accesses, without], stream)
    stream.seek(0)
    assert list(read_trace(stream)) == [with_accesses, without]


def test_accesses_are_compared_only_when_both_records_carry_them() -> None:
    _, tracked = _session(track_accesses=True)
    _, plain = _session()
    with_accesses = tracked.step()
    without = plain.step()
    assert compare_step_records(with_accesses, without) == ()
    altered = step_record_to_dict(with_accesses)
    altered["accesses"][2][2] = 0x41
    differences = compare_step_records(with_accesses, step_record_from_dict(altered))
    assert [difference.path for difference in differences] == ["accesses"]


def test_malformed_accesses_are_rejected() -> None:
    _, tracked = _session(track_accesses=True)
    encoded = step_record_to_dict(tracked.step())
    encoded["accesses"] = [["x", 0, 0]]
    with pytest.raises(ValueError, match="accesses"):
        step_record_from_dict(encoded)


def test_console_watch_over_continue_set_and_interrupts() -> None:
    cpu, session = _session(track_accesses=True)
    debugger = CommandDebugger(session)
    assert debugger.execute("watch $4000 w").lines == ("watchpoint added at 4000 (w)",)
    assert debugger.execute("breakpoints").lines == ("watch 4000 w",)
    stopped = debugger.execute("c").lines[-1]
    assert stopped.startswith("stopped=watchpoint steps=2") and stopped.endswith("w 4000=55")
    debugger.execute("unwatch 0x4000")
    debugger.execute("set HL 0x1234")
    assert (cpu.h, cpu.l) == (0x12, 0x34)
    debugger.execute("set F $FF")
    assert cpu.f.byte == 0xFF
    with pytest.raises(CommandError, match="no register"):
        debugger.execute("set Q 1")
    debugger.execute("int 0xE7")
    assert cpu.maskable_interrupt_pending
    debugger.execute("int off")
    assert not cpu.maskable_interrupt_pending
    debugger.execute("nmi")
    assert cpu.non_maskable_interrupt_pending
    reset = debugger.execute("reset").lines
    assert reset[0].endswith("reset -> PC=0000 +3T")
    assert not cpu.reset_pending


def test_console_over_runs_a_call_through_and_steps_anything_else() -> None:
    cpu = MemoryCPU()
    # CALL 0010h; HALT ... at 0010h: INC A; RET
    cpu.memory[0:4] = bytes((0xCD, 0x10, 0x00, 0x76))
    cpu.memory[0x10:0x12] = bytes((0x3C, 0xC9))
    cpu.sp = 0x8000
    debugger = CommandDebugger(DebugSession(cpu, peek_byte=cpu.memory.__getitem__))
    lines = debugger.execute("over").lines
    assert lines[0].startswith("#0 0000  CD 10 00")
    assert (cpu.pc, cpu.sp, cpu.a) == (0x0003, 0x8000, 1)
    assert debugger.execute("o").lines == ("#3 0003  76           HALT -> PC=0004 +4T",)


def test_continue_steps_off_a_breakpoint_before_running() -> None:
    _, session = _session()
    debugger = CommandDebugger(session)
    debugger.execute("break 0")
    lines = debugger.execute("continue").lines
    assert lines[0].startswith("#0 0000  21 00 40")
    assert lines[1].startswith("stopped=halted")


def test_python_dash_m_loads_a_binary_and_runs_commands(tmp_path) -> None:
    image = tmp_path / "program.bin"
    image.write_bytes(PROGRAM)
    output = io.StringIO()
    with redirect_stdout(output):
        main(
            [
                "--load",
                f"{image}@0x100",
                "--pc",
                "0x100",
                "--batch",
                "-c",
                "step 2",
                "-c",
                "m 0x4000 1",
            ]
        )
    text = output.getvalue()
    assert "0100  21 00 40     LD HL, 0x4000" in text
    assert "#1 0103  36 55        LD (HL), 0x55 -> PC=0105 +10T" in text
    assert "4000  55" in text


def test_python_dash_m_rejects_an_image_that_does_not_fit(tmp_path) -> None:
    image = tmp_path / "big.bin"
    image.write_bytes(bytes(0x200))
    with pytest.raises(SystemExit, match="do not fit"):
        main(["--load", f"{image}@0xFF00", "--batch"])
