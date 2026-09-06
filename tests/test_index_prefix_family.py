"""Red-first regression coverage for the DD/FD index-prefix family.

audit-index-prefix-family diagnosed the smallest ordinary-program IX/IY
prefix family as::

    DD 09/19/29/39  ADD IX,BC / ADD IX,DE / ADD IX,IX / ADD IX,SP
    FD 09/19/29/39  ADD IY,BC / ADD IY,DE / ADD IY,IY / ADD IY,SP
    DD/FD 21 nn nn  LD IX/IY,nn
    DD/FD 23        INC IX/IY
    DD/FD 2B        DEC IX/IY
    DD/FD E1        POP IX/IY
    DD/FD E5        PUSH IX/IY
    DD/FD E9        JP (IX/IY)

That is the exact 20-opcode family this module covers, and nothing else.

Documented state/flag/PC/stack effects (matching the SingleStepTests/z80
oracle and the Z80 reference):

* ``ADD IX/IY,rr`` -- 15 T-states; PC += 2, R += 2; index updated;
  WZ = old index + 1; H/N/C/X/Y recomputed from the 16-bit add while
  S/Z/PV are preserved; Q latches the new F value.
* ``LD IX/IY,nn`` -- 14 T-states; PC += 4, R += 2; index = nn; flags
  untouched; Q cleared; WZ untouched.
* ``INC IX/IY`` / ``DEC IX/IY`` -- 10 T-states; PC += 2, R += 2;
  index +/- 1 (wrapping); flags untouched; Q cleared; WZ untouched.
* ``POP IX/IY`` -- 14 T-states; PC += 2, R += 2; SP += 2; index reads the
  popped word; flags untouched; Q cleared; WZ untouched.
* ``PUSH IX/IY`` -- 15 T-states; PC += 2, R += 2; SP -= 2; (SP) = low byte,
  (SP+1) = high byte; flags untouched; Q cleared; WZ untouched.
* ``JP (IX/IY)`` -- 8 T-states; PC = index; R += 2; flags untouched;
  Q cleared; WZ untouched.

Why this file is red by design: the CPU core (src/z80_python/) currently
dispatches only the CB and ED prefixes in ``decode_and_execute``; a DD or FD
prefix falls through to ``_execute_main`` and raises ``NotImplementedError``.
Every unit test below therefore fails today, and every per-opcode vector
test below fails on the first case, because the family is unimplemented --
that is the regression this file pins.  When the family gets implemented,
these same tests flip green only if the full documented semantics (flags,
Q, WZ, PC, R, SP, stack bytes and T-state counts) match the oracle exactly.

Vector coverage uses the existing z80_test_utils.py seams
(``load_json_vector`` / ``run_test_case`` / ``assert_state_equal``) against
the locally cached SingleStepTests/z80 corpus under
``tests/z80_test_vectors/v1``; every invocation is offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from validation.vector_utils import assert_state_equal, load_json_vector, run_test_case
from z80_python.cpu import (
    FLAG_C,
    FLAG_H,
    FLAG_PV,
    FLAG_S,
    FLAG_X,
    FLAG_Y,
    FLAG_Z,
    Z80CPU,
)


class MemoryCPU(Z80CPU):
    """Concrete Z80CPU backed by a flat 64 KiB bytearray."""

    def __init__(self) -> None:
        super().__init__()
        self.memory = bytearray(0x10000)

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        raise NotImplementedError("unit-test CPU does not model I/O ports")

    def write_port(self, addr: int, value: int) -> None:
        raise NotImplementedError("unit-test CPU does not model I/O ports")


def _run(cpu: MemoryCPU, opcode_bytes: bytes) -> int:
    """Place ``opcode_bytes`` at ``pc``, execute, and return the T-state count.

    A ``NotImplementedError`` here is the whole point of the red regression:
    the DD/FD index-prefix family has no dispatcher yet, so every instruction
    in this module fails until the CPU implements it.
    """
    start = cpu.pc
    for offset, value in enumerate(opcode_bytes):
        cpu.write_byte((start + offset) & 0xFFFF, value)
    try:
        return cpu.decode_and_execute()
    except NotImplementedError as exc:
        pytest.fail(
            f"DD/FD index-prefix family is not implemented "
            f"(opcode bytes 0x{opcode_bytes.hex(' ')}): {exc}"
        )


def _get_index(cpu: MemoryCPU, prefix: int) -> int:
    """Read the index register selected by a DD/FD prefix."""
    return cpu.ix if prefix == 0xDD else cpu.iy


def _set_index(cpu: MemoryCPU, prefix: int, value: int) -> None:
    """Write the index register selected by a DD/FD prefix."""
    if prefix == 0xDD:
        cpu.ix = value & 0xFFFF
    else:
        cpu.iy = value & 0xFFFF


def _set_add_pair(cpu: MemoryCPU, prefix: int, pair_index: int, value: int) -> None:
    """Write the 16-bit pair selected by the ADD rr opcode field (0-3)."""
    value &= 0xFFFF
    if pair_index == 0:
        cpu.b = (value >> 8) & 0xFF
        cpu.c = value & 0xFF
    elif pair_index == 1:
        cpu.d = (value >> 8) & 0xFF
        cpu.e = value & 0xFF
    elif pair_index == 2:
        _set_index(cpu, prefix, value)
    else:
        cpu.sp = value


def _reference_add16_flags(x: int, y: int, f_before: int) -> tuple[int, int]:
    """ADD HL/IX/IY,rr flag recipe: H/N/C/X/Y recomputed, S/Z/PV preserved.

    Mirrors the SingleStepTests/z80 generator used by ``_op_add_hl_rr`` in
    src/z80_python/: C = carry out of bit 15, H = carry out of bit 11, N is
    cleared, and X/Y are copied from the high byte of the 16-bit result.
    """
    result = x + y
    carry = 1 if result > 0xFFFF else 0
    result &= 0xFFFF
    half_carry = ((x ^ y ^ result) & 0x1000) >> 12
    f_after = f_before & (FLAG_S | FLAG_Z | FLAG_PV)  # also clears N
    f_after |= FLAG_C if carry else 0
    f_after |= FLAG_H if half_carry else 0
    f_after |= (result >> 8) & (FLAG_X | FLAG_Y)
    return f_after, result


# ----------------------------------------------------------------------
# Deterministic CPU unit coverage
# ----------------------------------------------------------------------
# The initial F value below (0b1010_1001 = S+Y+X+C set) gives every
# recomputed flag a chance to differ from its preserved counterpart.

_ADD_CASES: tuple[tuple[int, int, int], ...] = (
    # (pair_index, pair value, index value)
    (0, 0x1234, 0x0FED),  # BC: plain add, no carry/half-carry
    (0, 0x0200, 0xFF00),  # BC: carry out of bit 15
    (1, 0x0001, 0x0FFF),  # DE: half-carry out of bit 11
    (2, 0x0000, 0x8000),  # IX/IY + IX/IY: self-add wrapping to 0 with carry
    (3, 0x5A5A, 0x3A5A),  # SP: plain add
)


@pytest.mark.parametrize("prefix", [0xDD, 0xFD], ids=["dd", "fd"])
@pytest.mark.parametrize(
    ("pair_index", "pair_value", "index_value"),
    _ADD_CASES,
    ids=["bc", "bc-carry", "de-halfcarry", "self-wrap", "sp"],
)
def test_add_index_rr(prefix: int, pair_index: int, pair_value: int, index_value: int) -> None:
    """DD/FD 09/19/29/39 ADD IX/IY,rr: index, flags, Q, WZ, PC, R, T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.f.byte = 0b1010_1001
    cpu.q = 0b1010_1001
    cpu.wz = 0x1234
    _set_index(cpu, prefix, index_value)
    if pair_index == 2:
        pair_value = index_value
    _set_add_pair(cpu, prefix, pair_index, pair_value)

    subopcode = (0x09, 0x19, 0x29, 0x39)[pair_index]
    tstates = _run(cpu, bytes([prefix, subopcode]))

    assert tstates == 15
    expected_f, expected_result = _reference_add16_flags(index_value, pair_value, 0b1010_1001)
    assert _get_index(cpu, prefix) == expected_result
    assert cpu.f.byte == expected_f
    assert cpu.q == expected_f
    assert cpu.wz == (index_value + 1) & 0xFFFF
    assert cpu.pc == 0x2002
    assert cpu.r == 2  # prefix and subopcode fetches each bump R


