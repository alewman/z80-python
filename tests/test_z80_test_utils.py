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
    real_case: dict,
) -> None:
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

    actual = run_test_case(real_case)
    final = real_case["final"]
    assert set(actual) == set(REGISTER_FIELDS) | {"ram"}
    assert actual["ram"] == final["ram"]
    for field in REGISTER_FIELDS:
        assert actual[field] == final[field], f"{field}: {actual[field]} != {final[field]}"
    # assert_state_equal tolerates the vector-only ei/p fields.
    assert_state_equal(final, actual)


# --- assert_state_equal ----------------------------------------------------


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
