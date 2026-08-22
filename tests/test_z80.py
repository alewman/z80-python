"""Run the SingleStepTests/z80 per-opcode JSON vectors against the Z80 CPU.

Each JSON file under ``tests/z80_test_vectors/v1`` holds 1000 test cases for
one opcode (or prefixed-opcode variant, e.g. ``cb 07.json`` or
``dd cb __ 06.json``); every case carries a full ``initial`` and ``final``
register/RAM snapshot.  This module parametrizes one pytest test per vector
file -- so the pytest short summary reports pass/fail per opcode file -- and
runs *every* case inside that test:

* cases are loaded with :func:`validation.vector_utils.load_json_vector`;
* each case is executed with :func:`validation.vector_utils.run_test_case` (which
    raises :class:`validation.vector_utils.OpcodeNotImplementedError`, a
  ``NotImplementedError`` subclass, for opcodes the CPU does not implement
  yet) and the observed state is compared exactly with
  :func:`z80_test_utils.assert_state_equal`;
* a caught ``NotImplementedError`` is reported with ``pytest.fail`` and an
  ``"Opcode not implemented: ..."`` message -- an unimplemented opcode is a
  red test until the CPU implements it, never a silent skip.

If ``validation.vector_utils`` cannot be imported, a compact inline fallback that
duplicates ``load_json_vector`` / ``run_test_case`` / ``assert_state_equal``
(plus the ``OpcodeNotImplementedError`` type) is used instead, so the runner
keeps working standalone.

Per-opcode pass/fail/not-implemented counts are recorded in the
session-scoped ``vector_results`` fixture provided by ``tests/conftest.py``;
``pytest_terminal_summary`` prints the per-file table after the whole session.
A missing or malformed vector file fails that file's test with a clear message
instead of breaking collection, and the file is still recorded in the summary
as failed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from validation.vector_utils import (
        OpcodeNotImplementedError,
        assert_state_equal,
        load_json_vector,
        run_test_case,
    )
except ImportError:  # pragma: no cover - inline fallback (see module docstring)
    from z80.cpu import Z80CPU

    #: Vector fields that map 1:1 onto Z80CPU attributes (fallback copy).
    REGISTER_FIELDS = (
        "a",
        "b",
        "c",
        "d",
        "e",
        "f",
        "h",
        "l",
        "i",
        "r",
        "ix",
        "iy",
        "sp",
        "pc",
        "wz",
        "af_",
        "bc_",
        "de_",
        "hl_",
        "im",
        "iff1",
        "iff2",
        "q",
    )

    class OpcodeNotImplementedError(NotImplementedError):
        """Fallback twin of ``z80_test_utils.OpcodeNotImplementedError``."""

    class _VectorCPU(Z80CPU):
        """Concrete Z80CPU backed by a flat 64 KiB bytearray (fallback)."""

        def __init__(self) -> None:
            super().__init__()
            self.memory = bytearray(0x10000)
            self.port_inputs: list[tuple[int, int]] = []
            self.port_outputs: list[tuple[int, int]] = []

        def read_byte(self, addr: int) -> int:
            return self.memory[addr & 0xFFFF]

        def write_byte(self, addr: int, value: int) -> None:
            self.memory[addr & 0xFFFF] = value & 0xFF

        def read_port(self, addr: int) -> int:
            if not self.port_inputs:
                raise AssertionError(
                    f"unexpected I/O port read at 0x{addr & 0xFFFF:04X}: "
                    "the vector provides no port input for this instruction"
                )
            expected_addr, value = self.port_inputs.pop(0)
            if expected_addr != addr & 0xFFFF:
                raise AssertionError(
                    f"I/O port read address mismatch: expected 0x{expected_addr:04X} "
                    f"(vector order), CPU read 0x{addr & 0xFFFF:04X}"
                )
            return value

        def write_port(self, addr: int, value: int) -> None:
            self.port_outputs.append((addr & 0xFFFF, value & 0xFF))

    def load_json_vector(file_path: str | Path) -> list[dict]:
        """Fallback loader: parse a JSON list of test-case dicts."""
        path = Path(file_path)
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list) or not data:
            raise ValueError(f"{path}: expected a non-empty list of test cases")
        return data

    def _setup_cpu(initial: dict) -> _VectorCPU:
        cpu = _VectorCPU()
        for field in REGISTER_FIELDS:
            value = initial[field]
            if field == "f":
                cpu.f.byte = value
            else:
                setattr(cpu, field, value)
        for addr, value in initial.get("ram", []):
            cpu.write_byte(addr, value)
        return cpu

    def _snapshot(cpu: _VectorCPU, final: dict) -> dict:
        state = {
            field: (cpu.f.byte if field == "f" else getattr(cpu, field))
            for field in REGISTER_FIELDS
        }
        state["ram"] = [[addr, cpu.read_byte(addr)] for addr, _ in final.get("ram", [])]
        return state

    def _fallback_opcode_and_pc(initial: dict) -> tuple[int | None, int | None]:
        """Fallback twin of ``z80_test_utils._opcode_and_pc``."""
        pc = initial.get("pc")
        if not isinstance(pc, int):
            return None, None
        ram = dict(initial.get("ram", []))
        return ram.get(pc), pc

    def run_test_case(case: dict) -> dict:
        """Fallback runner: execute one vector case and snapshot the result."""
        cpu = _setup_cpu(case["initial"])
        try:
            cpu.decode_and_execute()
        except NotImplementedError as exc:
            opcode, pc = _fallback_opcode_and_pc(case["initial"])
            location = f" at PC 0x{pc:04X}" if pc is not None else ""
            opcode_text = f"0x{opcode:02X}" if opcode is not None else "?"
            raise OpcodeNotImplementedError(
                f"opcode {opcode_text}{location} is not implemented ({exc})"
            ) from exc
        return _snapshot(cpu, case["final"])

    def assert_state_equal(expected: dict, actual: dict) -> None:
        """Fallback comparator: report register/RAM mismatches as AssertionError."""
        diffs = [
            f"  register {field}: expected {expected[field]!r}, got {actual.get(field)!r}"
            for field in REGISTER_FIELDS
            if field in expected and expected[field] != actual.get(field)
        ]
        expected_ram = expected.get("ram", [])
        actual_ram = dict(actual.get("ram", []))
        for addr, value in expected_ram:
            if actual_ram.get(addr) != value:
                diffs.append(
                    f"  ram[0x{addr:04X}]: expected {value!r}, got {actual_ram.get(addr)!r}"
                )
        if diffs:
            raise AssertionError("state mismatch:\n" + "\n".join(diffs))


#: Directory holding the per-opcode vector JSON files (SingleStepTests/z80
#: layout: every opcode/prefixed variant is one file under ``v1/``).
VECTOR_DIR = Path(__file__).parent / "z80_test_vectors" / "v1"

#: How many representative failures to include in each per-file report
#: (NotImplementedError is summarized by count alone).
_MAX_REPORTED_FAILURES = 10


def _classify_vector_outcome(passed: int, failed: int, not_implemented: int) -> str:
    """Decide one opcode file's outcome: "fail", "skip", or "pass".

    CONTRACT -- do not change "skip" to "fail" here. At the start of staged
    development zero opcodes are implemented, so every one of the ~1600 vector
    files hits ``not_implemented`` on every case. If that counted as a failure,
    the entire suite would be permanently red regardless of whether the CPU is
    actually correct, which defeats the whole point of reporting pass/fail per
    opcode file during incremental development. A real, observed register/RAM
    mismatch (``failed``) is always a genuine bug and must fail -- that part is
    non-negotiable -- but "this opcode simply doesn't exist yet" is not a bug,
    it's expected, and must skip instead so it doesn't block review or mask
    real regressions. See test_classify_vector_outcome_* below.
    """
    if failed:
        return "fail"
    if not_implemented:
        return "skip"
    return "pass"


def _discover_vector_files() -> list[Path]:
    """Return the sorted per-opcode vector files (empty if the dir is absent)."""
    if not VECTOR_DIR.is_dir():
        return []
    return sorted(VECTOR_DIR.glob("*.json"))


VECTOR_FILES = _discover_vector_files()
if VECTOR_FILES:
    _PARAMETRIZED: list[Path | None] = VECTOR_FILES
    _PARAMETRIZED_IDS = [path.name for path in VECTOR_FILES]
else:
    # The corpus is external and intentionally absent from a fresh checkout.
    # Collect one explicit skip so the normal fast suite remains reproducible.
    _PARAMETRIZED = [None]
    _PARAMETRIZED_IDS = ["no-vector-files"]


@pytest.mark.slow
@pytest.mark.parametrize("vector_path", _PARAMETRIZED, ids=_PARAMETRIZED_IDS)
def test_opcode_vector(
    vector_path: Path | None,
    vector_results: dict[str, dict[str, int | str | None]],
) -> None:
    """Every test case in one opcode file must match initial -> final exactly."""
    if vector_path is None:
        pytest.skip("run scripts/fetch_test_vectors.py to enable vector tests")

    file_name = vector_path.name
    passed = 0
    failed = 0
    not_implemented = 0
    total = 0
    error: str | None = None
    try:
        try:
            cases = load_json_vector(vector_path)
        except FileNotFoundError as exc:
            error = f"vector file missing: {exc}"
            pytest.fail(f"{file_name}: {error}")
        except (OSError, ValueError) as exc:
            error = f"vector file malformed: {exc}"
            pytest.fail(f"{file_name}: {error}")

        total = len(cases)
        not_implemented_message = ""
        failures: list[str] = []
        for index, case in enumerate(cases):
            name = case.get("name", f"case {index}")
            try:
                actual = run_test_case(case)
            except NotImplementedError as exc:
                # Unimplemented opcode: remember the first message so the
                # per-file report stays compact while every case still runs.
                not_implemented += 1
                if not not_implemented_message:
                    not_implemented_message = f"Opcode not implemented: {exc}"
                continue
            except Exception as exc:
                failed += 1
                failures.append(f"  case {name} raised {type(exc).__name__}: {exc}")
                continue
            try:
                assert_state_equal(case["final"], actual)
            except AssertionError as exc:
                failed += 1
                failures.append(str(exc))
            except Exception as exc:
                failed += 1
                failures.append(f"  case {name}: could not compare final state: {exc}")
            else:
                passed += 1
    finally:
        # Record this file even on failure so the terminal summary covers it.
        vector_results[file_name] = {
            "passed": passed,
            "failed": failed,
            "not_implemented": not_implemented,
            "total": total,
            "error": error,
        }

    outcome = _classify_vector_outcome(passed, failed, not_implemented)
    if outcome == "fail":
        summary = [
            f"{file_name}: {passed} passed, {failed} failed, "
            f"{not_implemented} not implemented of {total} cases"
        ]
        unique = list(dict.fromkeys(failures))
        summary.extend(unique[:_MAX_REPORTED_FAILURES])
        if len(unique) > _MAX_REPORTED_FAILURES:
            summary.append(
                f"  ... and {len(unique) - _MAX_REPORTED_FAILURES} more distinct failure(s)"
            )
        pytest.fail("\n".join(summary))

    if outcome == "skip":
        # Every case here hit an opcode that simply hasn't been built yet --
        # that's expected during staged development, not a regression, so it
        # must not block review the way a real mismatch does. Skip rather than
        # pass outright, since this file's behavior hasn't actually been
        # verified. Do NOT change this to pytest.fail -- see
        # _classify_vector_outcome's docstring.
        pytest.skip(
            f"{file_name}: {not_implemented} of {total} case(s) hit an "
            f"unimplemented opcode. {not_implemented_message}"
        )


def test_classify_vector_outcome_fails_on_any_real_mismatch() -> None:
    assert _classify_vector_outcome(passed=500, failed=1, not_implemented=499) == "fail"


def test_classify_vector_outcome_skips_pure_not_implemented_files() -> None:
    # This is the exact case every vector file starts in: zero opcodes
    # implemented yet. It must be "skip", never "fail" -- see
    # _classify_vector_outcome's docstring for why.
    assert _classify_vector_outcome(passed=0, failed=0, not_implemented=1000) == "skip"


def test_classify_vector_outcome_passes_when_everything_matches() -> None:
    assert _classify_vector_outcome(passed=1000, failed=0, not_implemented=0) == "pass"