@pytest.mark.parametrize("prefix", [0xDD, 0xFD], ids=["dd", "fd"])
def test_ld_index_nn(prefix: int) -> None:
    """DD/FD 21 nn nn LD IX/IY,nn: load only; flags/Q/WZ untouched or cleared."""
    cpu = MemoryCPU()
    cpu.pc = 0x3000
    cpu.f.byte = 0xD7
    cpu.q = 0xD7
    cpu.wz = 0x5A5A
    _set_index(cpu, prefix, 0x0000)

    tstates = _run(cpu, bytes([prefix, 0x21, 0x34, 0x12]))

    assert tstates == 14
    assert _get_index(cpu, prefix) == 0x1234
    assert cpu.f.byte == 0xD7  # flags untouched
    assert cpu.q == 0  # LD does not write F, so Q is cleared
    assert cpu.wz == 0x5A5A  # WZ untouched
    assert cpu.pc == 0x3004
    assert cpu.r == 2  # only the two opcode fetches bump R (operands do not)


@pytest.mark.parametrize("prefix", [0xDD, 0xFD], ids=["dd", "fd"])
@pytest.mark.parametrize(
    ("subopcode", "start", "expected"),
    [
        (0x23, 0x0001, 0x0002),  # INC
        (0x23, 0xFFFF, 0x0000),  # INC wrapping
        (0x2B, 0x0001, 0x0000),  # DEC
        (0x2B, 0x0000, 0xFFFF),  # DEC wrapping
    ],
    ids=["inc", "inc-wrap", "dec", "dec-wrap"],
)
def test_inc_dec_index(prefix: int, subopcode: int, start: int, expected: int) -> None:
    """DD/FD 23/2B INC/DEC IX/IY: index +/- 1; flags/Q/WZ untouched or cleared."""
    cpu = MemoryCPU()
    cpu.pc = 0x4000
    cpu.f.byte = 0xB5
    cpu.q = 0xB5
    cpu.wz = 0xABCD
    _set_index(cpu, prefix, start)

    tstates = _run(cpu, bytes([prefix, subopcode]))

    assert tstates == 10
    assert _get_index(cpu, prefix) == expected
    assert cpu.f.byte == 0xB5  # flags untouched
    assert cpu.q == 0  # INC/DEC do not write F, so Q is cleared
    assert cpu.wz == 0xABCD  # WZ untouched
    assert cpu.pc == 0x4002
    assert cpu.r == 2


