"""Core test logic for running a SingleStepTests/z80 JSON vector file.

The SingleStepTests/z80 project (https://github.com/SingleStepTests/z80) ships
one JSON file per opcode (or prefixed-opcode variant); each file holds 1000
test cases carrying a full ``initial`` and ``final`` register/RAM snapshot.
This module provides the plumbing to run one such file against the
:class:`z80_python.cpu.Z80CPU` core:

* :func:`load_json_vector` -- parse a vector file into a list of case dicts.
* :func:`setup_cpu` -- instantiate a CPU and load an ``initial`` snapshot.
* :func:`run_test_case` -- execute one instruction and snapshot the result.
* :func:`assert_state_equal` -- compare two snapshots with readable diffs.
* :func:`expected_state` -- the vector ``final`` snapshot plus the T-state
  total encoded by the case's ``cycles`` array, in the shape
  :func:`run_test_case` returns.

Timing is verified as well as state: every SingleStepTests case carries a
``cycles`` array with exactly one ``[address, data, pins]`` entry per T-state
the oracle spent on the instruction.  Its length is therefore the expected
return value of :meth:`Z80CPU.step` for that case, which pins down
conditional-branch timing (``JR cc,e`` taken vs. not taken), block-repeat
timing (``LDIR`` 21 vs. 16), and the extra M1 cost of every prefix.

I/O vectors additionally carry a top-level ``ports`` array (``[addr, value,
direction]`` entries).  :func:`run_test_case` feeds the ``"r"`` entries into
:class:`VectorCPU` as port inputs and verifies the CPU's port writes against
the ``"w"`` entries, so the input/output opcode group is validated end to end
through the same per-opcode vector files.

The helpers are deliberately single-file/single-case focused so a test runner
can loop over files and cases itself.  ``NotImplementedError`` raised by
``decode_and_execute`` is converted into :class:`OpcodeNotImplementedError`
so unimplemented opcodes surface as a named, inspectable condition instead of
leaking through as a raw stub error.

The module doubles as a runnable self-test: ``python validation/vector_utils.py``
exercises every helper against a tiny embedded JSON sample (see ``_main``).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from z80_python.cpu import Z80CPU

__all__ = [
    "REGISTER_FIELDS",
    "OpcodeNotImplementedError",
    "VectorCPU",
    "assert_state_equal",
    "expected_state",
    "load_json_vector",
    "run_test_case",
    "setup_cpu",
]

# How many differences are shown per assert_state_equal failure before the
# report is truncated with a "... and N more" note.
_MAX_REPORTED_DIFFS = 25

# Vector fields that map 1:1 onto Z80CPU attributes.  The generator's ``ei``
# ("EI was the last-emulated instruction") and ``p`` ("CMOS interrupt
# bookkeeping") fields are documented in z80_test_generator.js as ignorable
# and have no counterpart on Z80CPU, so they are excluded from the exact-state
# comparison.
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


class VectorCPU(Z80CPU):
    """Concrete Z80CPU backed by a flat 64 KiB bytearray for vector runs.

    I/O ports are driven from the SingleStepTests vector ``ports`` arrays:
    :meth:`read_port` consumes ``(addr, value)`` inputs in the order the
    oracle performed them (raising if the address does not match or no input
    remains), and :meth:`write_port` records every write so
    :func:`run_test_case` can compare them against the expected outputs.
    """

    def __init__(self) -> None:
        super().__init__()
        self.memory = bytearray(0x10000)
        #: Queue of ``(addr, value)`` port reads supplied by the vector.
        self.port_inputs: list[tuple[int, int]] = []
        #: Recorded ``(addr, value)`` port writes, in execution order.
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


class OpcodeNotImplementedError(NotImplementedError):
    """Raised by :func:`run_test_case` for an opcode the CPU does not implement.

    Subclasses ``NotImplementedError`` so existing handlers that treat
    unimplemented opcodes as a known, countable condition keep working, while
    callers can still catch this specific type.  The ``opcode`` and ``pc``
    attributes carry the failing instruction when it could be determined from
    the vector ``initial`` state.
    """

    def __init__(
        self,
        message: str,
        *,
        opcode: int | None = None,
        pc: int | None = None,
    ) -> None:
        super().__init__(message)
        self.opcode = opcode
        self.pc = pc


def _ram_pairs(ram: object) -> list[tuple[int, int]]:
    """Validate a vector ``ram`` list and return it as ``(addr, value)`` pairs."""
    if not isinstance(ram, list):
        raise ValueError(f"'ram' must be a list of [addr, value] pairs, got {type(ram).__name__}")
    pairs: list[tuple[int, int]] = []
    for entry in ram:
        try:
            addr, value = entry
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid RAM entry {entry!r}: expected a [addr, value] pair") from exc
        if not isinstance(addr, int) or not isinstance(value, int):
            raise ValueError(f"invalid RAM entry {entry!r}: addr and value must be ints")
        pairs.append((addr, value))
    return pairs


def load_json_vector(file_path: str | Path) -> list[dict]:
    """Load the list of test-case dicts from one SingleStepTests/z80 JSON file.

    Each returned case is a dict with at least ``name``, ``initial`` and
    ``final`` keys; ``initial`` carries every field in :data:`REGISTER_FIELDS`
    plus a ``ram`` list of ``[addr, value]`` pairs.

    Raises:
        FileNotFoundError: if ``file_path`` does not exist.
        ValueError: if the file is not valid JSON, does not hold a non-empty
            list of cases, or a case is missing required structure/fields.
    """
    path = Path(file_path)
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        raise FileNotFoundError(f"vector file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not valid JSON: {exc}") from exc

    if not isinstance(data, list) or not data:
        raise ValueError(
            f"{path}: expected a non-empty JSON list of test cases, got {type(data).__name__}"
        )

    for index, case in enumerate(data):
        if not isinstance(case, dict):
            raise ValueError(f"{path}: case {index} is {type(case).__name__}, expected a dict")
        for key in ("initial", "final"):
            if not isinstance(case.get(key), dict):
                raise ValueError(
                    f"{path}: case {index} ({case.get('name')!r}) must have a dict "
                    f"{key!r} state, got {type(case.get(key)).__name__}"
                )
        missing = [field for field in REGISTER_FIELDS if field not in case["initial"]]
        if missing:
            raise ValueError(
                f"{path}: case {index} ({case.get('name')!r}) initial state is missing "
                f"register fields: {', '.join(missing)}"
            )
        for state_name in ("initial", "final"):
            ram = case[state_name].get("ram")
            if ram is None:
                raise ValueError(
                    f"{path}: case {index} ({case.get('name')!r}) {state_name} state "
                    "is missing a 'ram' list"
                )
            try:
                _ram_pairs(ram)
            except ValueError as exc:
                raise ValueError(f"{path}: case {index} ({case.get('name')!r}): {exc}") from exc
    return data


def setup_cpu(initial_state: dict) -> VectorCPU:
    """Instantiate a :class:`VectorCPU` from a vector ``initial`` state dict.

    Sets every register named in :data:`REGISTER_FIELDS` (``f`` is stored as a
    full byte via :attr:`z80.cpu.Flags.byte`) and writes each ``[addr, value]``
    RAM entry from ``initial``.

    Raises:
        TypeError: if ``initial_state`` is not a dict.
        ValueError: if a required register field is missing or a RAM entry is
            malformed; the message names the offending field/entry.
    """
    if not isinstance(initial_state, dict):
        raise TypeError(f"initial_state must be a dict, got {type(initial_state).__name__}")
    missing = [field for field in REGISTER_FIELDS if field not in initial_state]
    if missing:
        raise ValueError(f"initial state is missing register fields: {', '.join(missing)}")

    cpu = VectorCPU()
    for field in REGISTER_FIELDS:
        value = initial_state[field]
        if field == "f":
            cpu.f.byte = value
        else:
            setattr(cpu, field, value)
    for addr, value in _ram_pairs(initial_state.get("ram", [])):
        cpu.write_byte(addr, value)
    return cpu


def _opcode_and_pc(initial: dict) -> tuple[int | None, int | None]:
    """Extract the ``(opcode, pc)`` the case will execute from its initial state."""
    pc = initial.get("pc")
    if not isinstance(pc, int):
        return None, None
    ram = dict(_ram_pairs(initial.get("ram", [])))
    return ram.get(pc), pc


def _not_implemented_message(opcode: int | None, pc: int | None, exc: NotImplementedError) -> str:
    """Build the descriptive message for an unimplemented opcode."""
    location = f" at PC 0x{pc:04X}" if pc is not None else ""
    opcode_text = f"0x{opcode:02X}" if opcode is not None else "?"
    return f"opcode {opcode_text}{location} is not implemented ({exc})"


def _port_entries(ports: object) -> list[tuple[int, int, str]]:
    """Validate a vector ``ports`` list and return ``(addr, value, direction)`` triples.

    Every SingleStepTests I/O vector carries a top-level ``ports`` array of
    ``[addr, value, direction]`` entries, ``direction`` being ``"r"`` for a
    port read the oracle performed or ``"w"`` for a port write it recorded.

    Raises:
        ValueError: if ``ports`` is not a list or an entry is malformed.
    """
    if not isinstance(ports, list):
        raise ValueError(
            f"'ports' must be a list of [addr, value, direction] triples, "
            f"got {type(ports).__name__}"
        )
    entries: list[tuple[int, int, str]] = []
    for entry in ports:
        try:
            addr, value, direction = entry
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid port entry {entry!r}: expected a [addr, value, direction] triple"
            ) from exc
        if not isinstance(addr, int) or not isinstance(value, int) or direction not in ("r", "w"):
            raise ValueError(
                f"invalid port entry {entry!r}: addr and value must be ints and "
                "direction must be 'r' or 'w'"
            )
        entries.append((addr, value, direction))
    return entries


def _load_port_inputs(cpu: VectorCPU, ports: object) -> None:
    """Queue the vector's ``"r"`` port entries so :meth:`VectorCPU.read_port` can serve them."""
    for addr, value, direction in _port_entries(ports):
        if direction == "r":
            cpu.port_inputs.append((addr, value))


