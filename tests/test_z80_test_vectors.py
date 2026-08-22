"""Validate the locally cached SingleStepTests/z80 test vectors.

The vectors are cloned from https://github.com/SingleStepTests/z80 into
``tests/z80_test_vectors`` (git-ignored; see ``.gitignore``). Each JSON file
holds 1000 instruction tests for one opcode (or prefixed-opcode variant).

This module checks that the expected per-opcode files are all present and
that a representative sample from each family is well-formed JSON with the
documented top-level structure (``name`` / ``initial`` / ``final``).
"""

import json
from pathlib import Path

import pytest

VECTOR_DIR = Path(__file__).parent / "z80_test_vectors" / "v1"

# Expected layout: one JSON file per opcode byte for the base set (excluding
# the prefix bytes 0xCB/0xDD/0xED/0xFD themselves, which are exercised by
# their own prefixed families), plus one per prefixed variant. The DD/FD
# families likewise omit prefix bytes as their second byte (e.g. there is no
# ``dd ed.json``) but do include the full ``dd cb __ xx`` / ``fd cb __ xx``
# displacement sets.
_PREFIX_BYTES = {0xCB, 0xDD, 0xED, 0xFD}

# The ED family ships vectors only for the 80 defined ED opcodes: the full
# 0x40-0x7F block plus the block-transfer/search group 0xA0-0xBB.
_ED_OPCODES = set(range(0x40, 0x80)) | {
    0xA0,
    0xA1,
    0xA2,
    0xA3,
    0xA8,
    0xA9,
    0xAA,
    0xAB,
    0xB0,
    0xB1,
    0xB2,
    0xB3,
    0xB8,
    0xB9,
    0xBA,
    0xBB,
}

EXPECTED_FILES = (
    {f"{opcode:02x}.json" for opcode in range(256) if opcode not in _PREFIX_BYTES}
    | {f"cb {opcode:02x}.json" for opcode in range(256)}
    | {f"ed {opcode:02x}.json" for opcode in _ED_OPCODES}
    | {f"dd {opcode:02x}.json" for opcode in range(256) if opcode not in _PREFIX_BYTES}
    | {f"dd cb __ {opcode:02x}.json" for opcode in range(256)}
    | {f"fd {opcode:02x}.json" for opcode in range(256) if opcode not in _PREFIX_BYTES}
    | {f"fd cb __ {opcode:02x}.json" for opcode in range(256)}
)

# One representative file per family for the structural parse check.
SAMPLE_FILES = [
    "00.json",  # base (NOP)
    "c3.json",  # base (JP nn)
    "cb 07.json",  # CB prefix (RLC A)
    "ed 44.json",  # ED prefix (NEG)
    "dd 21.json",  # DD prefix (LD IX, nn)
    "dd cb __ 06.json",  # DD CB prefix (RLC (IX+d))
    "fd 21.json",  # FD prefix (LD IY, nn)
    "fd cb __ 0e.json",  # FD CB prefix (RRC (IY+d))
]


def test_all_expected_vector_files_present() -> None:
    """Every opcode/prefixed variant has a JSON vector file."""
    if not VECTOR_DIR.is_dir():
        pytest.skip("run scripts/fetch_test_vectors.py to enable vector tests")
    actual = {path.name for path in VECTOR_DIR.glob("*.json")}
    assert actual == EXPECTED_FILES, (
        f"vector file set mismatch: {len(EXPECTED_FILES - actual)} missing, "
        f"{len(actual - EXPECTED_FILES)} unexpected"
    )


def test_vector_files_are_parseable_json() -> None:
    """Representative files from each family are valid JSON with documented keys."""
    if not VECTOR_DIR.is_dir():
        pytest.skip("run scripts/fetch_test_vectors.py to enable vector tests")
    for name in SAMPLE_FILES:
        path = VECTOR_DIR / name
        assert path.is_file(), f"missing sample vector file: {name}"
        with path.open(encoding="utf-8") as handle:
            entries = json.load(handle)
        assert isinstance(entries, list) and entries, f"{name}: expected a non-empty list"
        for entry in entries[:5]:
            assert {"name", "initial", "final"} <= set(entry), (
                f"{name}: entry {entry.get('name')!r} missing name/initial/final keys"
            )