@pytest.mark.parametrize("prefix", [0xDD, 0xFD], ids=["dd", "fd"])
def test_pop_index(prefix: int) -> None:
    """DD/FD E1 POP IX/IY: index reads (SP), SP += 2; flags/Q/WZ untouched."""
    cpu = MemoryCPU()
    cpu.pc = 0x5000
    cpu.sp = 0x6000
    cpu.write_byte(0x6000, 0xCD)
    cpu.write_byte(0x6001, 0xAB)
    cpu.f.byte = 0xB5
    cpu.q = 0xB5
    cpu.wz = 0x1234
    _set_index(cpu, prefix, 0x0000)

    tstates = _run(cpu, bytes([prefix, 0xE1]))

    assert tstates == 14
    assert _get_index(cpu, prefix) == 0xABCD
    assert cpu.sp == 0x6002
    assert cpu.f.byte == 0xB5  # flags untouched
    assert cpu.q == 0  # POP does not write F, so Q is cleared
    assert cpu.wz == 0x1234  # WZ untouched
    assert cpu.pc == 0x5002
    assert cpu.r == 2


@pytest.mark.parametrize("prefix", [0xDD, 0xFD], ids=["dd", "fd"])
def test_push_index(prefix: int) -> None:
    """DD/FD E5 PUSH IX/IY: SP -= 2, low byte then high byte; flags/Q/WZ untouched."""
    cpu = MemoryCPU()
    cpu.pc = 0x5000
    cpu.sp = 0x6000
    cpu.f.byte = 0xB5
    cpu.q = 0xB5
    cpu.wz = 0x1234
    _set_index(cpu, prefix, 0xABCD)

    tstates = _run(cpu, bytes([prefix, 0xE5]))

    assert tstates == 15
    assert cpu.sp == 0x5FFE
    assert cpu.read_byte(0x5FFE) == 0xCD  # low byte at the new SP
    assert cpu.read_byte(0x5FFF) == 0xAB  # high byte at SP + 1
    assert cpu.f.byte == 0xB5  # flags untouched
    assert cpu.q == 0  # PUSH does not write F, so Q is cleared
    assert cpu.wz == 0x1234  # WZ untouched
    assert cpu.pc == 0x5002
    assert cpu.r == 2


