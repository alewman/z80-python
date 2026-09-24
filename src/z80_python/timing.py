"""Where inside an instruction each of its memory and I/O accesses falls.

``step()`` reports an instruction's total T-states. A board that shares its
bus with another processor (the Mega Drive's arbiter, for one) also needs to
know *when* inside the instruction each access happens. The core does not
count T-states as it goes, so this module answers from a table instead:
:func:`instruction_timing` takes the instruction's bytes and returns every
access it can make, in order, each with its T-state offset.

The table (``_access_timing.py``) is derived from the SingleStepTests corpus
by ``scripts/derive_access_timing.py``, which records, for every one of its
1,604 instructions and every case, where each access falls, and refuses to
write a table unless every case of an instruction agrees. That corpus is
emulator-derived (docs/validation.md, "Oracle tiers"), and so is this table.
tests/test_access_timing.py re-derives it whenever the corpus is present,
and checks this core against it: for each shape of each instruction, the
accesses ``step()`` makes are the table's, in the same order and of the same
kinds, and its T-states are one of the table's lengths.

**Offsets.** The corpus samples the bus once per T-state, between T-states.
An access's ``t`` is the index of the first sample that shows it (RD or WR
with MREQ or IORQ), counted from the instruction's first T-state; every
opcode fetch has ``t == 1``, and an ordinary memory read after it ``t == 5``.

**Conditional and repeating instructions** have two shapes: ``CALL cc`` makes
five accesses when taken and three when not; ``LDIR`` takes 21 T-states when it
repeats and 16 when it stops. The two shapes always agree on every access they
both make, so :attr:`InstructionTiming.accesses` lists the longest, and the
k-th access a board sees falls at ``accesses[k].t`` whichever way the
instruction goes. :attr:`InstructionTiming.shapes` gives each shape's length
and how many of the accesses it makes.

**Not in the corpus**, and derived here by rule:

* The 176 undefined ED opcodes, which execute as 8-T-state no-ops (Young
  3.4): the ED prefix and opcode fetches, at the offsets every ED instruction
  in the corpus shows.
* A DD or FD followed by DD, FD or ED: the first byte is a stray prefix, its
  own 4-T-state opcode fetch (Young 3.7), and the instruction after it is
  timed as usual, 4 T-states later.

Interrupt acknowledge cycles (RESET, NMI, IM 0/1/2), and the 4-T-state HALT
idle cycle, are not instructions and are not covered.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from z80_python._access_timing import TABLE

__all__ = ["AccessTiming", "InstructionTiming", "instruction_timing"]


@dataclass(frozen=True, slots=True)
class AccessTiming:
    """One bus access: its kind (``"read"``, ``"write"``, ``"in"`` or ``"out"``) and offset."""

    kind: str
    t: int


@dataclass(frozen=True, slots=True)
class InstructionTiming:
    """Every access an instruction can make, and the ways it can execute.

    ``shapes`` holds ``(t_states, accesses_made)`` for each way: the
    instruction takes ``t_states`` and makes the first ``accesses_made`` of
    ``accesses``.
    """

    accesses: tuple[AccessTiming, ...]
    shapes: tuple[tuple[int, int], ...]


def _entry(key: tuple[int, ...]) -> InstructionTiming:
    accesses, shapes = TABLE[key]
    return InstructionTiming(tuple(AccessTiming(kind, t) for kind, t in accesses), shapes)


# The fetches every ED instruction begins with; an undefined ED opcode is only these.
_ED_NOP = InstructionTiming((AccessTiming("read", 1), AccessTiming("read", 5)), ((8, 2),))
_STRAY_PREFIX = AccessTiming("read", 1)


def instruction_timing(data: Sequence[int]) -> InstructionTiming:
    """The access timing of the instruction whose bytes begin ``data``.

    ``data`` starts at the instruction's first byte, as a host would peek it
    at PC before ``step()``; it needs as many bytes as the instruction has
    opcode and prefix bytes (four for ``DD CB d op``, more for a run of
    prefixes). Operands and displacements are not looked at.
    """
    first = data[0]
    if first in (0xCB, 0xED):
        key = (first, data[1])
        if first == 0xED and key not in TABLE:
            return _ED_NOP
        return _entry(key)
    if first in (0xDD, 0xFD):
        second = data[1]
        if second in (0xDD, 0xED, 0xFD):
            rest = instruction_timing(data[1:])
            return InstructionTiming(
                (_STRAY_PREFIX, *(AccessTiming(a.kind, a.t + 4) for a in rest.accesses)),
                tuple((t_states + 4, made + 1) for t_states, made in rest.shapes),
            )
        if second == 0xCB:
            return _entry((first, 0xCB, data[3]))
        return _entry((first, second))
    return _entry((first,))
