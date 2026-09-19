"""Smoke-test the installed z80-python package, from outside the source tree.

    python scripts/smoke_installed_package.py

CI runs this against the freshly built wheel, and the publish workflow runs it
before any upload. It must pass with only the installed package importable.
"""

from pathlib import Path

import z80_python
from z80_python import Z80CPU, CPUState, DebugSession, disassemble_bytes

source_tree = Path(__file__).resolve().parents[1] / "src"
assert source_tree not in Path(z80_python.__file__).resolve().parents, z80_python.__file__

memory = bytearray(0x10000)
cpu = Z80CPU(memory.__getitem__, memory.__setitem__)
memory[:2] = bytes((0x3E, 0x2A))  # LD A,2Ah
assert cpu.capture_state() == CPUState()
assert disassemble_bytes(memory[:2]).text == "LD A, 0x2A"
record = DebugSession(cpu, peek_byte=memory.__getitem__, track_accesses=True).step()
assert (record.after.a, record.t_states) == (0x2A, 7)
assert record.accesses == (("r", 0, 0x3E), ("r", 1, 0x2A))
print(f"z80-python {z80_python.__file__}: installed package OK")