def _verify_port_outputs(cpu: VectorCPU, ports: object) -> None:
    """Assert the CPU's port writes match the vector's ``"w"`` entries.

    Also fails when a port input the vector supplied was never read, which
    means the CPU skipped an I/O access the oracle performed.

    Raises:
        AssertionError: listing the expected vs actual port writes, or naming
            the unread port.
    """
    expected = [
        (addr, value) for addr, value, direction in _port_entries(ports) if direction == "w"
    ]
    if cpu.port_outputs != expected:
        expected_text = ", ".join(f"0x{addr:04X}<-0x{value:02X}" for addr, value in expected)
        actual_text = ", ".join(f"0x{addr:04X}<-0x{value:02X}" for addr, value in cpu.port_outputs)
        raise AssertionError(
            "I/O port output mismatch:\n"
            f"  expected: {expected_text or '(none)'}\n"
            f"  actual:   {actual_text or '(none)'}"
        )
    if cpu.port_inputs:
        addr, _ = cpu.port_inputs[0]
        raise AssertionError(
            f"missing I/O port read: the vector supplies a port input at 0x{addr:04X} "
            "but the CPU never read it"
        )


def run_test_case(case: dict) -> dict:
    """Run one vector test case and return the final register/RAM state.

    Sets up the CPU from ``case["initial"]``, feeds the port reads listed in
    the case's top-level ``ports`` array (if any) to the I/O bus, calls
    ``step()`` exactly once, verifies the port writes the CPU performed
    against the ``"w"`` entries, and returns a dict in the same shape as
    :func:`expected_state`: every register from :data:`REGISTER_FIELDS`, a
    ``ram`` list of ``[addr, value]`` pairs for the addresses recorded in the
    case's expected final state (the address set the SingleStepTests
    generator documents for that instruction), and ``t_states``, the T-state
    total ``step()`` returned.

    ``step()`` rather than ``decode_and_execute()`` is deliberate: it is the
    public host entry point, and the vector state never carries a pending
    RESET/NMI/INT request, so the two are equivalent here except that
    ``step()`` is the one whose timing a host actually schedules from.

    Raises:
        OpcodeNotImplementedError: if ``decode_and_execute`` raises
            ``NotImplementedError``; the message names the opcode and PC, and
            the exception carries ``opcode``/``pc`` attributes.
        AssertionError: if a port write does not match the vector's expected
            ``"w"`` entry, a port read addresses a port the vector did not
            supply, or a supplied port input was never consumed.
        TypeError/ValueError: if ``case`` is malformed or the initial state is
            invalid (see :func:`setup_cpu`).
    """
    if not isinstance(case, dict):
        raise TypeError(f"case must be a dict, got {type(case).__name__}")
    for key in ("initial", "final"):
        if not isinstance(case.get(key), dict):
            raise ValueError(
                f"case must have a dict {key!r} state, got {type(case.get(key)).__name__}"
            )

    cpu = setup_cpu(case["initial"])
    _load_port_inputs(cpu, case.get("ports", []))
    try:
        t_states = cpu.step()
    except NotImplementedError as exc:
        opcode, pc = _opcode_and_pc(case["initial"])
        raise OpcodeNotImplementedError(
            _not_implemented_message(opcode, pc, exc),
            opcode=opcode,
            pc=pc,
        ) from exc
    _verify_port_outputs(cpu, case.get("ports", []))
    state = _snapshot_state(cpu, case["final"])
    state["t_states"] = t_states
    return state


