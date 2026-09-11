"""Unit tests for the SingleStepTests/z80 vector test utilities.

Covers the four validation-only helpers in ``validation/vector_utils.py``
(``load_json_vector``, ``setup_cpu``, ``run_test_case``,
``assert_state_equal``) plus the ``OpcodeNotImplementedError`` conversion and
the module's embedded-sample self-test main guard.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from validation.vector_utils import (
    REGISTER_FIELDS,
    OpcodeNotImplementedError,
    VectorCPU,
    _main,
    assert_state_equal,
    expected_memory_transactions,
    expected_state,
    load_json_vector,
    run_test_case,
    setup_cpu,
)

VECTOR_DIR = Path(__file__).parent / "z80_test_vectors" / "v1"


@pytest.fixture(scope="module")
def real_cases() -> list[dict]:
    """The 1000 real NOP test cases from the locally cached vector set."""
    if not VECTOR_DIR.is_dir():
        pytest.skip("run scripts/fetch_test_vectors.py to enable vector tests")
    return load_json_vector(VECTOR_DIR / "00.json")


@pytest.fixture()
def real_case(real_cases: list[dict]) -> dict:
    return real_cases[0]


def _write_json(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "vector.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --- load_json_vector ------------------------------------------------------


def test_load_json_vector_returns_all_cases(real_cases: list[dict]) -> None:
    assert len(real_cases) == 1000
    for case in real_cases[:5]:
        assert {"name", "initial", "final"} <= set(case)
        assert isinstance(case["initial"]["ram"], list)
        assert isinstance(case["final"]["ram"], list)


def test_load_json_vector_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        load_json_vector(tmp_path / "missing.json")


def test_load_json_vector_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "vector.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_json_vector(path)


def test_load_json_vector_empty_list_raises(tmp_path: Path) -> None:
    path = _write_json(tmp_path, [])
    with pytest.raises(ValueError, match="non-empty"):
        load_json_vector(path)


def test_load_json_vector_case_missing_register_field_raises(
    tmp_path: Path, real_case: dict
) -> None:
    case = copy.deepcopy(real_case)
    del case["initial"]["wz"]
    path = _write_json(tmp_path, [case])
    with pytest.raises(ValueError, match="wz"):
        load_json_vector(path)


def test_load_json_vector_malformed_ram_entry_raises(tmp_path: Path, real_case: dict) -> None:
    case = copy.deepcopy(real_case)
    case["initial"]["ram"] = [[case["initial"]["pc"]]]  # missing value
    path = _write_json(tmp_path, [case])
    with pytest.raises(ValueError, match="RAM entry"):
        load_json_vector(path)


def test_load_json_vector_missing_ram_list_raises(tmp_path: Path, real_case: dict) -> None:
    case = copy.deepcopy(real_case)
    del case["initial"]["ram"]
    path = _write_json(tmp_path, [case])
    with pytest.raises(ValueError, match="'ram' list"):
        load_json_vector(path)


# --- setup_cpu -------------------------------------------------------------


def test_setup_cpu_sets_registers_and_ram(real_case: dict) -> None:
    cpu = setup_cpu(real_case["initial"])
    initial = real_case["initial"]
    assert cpu.pc == initial["pc"]
    assert cpu.sp == initial["sp"]
    assert cpu.a == initial["a"]
    assert cpu.f.byte == initial["f"]
    assert cpu.wz == initial["wz"]
    assert cpu.af_ == initial["af_"]
    assert cpu.q == initial["q"]
    for addr, value in initial["ram"]:
        assert cpu.read_byte(addr) == value


def test_setup_cpu_requires_all_register_fields(real_case: dict) -> None:
    initial = copy.deepcopy(real_case["initial"])
    del initial["hl_"]
    with pytest.raises(ValueError, match="hl_"):
        setup_cpu(initial)


def test_setup_cpu_rejects_malformed_ram(real_case: dict) -> None:
    initial = copy.deepcopy(real_case["initial"])
    initial["ram"] = [["0x100", 0x00]]  # addr must be an int
    with pytest.raises(ValueError, match="RAM entry"):
        setup_cpu(initial)


def test_setup_cpu_rejects_non_dict() -> None:
    with pytest.raises(TypeError, match="dict"):
        setup_cpu("not a dict")  # type: ignore[arg-type]


# --- run_test_case ---------------------------------------------------------


def test_run_test_case_raises_custom_exception_for_unimplemented_opcode(
    monkeypatch: pytest.MonkeyPatch, real_case: dict
) -> None:
    """This core implements every opcode, so the condition is staged: a port's
    unfinished core raising ``NotImplementedError`` must surface as the named
    exception carrying the opcode and PC read from the vector."""

    def unfinished_decode(self: VectorCPU) -> int:
        raise NotImplementedError(f"unhandled opcode 0xDD at PC 0x{self.pc:04X}")

    monkeypatch.setattr(VectorCPU, "decode_and_execute", unfinished_decode)
    unsupported_case = {
        "initial": {
            **real_case["initial"],
            "ram": [
                [real_case["initial"]["pc"], 0xDD],
                [(real_case["initial"]["pc"] + 1) & 0xFFFF, 0xED],
            ],
        },
        "final": real_case["final"],
    }
    with pytest.raises(OpcodeNotImplementedError) as excinfo:
        run_test_case(unsupported_case)
    exc = excinfo.value
    assert exc.opcode == 0xDD
    assert exc.pc == real_case["initial"]["pc"]
    assert "not implemented" in str(exc)
    assert "0xDD" in str(exc)


def test_run_test_case_returns_vector_shaped_final_state(
    monkeypatch: pytest.MonkeyPatch, real_case: dict
) -> None:
    """With a working decode, run_test_case must reproduce the vector final exactly."""

    def fake_decode_and_execute(self: VectorCPU) -> int:
        self.pc = (self.pc + 1) & 0xFFFF
        self._inc_r()
        self._update_q(False)
        return 4

    monkeypatch.setattr(VectorCPU, "decode_and_execute", fake_decode_and_execute)

    # The stub performs no memory access, so its empty bus log says nothing
    # about the real core; this test is about run_test_case's return shape.
    actual = run_test_case(real_case, verify_memory_bus=False)
    final = real_case["final"]
    assert set(actual) == set(REGISTER_FIELDS) | {"ram", "t_states"}
    assert actual["ram"] == final["ram"]
    assert actual["t_states"] == 4, "run_test_case must report what step() returned"
    for field in REGISTER_FIELDS:
        assert actual[field] == final[field], f"{field}: {actual[field]} != {final[field]}"
    # assert_state_equal tolerates the vector-only ei/p fields.
    assert_state_equal(final, actual)


# --- assert_state_equal ----------------------------------------------------


def test_expected_state_adds_t_states_from_cycles(real_case: dict) -> None:
    """One SingleStepTests ``cycles`` entry per T-state; no array, no expectation."""
    expected = expected_state(real_case)
    assert expected["t_states"] == len(real_case["cycles"])
    assert expected["t_states"] > 0
    untimed = {key: value for key, value in real_case.items() if key != "cycles"}
    assert "t_states" not in expected_state(untimed)


def test_assert_state_equal_reports_t_state_mismatch(real_case: dict) -> None:
    expected = expected_state(real_case)
    actual = {**real_case["final"], "t_states": expected["t_states"] + 1}
    with pytest.raises(AssertionError, match="t_states: expected"):
        assert_state_equal(expected, actual)
    assert_state_equal(expected, {**real_case["final"], "t_states": expected["t_states"]})


def test_assert_state_equal_passes_for_equal_states(real_case: dict) -> None:
    assert_state_equal(real_case["final"], real_case["final"])  # must not raise


def test_assert_state_equal_reports_register_mismatch(real_case: dict) -> None:
    broken = dict(real_case["final"])
    broken["a"] = 0x00
    with pytest.raises(AssertionError, match="register a"):
        assert_state_equal(real_case["final"], broken)


def test_assert_state_equal_reports_ram_mismatch_and_unexpected_address(
    real_case: dict,
) -> None:
    broken = dict(real_case["final"])
    broken["ram"] = [[real_case["final"]["pc"] - 1, 0xFF], [0x9999, 0x42]]
    with pytest.raises(AssertionError) as excinfo:
        assert_state_equal(real_case["final"], broken)
    message = str(excinfo.value)
    assert "ram[0x" in message
    assert "0x9999" in message
    assert "unexpected" in message


# --- embedded self-test ----------------------------------------------------


def test_main_guard_self_test_runs() -> None:
    _main()  # raises AssertionError if any embedded-sample check fails


# --- memory bus transactions ------------------------------------------------


def test_expected_memory_transactions_reads_latch_on_the_following_cycle() -> None:
    """A read asserts ``r-m-``; its data byte appears on the next cycle entry."""
    case = {
        "cycles": [
            [0x1000, None, "----"],
            [0x1000, None, "r-m-"],
            [0x4D2A, 0x3E, "----"],
        ]
    }
    assert expected_memory_transactions(case) == [("MR", 0x1000, 0x3E)]


def test_expected_memory_transactions_writes_carry_their_value_inline() -> None:
    case = {"cycles": [[0x8001, 0xD7, "-wm-"], [0x8000, 0x49, "-wm-"]]}
    assert expected_memory_transactions(case) == [
        ("MW", 0x8001, 0xD7),
        ("MW", 0x8000, 0x49),
    ]


def test_expected_memory_transactions_skips_internal_and_refresh_cycles() -> None:
    """Idle cycles and the M1 ``I << 8 | R`` refresh address carry no strobe."""
    case = {"cycles": [[0x0000, None, "----"], [0x3D74, 0x7E, "----"]]}
    assert expected_memory_transactions(case) == []


def test_expected_memory_transactions_ignores_port_strobes() -> None:
    """Port order is already checked by VectorCPU's port_inputs/port_outputs."""
    case = {"cycles": [[0x00FE, None, "r--i"], [0x00FE, 0xBF, "----"]]}
    assert expected_memory_transactions(case) == []


def test_expected_memory_transactions_without_cycles_returns_none() -> None:
    assert expected_memory_transactions({"final": {}}) is None


def test_run_test_case_detects_reordered_memory_writes(
    monkeypatch: pytest.MonkeyPatch, real_case: dict
) -> None:
    """A core whose writes land in the wrong order must fail, even though the
    resulting memory is identical and no state comparison can see it."""

    def swapped_writes(self: VectorCPU) -> int:
        self.pc = (self.pc + 1) & 0xFFFF
        self._inc_r()
        self._update_q(False)
        self.write_byte(0x9001, 0xD7)
        self.write_byte(0x9000, 0x49)
        return 4

    monkeypatch.setattr(VectorCPU, "decode_and_execute", swapped_writes)
    case = copy.deepcopy(real_case)
    case["cycles"] = [[0x9000, 0x49, "-wm-"], [0x9001, 0xD7, "-wm-"]]
    with pytest.raises(AssertionError, match="memory bus transaction mismatch"):
        run_test_case(case)
