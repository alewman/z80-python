"""Rotates and bit operations: one instruction per row, checked in full.

The rows cover rotates, shifts, BIT, RES and SET, RLD and RRD. Each row is
``Row(program, t_states, initial, changes)``, run by ``conftest.check_step``:
the CPU starts from ``initial`` with ``program`` at PC and executes one
``step()``, and afterwards every register, every byte of memory, every port
write and the T-states must be exactly as the row says. What ``changes`` lists
changed to that value; everything else is unchanged. ``conftest.Row`` explains
the notation.

The handlers are in ``src/z80_python/_rotate.py``. The rows were recorded from
the hand-written per-opcode tests this file replaced (0.4.0, polish item 3),
each of which they reproduce exactly; the SingleStepTests corpus
(``tests/test_z80.py``) covers the same opcodes exhaustively.
"""

import pytest
from conftest import Row, check_step

# The rows are a table; the formatter would put every field on its own line.
# fmt: off
ROWS = (
    Row("CB 00", 8,
        "pc=0000 b=81",
        "f=05 b=03 pc=0002 r=02 q=05"),
    Row("CB 01", 8,
        "pc=0000 c=81",
        "f=05 c=03 pc=0002 r=02 q=05"),
    Row("CB 02", 8,
        "pc=0000 d=81",
        "f=05 d=03 pc=0002 r=02 q=05"),
    Row("CB 03", 8,
        "pc=0000 e=81",
        "f=05 e=03 pc=0002 r=02 q=05"),
    Row("CB 04", 8,
        "pc=0000 h=81",
        "f=05 h=03 pc=0002 r=02 q=05"),
    Row("CB 05", 8,
        "pc=0000 l=81",
        "f=05 l=03 pc=0002 r=02 q=05"),
    Row("CB 06", 15,
        "pc=0000 h=40 (4000)=15",
        "f=28 pc=0002 r=02 q=28 (4000)=2A"),
    Row("CB 07", 8,
        "pc=0000 a=81",
        "a=03 f=05 pc=0002 r=02 q=05"),
    Row("CB 07", 8,
        "pc=0000 a=BF",
        "a=7F f=29 pc=0002 r=02 q=29"),
    Row("CB 0F", 8,
        "pc=0000 a=01",
        "a=80 f=81 pc=0002 r=02 q=81"),
    Row("CB 10", 8,
        "pc=0000 f=01 b=80",
        "b=01 pc=0002 r=02 q=01"),
    Row("CB 18", 8,
        "pc=0000 f=01 b=01",
        "f=81 b=80 pc=0002 r=02 q=81"),
    Row("CB 20", 8,
        "pc=0000 b=80",
        "f=45 b=00 pc=0002 r=02 q=45"),
    Row("CB 28", 8,
        "pc=0000 b=81",
        "f=85 b=C0 pc=0002 r=02 q=85"),
    Row("CB 30", 8,
        "pc=0000 b=40",
        "f=84 b=81 pc=0002 r=02 q=84"),
    Row("CB 38", 8,
        "pc=0000 b=81",
        "f=01 b=40 pc=0002 r=02 q=01"),
    Row("ED 67", 18,
        "pc=0000 a=42 h=09 l=8F (098F)=38",
        "a=48 f=0C pc=0002 wz=0990 r=02 q=0C (098F)=23"),
    Row("ED 6F", 18,
        "pc=0000 a=9F h=A6 l=81 (A681)=83",
        "a=98 f=88 pc=0002 wz=A682 r=02 q=88 (A681)=3F"),
    Row("ED 6F", 18,
        "pc=0000 f=01 h=40",
        "f=45 pc=0002 wz=4001 r=02 q=45"),
    Row("ED 6F", 18,
        "pc=0000 h=40 r=10",
        "f=44 pc=0002 wz=4001 r=12 q=44"),
)
# fmt: on


@pytest.mark.parametrize("row", ROWS, ids=str)
def test_step(row: Row) -> None:
    check_step(row)