def _snapshot_state(cpu: VectorCPU, final: dict) -> dict:
    """Snapshot CPU state in the same shape as a vector ``final`` field."""
    state = {
        field: (cpu.f.byte if field == "f" else getattr(cpu, field)) for field in REGISTER_FIELDS
    }
    state["ram"] = [[addr, cpu.read_byte(addr)] for addr, _ in _ram_pairs(final.get("ram", []))]
    return state


def expected_state(case: dict) -> dict:
    """Return the case's ``final`` snapshot extended with its expected T-states.

    The SingleStepTests ``cycles`` array holds one entry per T-state, so its
    length is the T-state total ``step()`` must return.  A case without a
    ``cycles`` array (older or hand-written vectors) yields no ``t_states``
    key, and :func:`assert_state_equal` then skips the timing comparison for
    that case rather than inventing an expectation.

    Raises:
        TypeError/ValueError: if ``case`` or its ``final``/``cycles`` fields
            are malformed.
    """
    if not isinstance(case, dict) or not isinstance(case.get("final"), dict):
        raise TypeError("case must be a dict with a dict 'final' state")
    expected = dict(case["final"])
    cycles = case.get("cycles")
    if cycles is not None:
        if not isinstance(cycles, list):
            raise ValueError(
                f"'cycles' must be a list of per-T-state entries, got {type(cycles).__name__}"
            )
        expected["t_states"] = len(cycles)
    return expected


