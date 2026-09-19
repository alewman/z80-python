"""Block instructions: one instruction per row, checked in full.

The rows cover block transfers and searches. Each row is ``Row(program,
t_states, initial, changes)``, run by ``conftest.check_step``: the CPU starts
from ``initial`` with ``program`` at PC and executes one ``step()``, and
afterwards every register, every byte of memory, every port write and the
T-states must be exactly as the row says. What ``changes`` lists changed to
that value; everything else is unchanged. ``conftest.Row`` explains the
notation.

The handlers are in ``src/z80_python/_blocks.py``. The rows were recorded from
the hand-written per-opcode tests this file replaced (0.4.0, polish item 3),
each of which they reproduce exactly; the SingleStepTests corpus
(``tests/test_z80.py``) covers the same opcodes exhaustively.
"""

import pytest
from conftest import Row, check_step

# The rows are a table; the formatter would put every field on its own line.
# fmt: off
ROWS = (
    Row("ED A0", 16,
        "pc=1000 a=02 c=01 d=30 h=20",
        "f=20 c=00 e=01 l=01 pc=1002 r=02 q=20"),
    Row("ED A0", 16,
        "pc=1000 c=03 d=30 h=20 wz=ABCD (2000)=5A",
        "f=2C c=02 e=01 l=01 pc=1002 r=02 q=2C (3000)=5A"),
    Row("ED A0", 16,
        "pc=1000 f=55 c=01 d=30 h=20 (2000)=01",
        "f=41 c=00 e=01 l=01 pc=1002 r=02 q=41 (3000)=01"),
    Row("ED A1", 16,
        "pc=1000 a=10 f=01 c=03 h=20 wz=1234 (2000)=05",
        "f=3F c=02 l=01 pc=1002 wz=1235 r=02 q=3F"),
    Row("ED A1", 16,
        "pc=1000 a=42 c=01 h=20 (2000)=42",
        "f=42 c=00 l=01 pc=1002 wz=0001 r=02 q=42"),
    Row("ED A8", 16,
        "pc=1000 c=02 d=30 h=20 (2000)=7B",
        "f=2C c=01 d=2F e=FF h=1F l=FF pc=1002 r=02 q=2C (3000)=7B"),
    Row("ED A9", 16,
        "pc=1000 a=10 c=03 h=20 wz=1234 (2000)=05",
        "f=3E c=02 h=1F l=FF pc=1002 wz=1233 r=02 q=3E"),
    Row("ED B0", 16,
        "pc=1000 a=99 f=04 c=01 d=30 e=02 h=20 l=02 wz=1001 r=05 q=04 (0000)=3E (0001)=99 "
        "(2000)=10 (2001)=11 (2002)=12 (3000)=10 (3001)=11",
        "f=28 c=00 e=03 l=03 pc=1002 r=07 q=28 (3002)=12"),
    Row("ED B0", 16,
        "pc=1000 c=01 d=30 h=20 wz=ABCD (2000)=11",
        "c=00 e=01 l=01 pc=1002 r=02 (3000)=11"),
    Row("ED B0", 16,
        "pc=1000 f=04 c=01 d=30 e=02 h=20 l=02 wz=1001 r=04 q=04 (2000)=10 (2001)=11 (2002)=12 "
        "(3000)=10 (3001)=11",
        "f=20 c=00 e=03 l=03 pc=1002 r=06 q=20 (3002)=12"),
    Row("ED B0", 21,
        "pc=1000 a=99 f=04 c=02 d=30 e=01 h=20 l=01 wz=1001 r=03 (0000)=3E (0001)=99 (2000)=10 "
        "(2001)=11 (2002)=12 (3000)=10",
        "c=01 e=02 l=02 r=05 q=04 (3001)=11"),
    Row("ED B0", 21,
        "pc=1000 c=03 d=30 h=20 (2000)=10 (2001)=11 (2002)=12",
        "f=04 c=02 e=01 l=01 wz=1001 r=02 q=04 (3000)=10"),
    Row("ED B0", 21,
        "pc=1000 c=03 d=30 h=20 (2000)=11",
        "f=04 c=02 e=01 l=01 wz=1001 r=02 q=04 (3000)=11"),
    Row("ED B0", 21,
        "pc=1000 d=30 h=20 (2000)=5A",
        "f=04 b=FF c=FF e=01 l=01 wz=1001 r=02 q=04 (3000)=5A"),
    Row("ED B0", 21,
        "pc=1000 f=04 c=02 d=30 e=01 h=20 l=01 wz=1001 r=02 q=04 (2000)=10 (2001)=11 (2002)=12 "
        "(3000)=10",
        "c=01 e=02 l=02 r=04 (3001)=11"),
    Row("ED B1", 16,
        "pc=1000 a=11 f=16 c=02 h=20 l=02 wz=1001 r=04 q=16 (2000)=01 (2001)=02 (2002)=11 "
        "(2003)=04",
        "f=46 c=01 l=03 pc=1002 wz=1002 r=06 q=46"),
    Row("ED B1", 16,
        "pc=1000 a=FF f=86 c=01 h=20 l=01 wz=1001 r=02 q=86 (2000)=01 (2001)=02",
        "f=8A c=00 l=02 pc=1002 wz=1002 r=04 q=8A"),
    Row("ED B1", 21,
        "pc=1000 a=11 c=04 h=20 wz=5000 (2000)=01 (2001)=02 (2002)=11 (2003)=04",
        "f=06 c=03 l=01 wz=1001 r=02 q=06"),
    Row("ED B1", 21,
        "pc=1000 a=11 f=06 c=03 h=20 l=01 wz=1001 r=02 q=06 (2000)=01 (2001)=02 (2002)=11 "
        "(2003)=04",
        "f=16 c=02 l=02 r=04 q=16"),
    Row("ED B1", 21,
        "pc=1000 a=FF c=02 h=20 (2000)=01 (2001)=02",
        "f=86 c=01 l=01 wz=1001 r=02 q=86"),
    Row("ED B8", 16,
        "pc=1000 f=04 c=01 d=30 h=20 wz=1001 r=04 q=04 (2000)=A0 (2001)=A1 (2002)=A2 (3001)=A1 "
        "(3002)=A2",
        "f=00 c=00 d=2F e=FF h=1F l=FF pc=1002 r=06 q=00 (3000)=A0"),
    Row("ED B8", 21,
        "pc=1000 c=03 d=30 e=02 h=20 l=02 (2000)=A0 (2001)=A1 (2002)=A2",
        "f=04 c=02 e=01 l=01 wz=1001 r=02 q=04 (3002)=A2"),
    Row("ED B8", 21,
        "pc=1000 f=04 c=02 d=30 e=01 h=20 l=01 wz=1001 r=02 q=04 (2000)=A0 (2001)=A1 (2002)=A2 "
        "(3002)=A2",
        "c=01 e=00 l=00 r=04 (3001)=A1"),
    Row("ED B9", 16,
        "pc=1000 a=02 f=96 c=02 h=20 l=01 wz=1001 r=04 q=96 (2000)=01 (2001)=02 (2002)=03 "
        "(2003)=04",
        "f=46 c=01 l=00 pc=1002 wz=1000 r=06 q=46"),
    Row("ED B9", 21,
        "pc=1000 a=02 c=04 h=20 l=03 wz=6000 (2000)=01 (2001)=02 (2002)=03 (2003)=04",
        "f=96 c=03 l=02 wz=1001 r=02 q=96"),
    Row("ED B9", 21,
        "pc=1000 a=02 f=96 c=03 h=20 l=02 wz=1001 r=02 q=96 (2000)=01 (2001)=02 (2002)=03 "
        "(2003)=04",
        "c=02 l=01 r=04"),
)
# fmt: on


@pytest.mark.parametrize("row", ROWS, ids=str)
def test_step(row: Row) -> None:
    check_step(row)
