"""Readability contract for the instruction core, enforced the way correctness is.

The project's correctness claim is checked mechanically against external
oracles. This module applies the same discipline to the property that makes
the code usable as a reference: every opcode handler must be findable by the
mnemonic a Z80 programmer would grep for, and must live in the module that
owns that instruction group.

Three invariants, all derived from the source with :mod:`ast` (no import-time
side effects, no execution):

1. Every ``_op_*`` method has a docstring whose first line starts with one or
   more official Zilog mnemonics (``DJNZ e``, ``BIT b,(HL)``, ``SCF/CCF``),
   optionally followed by operands and a ``--`` explanation.
2. Every handler lives in the module that owns its mnemonic group.  The index
   module is the one exception to mnemonic ownership: it may implement any
   mnemonic, but only in an IX/IY form, so ``DJNZ`` cannot hide there again.
3. Every Zilog mnemonic is claimed by at least one handler, and no handler
   name is defined twice across the mixins (a duplicate would be silently
   shadowed by the MRO and never executed).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "z80_python"

#: The complete Z80 mnemonic vocabulary: Zilog's documented set plus ``SLL``,
#: the universally used name for the undocumented CB shift.
ZILOG_MNEMONICS = frozenset(
    """
    ADC ADD AND BIT CALL CCF CP CPD CPDR CPI CPIR CPL DAA DEC DI DJNZ EI EX EXX
    HALT IM IN INC IND INDR INI INIR JP JR LD LDD LDDR LDI LDIR NEG NOP OR OTDR
    OTIR OUT OUTD OUTI POP PUSH RES RET RETI RETN RL RLA RLC RLCA RLD RR RRA RRC
    RRCA RRD RST SBC SCF SET SLA SLL SRA SRL SUB XOR
    """.split()  # noqa: SIM905 - a whitespace table reads better than 68 quoted strings
)

#: Which module owns which mnemonics.  A handler whose docstring names a
#: mnemonic outside its module's set is misfiled.  ``_index.py`` is governed by
#: :data:`INDEX_OPERAND` instead: any mnemonic, IX/IY operands only.
OWNERS: dict[str, frozenset[str]] = {
    module: frozenset(mnemonics.split())
    for module, mnemonics in {
        "_loads.py": "LD PUSH POP",
        "_alu.py": "ADD ADC SUB SBC AND XOR OR CP INC DEC NEG DAA CPL SCF CCF",
        "_control.py": "JP JR DJNZ CALL RET RETI RETN RST EX EXX DI EI IM NOP HALT",
        "_rotate.py": "RLC RRC RL RR SLA SRA SLL SRL RLCA RRCA RLA RRA RLD RRD BIT RES SET",
        "_blocks.py": "LDI LDD LDIR LDDR CPI CPD CPIR CPDR",
        "_io.py": "IN OUT INI IND INIR INDR OUTI OUTD OTIR OTDR",
    }.items()
}
INDEX_MODULE = "_index.py"
INDEX_OPERAND = re.compile(r"\bI[XY]")

#: First-line grammar: ``MNEMONIC[/MNEMONIC...] [operands] [-- explanation]``.
_HEADLINE = re.compile(r"^(?P<mnemonics>[A-Z]+(?:/[A-Z]+)*)(?P<rest>(?:\s.*)?)$")


class Handler:
    """One ``_op_*`` method as found in the source."""

    def __init__(self, module: str, node: ast.FunctionDef) -> None:
        self.module = module
        self.name = node.name
        self.lineno = node.lineno
        self.docstring = ast.get_docstring(node, clean=True)

    @property
    def location(self) -> str:
        return f"{self.module}:{self.lineno} {self.name}"

    @property
    def headline(self) -> str:
        return (self.docstring or "").splitlines()[0] if self.docstring else ""

    def parse(self) -> tuple[list[str], str]:
        """Return ``(mnemonics, operand_text)`` from the docstring headline."""
        form = self.headline.split(" -- ", 1)[0].strip()
        match = _HEADLINE.match(form)
        if match is None:
            raise AssertionError(
                f"{self.location}: docstring must start with a Zilog mnemonic "
                f"(got {self.headline!r})"
            )
        return match.group("mnemonics").split("/"), match.group("rest").strip()


def _handlers() -> list[Handler]:
    found: list[Handler] = []
    for path in sorted(SRC.glob("_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            found.extend(
                Handler(path.name, node)
                for node in cls.body
                if isinstance(node, ast.FunctionDef) and node.name.startswith("_op_")
            )
    assert found, f"no _op_* handlers found under {SRC}"
    return found


HANDLERS = _handlers()


@pytest.mark.parametrize("handler", HANDLERS, ids=lambda h: f"{h.module}::{h.name}")
def test_handler_docstring_starts_with_zilog_mnemonic(handler: Handler) -> None:
    assert handler.docstring, f"{handler.location}: opcode handler has no docstring"
    mnemonics, _ = handler.parse()
    unknown = [m for m in mnemonics if m not in ZILOG_MNEMONICS]
    assert not unknown, f"{handler.location}: not Zilog mnemonics: {unknown}"


@pytest.mark.parametrize("handler", HANDLERS, ids=lambda h: f"{h.module}::{h.name}")
def test_handler_lives_in_owning_module(handler: Handler) -> None:
    mnemonics, operands = handler.parse()
    if handler.module == INDEX_MODULE:
        assert INDEX_OPERAND.search(operands), (
            f"{handler.location}: {handler.headline!r} has no IX/IY operand, so it does "
            f"not belong in {INDEX_MODULE}; move it to the module owning {mnemonics}"
        )
        return
    owned = OWNERS.get(handler.module)
    assert owned is not None, (
        f"{handler.location}: module {handler.module} is not a registered handler owner; "
        "add it to OWNERS or move the handler"
    )
    strays = [m for m in mnemonics if m not in owned]
    assert not strays, (
        f"{handler.location}: {strays} are not owned by {handler.module}; owners are "
        + ", ".join(f"{name} -> {sorted(o)}" for name, o in OWNERS.items())
    )


def test_every_zilog_mnemonic_has_a_greppable_handler() -> None:
    claimed: set[str] = set()
    for handler in HANDLERS:
        claimed.update(handler.parse()[0])
    missing = sorted(ZILOG_MNEMONICS - claimed)
    assert not missing, f"no handler docstring names these mnemonics: {missing}"


def test_handler_names_are_unique_across_mixins() -> None:
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for handler in HANDLERS:
        if handler.name in seen:
            duplicates.append(f"{handler.name} in {seen[handler.name]} and {handler.module}")
        seen[handler.name] = handler.module
    assert not duplicates, "handlers shadowed by the mixin MRO: " + "; ".join(duplicates)


def test_owner_tables_cover_the_whole_vocabulary() -> None:
    """The ownership map itself must partition the vocabulary with no gaps or overlaps."""
    union: set[str] = set()
    for name, owned in OWNERS.items():
        overlap = union & owned
        assert not overlap, f"{name} claims mnemonics already owned elsewhere: {sorted(overlap)}"
        union |= owned
    assert union == ZILOG_MNEMONICS, (
        f"unowned: {sorted(ZILOG_MNEMONICS - union)}; unknown: {sorted(union - ZILOG_MNEMONICS)}"
    )