def _format_value(value: object) -> str:
    """Format a register/RAM value for a readable mismatch message."""
    if isinstance(value, int):
        return f"0x{value:X}"
    return repr(value)


def assert_state_equal(expected: dict, actual: dict) -> None:
    """Assert two vector-style state dicts are equal, with a readable diff.

    Compares every register field from :data:`REGISTER_FIELDS` present in
    ``expected`` against ``actual`` (fields without a CPU counterpart such as
    the generator's ``ei``/``p`` are ignored), the ``t_states`` total when
    ``expected`` carries one (see :func:`expected_state`), and every
    ``[addr, value]`` RAM pair in ``expected`` against the corresponding
    address in ``actual``.  RAM
    addresses present in ``actual`` but absent from ``expected`` are also
    reported, since the SingleStepTests generator enumerates every relevant
    address per instruction -- an address outside the expected set means the
    emulator touched memory the oracle says it should not have.

    Raises:
        AssertionError: listing each mismatch (truncated after
            ``_MAX_REPORTED_DIFFS`` entries).
        TypeError: if either argument is not a dict.
        ValueError: if either ``ram`` list is malformed.
    """
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        raise TypeError(
            "expected and actual must both be state dicts, got "
            f"{type(expected).__name__} and {type(actual).__name__}"
        )

    diffs: list[str] = []
    diffs.extend(
        f"  register {field}: expected {_format_value(expected[field])}, "
        f"got {_format_value(actual.get(field))}"
        for field in REGISTER_FIELDS
        if field in expected and expected[field] != actual.get(field)
    )
    if "t_states" in expected and expected["t_states"] != actual.get("t_states"):
        diffs.append(
            f"  t_states: expected {expected['t_states']}, got {actual.get('t_states')} "
            "(one SingleStepTests 'cycles' entry per T-state)"
        )

    expected_ram = _ram_pairs(expected.get("ram", []))
    actual_ram = _ram_pairs(actual.get("ram", []))
    actual_by_addr = dict(actual_ram)
    for addr, value in expected_ram:
        if addr not in actual_by_addr:
            diffs.append(
                f"  ram[0x{addr:04X}]: expected {_format_value(value)}, "
                "got <address not present in actual RAM>"
            )
        elif actual_by_addr[addr] != value:
            diffs.append(
                f"  ram[0x{addr:04X}]: expected {_format_value(value)}, "
                f"got {_format_value(actual_by_addr[addr])}"
            )

    expected_addrs = {addr for addr, _ in expected_ram}
    for addr, value in actual_ram:
        if addr not in expected_addrs:
            diffs.append(
                f"  ram[0x{addr:04X}]: unexpected value {_format_value(value)} "
                "(address absent from expected RAM)"
            )

    if diffs:
        shown = diffs[:_MAX_REPORTED_DIFFS]
        if len(diffs) > _MAX_REPORTED_DIFFS:
            shown.append(f"  ... and {len(diffs) - _MAX_REPORTED_DIFFS} more difference(s)")
        raise AssertionError("state mismatch:\n" + "\n".join(shown))