@pytest.mark.parametrize("prefix", [0xDD, 0xFD], ids=["dd", "fd"])
def test_jp_index(prefix: int) -> None:
    """DD/FD E9 JP (IX/IY): PC = index; flags/Q/WZ untouched."""
    cpu = MemoryCPU()
    cpu.pc = 0x5000
    cpu.f.byte = 0xB5
    cpu.q = 0xB5
    cpu.wz = 0x1234
    _set_index(cpu, prefix, 0x7F00)

    tstates = _run(cpu, bytes([prefix, 0xE9]))

    assert tstates == 8
    assert cpu.pc == 0x7F00
    assert cpu.f.byte == 0xB5  # flags untouched
    assert cpu.q == 0  # JP does not write F, so Q is cleared
    assert cpu.wz == 0x1234  # WZ untouched
    assert cpu.r == 2


# ----------------------------------------------------------------------
# Bounded offline vector coverage (locally cached SingleStepTests corpus)
# ----------------------------------------------------------------------
# One JSON file per (prefix, subopcode) pair, 1000 cases each.  Only the
# files that actually exist in the cached corpus are parametrized, so this
# stays fully offline and bounded by the corpus itself.

VECTOR_DIR = Path(__file__).parent / "z80_test_vectors" / "v1"

#: The exact DD/FD family selected by audit-index-prefix-family.
INDEX_PREFIX_VECTOR_FILES: tuple[str, ...] = (
    "dd 09.json",
    "dd 19.json",
    "dd 29.json",
    "dd 39.json",
    "dd 21.json",
    "dd 23.json",
    "dd 2b.json",
    "dd e1.json",
    "dd e5.json",
    "dd e9.json",
    "fd 09.json",
    "fd 19.json",
    "fd 29.json",
    "fd 39.json",
    "fd 21.json",
    "fd 23.json",
    "fd 2b.json",
    "fd e1.json",
    "fd e5.json",
    "fd e9.json",
)


def _present_vector_files() -> list[str]:
    """Return the subset of the selected family present in the cached corpus."""
    return [name for name in INDEX_PREFIX_VECTOR_FILES if (VECTOR_DIR / name).is_file()]


PRESENT_VECTOR_FILES = _present_vector_files()


def test_index_prefix_vector_corpus_is_present() -> None:
    """The whole selected family must exist in the locally cached corpus."""
    if not VECTOR_DIR.is_dir():
        pytest.skip("run scripts/fetch_test_vectors.py to enable vector tests")
    missing = [name for name in INDEX_PREFIX_VECTOR_FILES if name not in PRESENT_VECTOR_FILES]
    assert not missing, "cached corpus is missing selected DD/FD vector files: " + ", ".join(
        missing
    )


@pytest.mark.slow
@pytest.mark.parametrize("vector_file", PRESENT_VECTOR_FILES, ids=PRESENT_VECTOR_FILES)
def test_index_prefix_vector_file(vector_file: str) -> None:
    """Every case in one DD/FD vector file must match initial -> final exactly.

    Unlike tests/test_z80.py -- which reports an unimplemented opcode as a
    skip while the family is being built -- this red regression treats the
    missing DD/FD dispatcher as the failure it is: the selected family is
    supposed to work, so a ``NotImplementedError`` fails the test.
    """
    cases = load_json_vector(VECTOR_DIR / vector_file)
    for index, case in enumerate(cases):
        try:
            actual = run_test_case(case)
        except NotImplementedError as exc:
            pytest.fail(
                f"{vector_file} case {index} ({case.get('name', '?')}): "
                f"DD/FD index-prefix family is not implemented: {exc}"
            )
        assert_state_equal(case["final"], actual)
