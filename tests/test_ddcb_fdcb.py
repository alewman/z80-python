"""DD CB and FD CB: one instruction per row, checked in full.

The rows cover rotates, BIT, RES and SET on (IX+d)/(IY+d). Each row is
``Row(program, t_states, initial, changes)``, run by ``conftest.check_step``:
the CPU starts from ``initial`` with ``program`` at PC and executes one
``step()``, and afterwards every register, every byte of memory, every port
write and the T-states must be exactly as the row says. What ``changes`` lists
changed to that value; everything else is unchanged. ``conftest.Row`` explains
the notation.

The handlers are in ``src/z80_python/_index.py``. The rows were recorded from
the hand-written per-opcode tests this file replaced (0.4.0, polish item 3),
each of which they reproduce exactly; the SingleStepTests corpus
(``tests/test_z80.py``) covers the same opcodes exhaustively.
"""

import pytest
from conftest import Row, check_step

# The rows are a table; the formatter would put every field on its own line.
# fmt: off
ROWS = (
    Row("DD CB 01 1D", 23,
        "pc=2000 a=01 f=01 b=02 c=03 d=04 e=05 h=06 l=07 ix=A810 iy=5678 r=3E q=01 (A811)=02",
        "f=84 l=81 pc=2004 wz=A811 r=40 q=84 (A811)=81"),
    Row("DD CB 01 3E", 23,
        "pc=2000 a=01 b=02 c=03 d=04 e=05 h=06 l=07 ix=FFFF iy=5678 r=3E (0000)=01",
        "f=45 pc=2004 r=40 q=45 (0000)=00"),
    Row("DD CB 01 46", 20,
        "pc=2000 a=01 f=01 b=02 c=03 d=04 e=05 h=06 l=07 ix=FFFF iy=5678 wz=BEEF r=3E q=01 "
        "(0000)=01",
        "f=11 pc=2004 wz=0000 r=40 q=11"),
    Row("DD CB 01 7F", 20,
        "pc=2000 a=01 f=01 b=02 c=03 d=04 e=05 h=06 l=07 ix=A810 iy=5678 wz=BEEF r=3E q=01 "
        "(A811)=80",
        "f=B9 pc=2004 wz=A811 r=40 q=B9"),
    Row("DD CB 01 AD", 23,
        "pc=2000 a=01 f=C5 b=02 c=03 d=04 e=05 h=06 l=07 ix=A810 iy=5678 r=3E q=C5 (A811)=2F",
        "l=0F pc=2004 wz=A811 r=40 q=00 (A811)=0F"),
    Row("DD CB 01 FE", 23,
        "pc=2000 a=01 f=C5 b=02 c=03 d=04 e=05 h=06 l=07 ix=FFFF iy=5678 r=3E q=C5 (0000)=01",
        "pc=2004 r=40 q=00 (0000)=81"),
    Row("DD CB FF 00", 23,
        "pc=2000 a=01 b=02 c=03 d=04 e=05 h=06 l=07 ix=2800 iy=5678 r=3E (27FF)=81",
        "f=05 b=03 pc=2004 wz=27FF r=40 q=05 (27FF)=03"),
    Row("DD CB FF 40", 20,
        "pc=2000 a=01 f=01 b=02 c=03 d=04 e=05 h=06 l=07 ix=2800 iy=5678 wz=BEEF r=3E q=01",
        "f=75 pc=2004 wz=27FF r=40 q=75"),
    Row("DD CB FF 80", 23,
        "pc=2000 a=01 f=C5 b=02 c=03 d=04 e=05 h=06 l=07 ix=2800 iy=5678 r=3E q=C5 (27FF)=FF",
        "b=FE pc=2004 wz=27FF r=40 q=00 (27FF)=FE"),
    Row("FD CB 01 1D", 23,
        "pc=2000 a=01 f=01 b=02 c=03 d=04 e=05 h=06 l=07 ix=1234 iy=A810 r=3E q=01 (A811)=02",
        "f=84 l=81 pc=2004 wz=A811 r=40 q=84 (A811)=81"),
    Row("FD CB 01 3E", 23,
        "pc=2000 a=01 b=02 c=03 d=04 e=05 h=06 l=07 ix=1234 iy=FFFF r=3E (0000)=01",
        "f=45 pc=2004 r=40 q=45 (0000)=00"),
    Row("FD CB 01 46", 20,
        "pc=2000 a=01 f=01 b=02 c=03 d=04 e=05 h=06 l=07 ix=1234 iy=FFFF wz=BEEF r=3E q=01 "
        "(0000)=01",
        "f=11 pc=2004 wz=0000 r=40 q=11"),
    Row("FD CB 01 7F", 20,
        "pc=2000 a=01 f=01 b=02 c=03 d=04 e=05 h=06 l=07 ix=1234 iy=A810 wz=BEEF r=3E q=01 "
        "(A811)=80",
        "f=B9 pc=2004 wz=A811 r=40 q=B9"),
    Row("FD CB 01 AD", 23,
        "pc=2000 a=01 f=C5 b=02 c=03 d=04 e=05 h=06 l=07 ix=1234 iy=A810 r=3E q=C5 (A811)=2F",
        "l=0F pc=2004 wz=A811 r=40 q=00 (A811)=0F"),
    Row("FD CB 01 FE", 23,
        "pc=2000 a=01 f=C5 b=02 c=03 d=04 e=05 h=06 l=07 ix=1234 iy=FFFF r=3E q=C5 (0000)=01",
        "pc=2004 r=40 q=00 (0000)=81"),
    Row("FD CB FF 00", 23,
        "pc=2000 a=01 b=02 c=03 d=04 e=05 h=06 l=07 ix=1234 iy=2800 r=3E (27FF)=81",
        "f=05 b=03 pc=2004 wz=27FF r=40 q=05 (27FF)=03"),
    Row("FD CB FF 40", 20,
        "pc=2000 a=01 f=01 b=02 c=03 d=04 e=05 h=06 l=07 ix=1234 iy=2800 wz=BEEF r=3E q=01",
        "f=75 pc=2004 wz=27FF r=40 q=75"),
    Row("FD CB FF 80", 23,
        "pc=2000 a=01 f=C5 b=02 c=03 d=04 e=05 h=06 l=07 ix=1234 iy=2800 r=3E q=C5 (27FF)=FF",
        "b=FE pc=2004 wz=27FF r=40 q=00 (27FF)=FE"),
)
# fmt: on


@pytest.mark.parametrize("row", ROWS, ids=str)
def test_step(row: Row) -> None:
    check_step(row)