# A tiny embedded sample (one NOP case) used by _main; deliberately not the
# full opcode set.  Values are synthetic but structurally identical to the
# real SingleStepTests/z80 vectors (initial/final register snapshots + ram).
_SAMPLE_JSON = """[
  {
    "name": "00 NOP (embedded sample)",
    "initial": {
      "pc": 256, "sp": 61440, "a": 110, "b": 185, "c": 144, "d": 208,
      "e": 190, "f": 250, "h": 131, "l": 147, "i": 166, "r": 16,
      "wz": 3933, "ix": 35859, "iy": 45708,
      "af_": 30257, "bc_": 17419, "de_": 13842, "hl_": 28289,
      "im": 0, "q": 0, "iff1": 1, "iff2": 1,
      "ram": [[256, 0]]
    },
    "final": {
      "pc": 257, "sp": 61440, "a": 110, "b": 185, "c": 144, "d": 208,
      "e": 190, "f": 250, "h": 131, "l": 147, "i": 166, "r": 17,
      "wz": 3933, "ix": 35859, "iy": 45708,
      "af_": 30257, "bc_": 17419, "de_": 13842, "hl_": 28289,
      "im": 0, "q": 0, "iff1": 1, "iff2": 1,
      "ram": [[256, 0]]
    }
  }
]
"""


