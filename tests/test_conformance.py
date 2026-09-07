"""The conformance kit: manifests, the shared host, reference traces, and the differ."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from z80_python import BoundaryKind, CPUState, read_trace, step_record_to_dict, write_trace
from z80_python.conformance import (
    Event,
    Manifest,
    MemorySegment,
    StopRule,
    diff_manifest,
    load_manifest,
    main,
    manifest_from_dict,
    manifest_to_dict,
    trace_manifest,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "conformance"


def _manifest(program: bytes, **overrides: object) -> Manifest:
    values: dict[str, object] = {
        "name": "unit",
        "memory": (MemorySegment(0, program),),
        "initial": CPUState(sp=0xFFFF),
        "stop": StopRule(max_steps=50),
    }
    values.update(overrides)
    return Manifest(**values)  # type: ignore[arg-type]


# --- manifests ---------------------------------------------------------------


def test_manifest_round_trips_through_its_json_form() -> None:
    manifest = _manifest(
        bytes((0x00, 0x76)),
        events=(Event(1, "int", 0xC7), Event(3, "nmi")),
        stop=StopRule(max_steps=9, on_halt=False, at_pc=(0x0002,)),
        host="cpm-minimal",
        port_read_value=0x12,
    )
    encoded = json.loads(json.dumps(manifest_to_dict(manifest)))
    assert manifest_from_dict(encoded) == manifest


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda d: d.update(version=2), "unsupported manifest version"),
        (lambda d: d.update(host="spectrum"), "host must be one of"),
        (lambda d: d["stop"].pop("max_steps"), "missing=\\['max_steps'\\]"),
        (
            lambda d: d.update(
                events=[{"at_step": 5, "kind": "nmi"}, {"at_step": 1, "kind": "nmi"}]
            ),
            "ordered",
        ),
        (lambda d: d["memory"].append({"address": 0xFFFF, "data": "0000"}), "does not fit"),
        (lambda d: d["memory"].append({"address": 0}), "exactly one of"),
        (lambda d: d.update(initial={"pc": 0x10000}), "invalid initial state"),
        (lambda d: d.update(bogus=1), "unknown=\\['bogus'\\]"),
    ),
)
def test_manifest_rejects_malformed_input(mutation, message: str) -> None:
    encoded = manifest_to_dict(_manifest(bytes((0x76,))))
    mutation(encoded)
    with pytest.raises(ValueError, match=message):
        manifest_from_dict(encoded)


def test_file_segments_resolve_relative_to_the_manifest(tmp_path: Path) -> None:
    (tmp_path / "rom.bin").write_bytes(bytes((0xAA, 0x3C, 0x76, 0xBB)))
    (tmp_path / "m.json").write_text(
        json.dumps(
            {
                "version": 1,
                "name": "file",
                "memory": [{"address": 0x100, "file": "rom.bin", "offset": 1, "length": 2}],
                "initial": {"pc": 0x100},
                "stop": {"max_steps": 5},
            }
        )
    )
    manifest = load_manifest(tmp_path / "m.json")
    assert manifest.memory == (MemorySegment(0x100, bytes((0x3C, 0x76))),)
    records = list(trace_manifest(manifest))
    assert [r.instruction.mnemonic for r in records] == ["INC", "HALT"]


# --- reference traces ----------------------------------------------------------


def test_trace_stops_on_halt_and_reports_why() -> None:
    result = []
    records = list(trace_manifest(_manifest(bytes((0x3E, 0x2A, 0x3C, 0x76))), result=result))
    assert [r.instruction.text for r in records] == ["LD A, 0x2A", "INC A", "HALT"]
    assert records[-1].after.a == 0x2B and records[-1].after.halted
    assert result[0].reason == "halted" and result[0].steps == 3 and result[0].t_states == 15


def test_trace_honours_step_budget_and_pc_stops() -> None:
    loop = bytes((0x00, 0xC3, 0x00, 0x00))  # NOP; JP 0
    result = []
    assert (
        len(list(trace_manifest(_manifest(loop, stop=StopRule(max_steps=7)), result=result))) == 7
    )
    assert result[0].reason == "max_steps"
    result = []
    records = list(
        trace_manifest(_manifest(loop, stop=StopRule(max_steps=7, at_pc=(1,))), result=result)
    )
    assert len(records) == 1 and result[0].reason == "at_pc"


def test_halt_does_not_stop_the_run_while_an_event_is_still_due() -> None:
    manifest = _manifest(bytes((0x76,)), events=(Event(3, "nmi"),), stop=StopRule(max_steps=10))
    kinds = [r.kind for r in trace_manifest(manifest)]
    assert kinds[0] is BoundaryKind.INSTRUCTION  # HALT
    assert kinds[1:3] == [BoundaryKind.HALT_IDLE, BoundaryKind.HALT_IDLE]
    assert kinds[3] is BoundaryKind.NON_MASKABLE_INTERRUPT
    assert kinds[4] is BoundaryKind.INSTRUCTION  # code at 0x0066 (zero = NOP)


def test_events_reach_the_core_through_the_lifecycle_api() -> None:
    manifest = _manifest(
        bytes((0xFB, 0x00, 0x00, 0x00, 0x76)),  # EI; NOP; NOP; NOP; HALT
        events=(Event(1, "int", 0xFF), Event(4, "reset"), Event(5, "reset_clear")),
        stop=StopRule(max_steps=8, on_halt=False),
    )
    records = list(trace_manifest(manifest))
    kinds = [r.kind for r in records]
    # EI, NOP (delay), accept INT (IM 0 RST 38h), then whatever is at 0x38, then RESET.
    assert kinds[:3] == [BoundaryKind.INSTRUCTION] * 2 + [BoundaryKind.MASKABLE_INTERRUPT]
    assert records[2].after.pc == 0x0038 and records[2].t_states == 13
    assert kinds[4] is BoundaryKind.RESET and records[4].after.pc == 0
    assert records[4].after.reset_pending is True and records[5].before.reset_pending is False


def test_cpm_minimal_traps_produce_output_and_no_records() -> None:
    program = (
        bytes(
            (
                0x0E,
                0x02,
                0x1E,
                0x41,
                0xCD,
                0x05,
                0x00,  # LD C,2; LD E,'A'; CALL 5
                0x0E,
                0x09,
                0x11,
                0x14,
                0x01,
                0xCD,
                0x05,
                0x00,  # LD C,9; LD DE,msg; CALL 5
                0x0E,
                0x00,
                0xCD,
                0x05,
                0x00,  # LD C,0; CALL 5  (exit)
            )
        )
        + b"BC$"
    )
    manifest = Manifest(
        name="cpm",
        memory=(MemorySegment(0x100, program),),
        initial=CPUState(pc=0x100, sp=0xF000),
        stop=StopRule(max_steps=50),
        host="cpm-minimal",
    )
    result = []
    records = list(trace_manifest(manifest, result=result))
    assert result[0].output == b"ABC" and result[0].reason == "cpm_exit"
    # Every record is an instruction the program executed; the traps are invisible.
    assert all(r.kind is BoundaryKind.INSTRUCTION for r in records)
    assert [r.instruction.mnemonic for r in records].count("CALL") == 3
    assert records[-1].instruction.address == 0x100 + 0x11  # the final CALL 5


# --- diffing -------------------------------------------------------------------


def test_reference_trace_diffs_clean_against_itself_even_without_text() -> None:
    manifest = load_manifest(EXAMPLES / "flags-and-branches.json")
    stream = io.StringIO()
    write_trace(trace_manifest(manifest), stream)
    stripped = io.StringIO()
    for line in stream.getvalue().splitlines():
        record = json.loads(line)
        if record["instruction"] is not None:
            record["instruction"] = {k: record["instruction"][k] for k in ("address", "data")}
        stripped.write(json.dumps(record) + "\n")
    stripped.seek(0)
    assert diff_manifest(manifest, read_trace(stripped)) is None


def test_diff_reports_the_first_wrong_field_and_stops_there() -> None:
    manifest = load_manifest(EXAMPLES / "flags-and-branches.json")
    records = list(trace_manifest(manifest))
    broken = [step_record_to_dict(r) for r in records]
    broken[5]["after"]["f"] ^= 0x08  # flip X on the sixth record
    broken[9]["t_states"] += 1  # a later error must not be reported first
    stream = io.StringIO("".join(json.dumps(r) + "\n" for r in broken))
    divergence = diff_manifest(manifest, read_trace(stream))
    assert divergence is not None and divergence.position == 5
    assert [d.path for d in divergence.differences] == ["after.f"]


def test_diff_reports_a_truncated_external_trace() -> None:
    manifest = load_manifest(EXAMPLES / "flags-and-branches.json")
    records = list(trace_manifest(manifest))
    stream = io.StringIO("".join(json.dumps(step_record_to_dict(r)) + "\n" for r in records[:-1]))
    divergence = diff_manifest(manifest, read_trace(stream))
    assert divergence is not None and divergence.position == len(records) - 1
    assert divergence.differences[0].path == "record"


# --- golden fixtures and the command line ---------------------------------------


@pytest.mark.parametrize("name", ("flags-and-branches", "interrupts"))
def test_committed_reference_traces_match_a_fresh_run(name: str) -> None:
    """The .jsonl beside each manifest is the reference trace; a change here is a core change."""
    manifest = load_manifest(EXAMPLES / f"{name}.json")
    with (EXAMPLES / f"{name}.jsonl").open(encoding="utf-8") as handle:
        assert diff_manifest(manifest, read_trace(handle)) is None


def test_cli_trace_then_diff(tmp_path: Path) -> None:
    manifest = str(EXAMPLES / "interrupts.json")
    out = io.StringIO()
    assert main(["trace", manifest, "--out", str(tmp_path / "t.jsonl")], stdout=out) == 0
    assert "stopped on halted" in out.getvalue()
    out = io.StringIO()
    assert main(["diff", manifest, str(tmp_path / "t.jsonl")], stdout=out) == 0
    assert "identical" in out.getvalue()

    lines = (tmp_path / "t.jsonl").read_text().splitlines()
    record = json.loads(lines[3])
    record["t_states"] += 6
    lines[3] = json.dumps(record)
    (tmp_path / "bad.jsonl").write_text("\n".join(lines) + "\n")
    out = io.StringIO()
    assert main(["diff", manifest, str(tmp_path / "bad.jsonl")], stdout=out) == 1
    assert "position 3" in out.getvalue() and "t_states: reference=13 external=19" in out.getvalue()

    out = io.StringIO()
    assert main(["diff", str(tmp_path / "missing.json"), "-"], stdout=out) == 2
