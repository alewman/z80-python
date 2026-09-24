"""z80_python.timing: the access-timing table, its decoding, and the core against it.

The fast tests check how instruction_timing() finds an instruction's entry.
The slow ones need the SingleStepTests corpus: they re-derive the table from
it (it must be the committed one), and run this core on one case of every
shape of every instruction, requiring the accesses step() makes to be the
table's, in order and of the same kinds, and its T-states one of the table's.
"""

import importlib.util
import json
from pathlib import Path

import pytest

from validation.vector_utils import _load_port_inputs, setup_cpu
from z80_python._access_timing import TABLE
from z80_python.timing import AccessTiming, InstructionTiming, instruction_timing

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "z80_test_vectors" / "v1"
KINDS = {"read", "write", "in", "out"}


def _derive_module():
    spec = importlib.util.spec_from_file_location(
        "derive_access_timing", ROOT / "scripts" / "derive_access_timing.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_corpus_instruction_has_an_entry_and_every_entry_starts_with_its_fetch() -> None:
    assert len(TABLE) == 1604
    for key, (accesses, shapes) in TABLE.items():
        assert accesses[0] == ("read", 1), key
        assert {kind for kind, _ in accesses} <= KINDS, key
        assert [t for _, t in accesses] == sorted(t for _, t in accesses), key
        assert shapes and all(made <= len(accesses) for _, made in shapes), key


def test_plain_cb_ed_and_index_instructions_are_found_by_their_opcode_bytes() -> None:
    assert instruction_timing([0x00]) == InstructionTiming((AccessTiming("read", 1),), ((4, 1),))
    assert instruction_timing([0xCB, 0x06]).shapes == ((15, 4),)
    assert instruction_timing([0xED, 0xB0]).shapes == ((16, 4), (21, 4))
    assert instruction_timing([0xDD, 0x7E, 0x05]).shapes == ((19, 4),)
    # POP: the two stack reads, three T-states apart (issue #16's Mega Drive case).
    pop = instruction_timing([0xE1])
    assert [(a.kind, a.t) for a in pop.accesses] == [("read", 1), ("read", 5), ("read", 8)]


def test_index_cb_is_keyed_by_the_last_byte_not_the_displacement() -> None:
    assert instruction_timing([0xDD, 0xCB, 0x80, 0x06]) == instruction_timing(
        [0xDD, 0xCB, 0x00, 0x06]
    )
    assert instruction_timing([0xFD, 0xCB, 0x05, 0x46]).shapes == ((20, 5),)


def test_conditional_instructions_list_the_accesses_of_their_longest_shape() -> None:
    call_nz = instruction_timing([0xC4, 0x00, 0x00])
    assert [a.kind for a in call_nz.accesses] == ["read", "read", "read", "write", "write"]
    assert call_nz.shapes == ((10, 3), (17, 5))


def test_an_undefined_ed_opcode_is_its_two_fetches() -> None:
    timing = instruction_timing([0xED, 0x00])
    assert timing.accesses == (AccessTiming("read", 1), AccessTiming("read", 5))
    assert timing.shapes == ((8, 2),)


def test_a_stray_prefix_is_one_more_fetch_and_shifts_the_rest_by_four() -> None:
    plain = instruction_timing([0xDD, 0x7E, 0x05])
    stray = instruction_timing([0xFD, 0xDD, 0x7E, 0x05])
    assert stray.accesses[0] == AccessTiming("read", 1)
    assert stray.accesses[1:] == tuple(AccessTiming(a.kind, a.t + 4) for a in plain.accesses)
    assert stray.shapes == ((23, 5),)
    before_ed = instruction_timing([0xDD, 0xED, 0xB0])
    assert before_ed.shapes == ((20, 5), (25, 5))


@pytest.fixture(scope="module")
def corpus_cases() -> dict[tuple[int, ...], list[dict]]:
    """One case per shape of every corpus instruction."""
    if not CORPUS.is_dir():
        pytest.skip("SingleStepTests corpus not fetched (scripts/fetch_test_vectors.py)")
    derive = _derive_module()
    chosen: dict[tuple[int, ...], list[dict]] = {}
    for path in sorted(CORPUS.glob("*.json")):
        seen: dict = {}
        for case in json.loads(path.read_text()):
            shape = (derive.accesses_of(case["cycles"]), len(case["cycles"]))
            seen.setdefault(shape, case)
        chosen[derive.key_of(path.stem)] = list(seen.values())
    return chosen


@pytest.mark.slow
def test_the_committed_table_is_a_fresh_derivation_from_the_corpus() -> None:
    if not CORPUS.is_dir():
        pytest.skip("SingleStepTests corpus not fetched (scripts/fetch_test_vectors.py)")
    derive = _derive_module()
    assert derive.TABLE.read_text() == derive.render(derive.derive())


def _bus_kinds(case: dict) -> tuple[list[str], int]:
    """Run ``case`` on this core; return the kinds of its accesses, in order, and its T-states."""
    cpu = setup_cpu(case["initial"])
    _load_port_inputs(cpu, case.get("ports", []))
    kinds: list[str] = []
    read_byte, write_byte = cpu.read_byte, cpu.write_byte
    read_port, write_port = cpu.read_port, cpu.write_port

    def logged_read(address: int) -> int:
        kinds.append("read")
        return read_byte(address)

    def logged_write(address: int, value: int) -> None:
        kinds.append("write")
        write_byte(address, value)

    def logged_in(port: int) -> int:
        kinds.append("in")
        return read_port(port)

    def logged_out(port: int, value: int) -> None:
        kinds.append("out")
        write_port(port, value)

    cpu.read_byte, cpu.write_byte = logged_read, logged_write
    cpu.read_port, cpu.write_port = logged_in, logged_out
    return kinds, cpu.step()


@pytest.mark.slow
def test_the_core_makes_the_tables_accesses_in_order(corpus_cases) -> None:
    for key, cases in corpus_cases.items():
        accesses, shapes = TABLE[key]
        for case in cases:
            kinds, t_states = _bus_kinds(case)
            assert (t_states, len(kinds)) in shapes, (key, case["name"], t_states, kinds)
            assert kinds == [kind for kind, _ in accesses[: len(kinds)]], (key, case["name"])