def _main() -> None:
    """Run a tiny embedded self-test of every public helper.

    Writes the embedded sample to a temporary JSON file so
    :func:`load_json_vector` is exercised too, then checks each contract.
    The happy path is demonstrated with :func:`assert_state_equal` on an
    already-correct snapshot and the error path by checking that
    :func:`run_test_case` raises :class:`OpcodeNotImplementedError` for a
    deliberately unsupported instruction.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        sample_path = Path(tmp_dir) / "sample.json"
        sample_path.write_text(_SAMPLE_JSON, encoding="utf-8")

        cases = load_json_vector(sample_path)
        assert len(cases) == 1, f"expected 1 sample case, got {len(cases)}"
        case = cases[0]

        cpu = setup_cpu(case["initial"])
        assert cpu.pc == 0x0100, hex(cpu.pc)
        assert cpu.a == 0x6E, hex(cpu.a)
        assert cpu.f.byte == 0xFA, hex(cpu.f.byte)
        assert cpu.read_byte(0x0100) == 0x00, hex(cpu.read_byte(0x0100))

        unsupported_case = {
            "initial": {**case["initial"], "ram": [[0x0100, 0xDD], [0x0101, 0xED]]},
            "final": case["final"],
        }
        try:
            run_test_case(unsupported_case)
        except OpcodeNotImplementedError as exc:
            assert exc.opcode == 0xDD, exc.opcode
            assert exc.pc == 0x0100, exc.pc
            assert "not implemented" in str(exc), str(exc)
            assert "0xDD" in str(exc), str(exc)
        else:
            raise AssertionError(
                "run_test_case should raise OpcodeNotImplementedError for an unsupported opcode"
            )

        # Happy path: temporarily substitute a NOP implementation for the
        # skeleton's decode_and_execute and confirm run_test_case reproduces
        # the embedded sample's expected final state end-to-end (the sample is
        # a NOP case, so final differs from initial only in pc and r).
        real_decode = VectorCPU.decode_and_execute

        def fake_nop_decode(self: VectorCPU) -> int:
            self.pc = (self.pc + 1) & 0xFFFF
            self._inc_r()
            self._update_q(False)
            return 4

        VectorCPU.decode_and_execute = fake_nop_decode
        try:
            actual = run_test_case(case)
        finally:
            VectorCPU.decode_and_execute = real_decode
        assert_state_equal(case["final"], actual)
        assert actual["pc"] == case["final"]["pc"], actual["pc"]
        assert actual["r"] == case["final"]["r"], actual["r"]
        assert actual["t_states"] == 4, actual["t_states"]

        assert_state_equal(case["final"], case["final"])

        # Timing path: a 4-entry cycles array must match the NOP's 4 T-states,
        # and a wrong length must be reported by name.
        timed_case = {**case, "cycles": [[0x0100, 0x00, "r-m-"]] * 4}
        assert expected_state(timed_case)["t_states"] == 4
        assert_state_equal(expected_state(timed_case), actual)
        try:
            assert_state_equal(expected_state({**case, "cycles": [[0, 0, "----"]] * 5}), actual)
        except AssertionError as exc:
            assert "t_states: expected 5, got 4" in str(exc), str(exc)
        else:
            raise AssertionError("assert_state_equal should raise on a T-state mismatch")
        assert "t_states" not in expected_state(case), "no cycles array -> no timing expectation"

        broken = dict(case["final"])
        broken["a"] = 0x00
        broken["ram"] = [[0x0100, 0xFF], [0x9999, 0x42]]
        try:
            assert_state_equal(case["final"], broken)
        except AssertionError as exc:
            message = str(exc)
            assert "register a" in message, message
            assert "ram[0x0100]" in message, message
            assert "0x9999" in message, message
        else:
            raise AssertionError("assert_state_equal should raise on a mismatched snapshot")

        print("z80_test_utils self-test passed")


if __name__ == "__main__":
    _main()
