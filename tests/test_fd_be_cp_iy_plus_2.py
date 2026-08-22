"""Red-first witness for the FD indexed CP A,(IY+d) form.

``_execute_index`` routes FD-prefixed sub-opcodes through the indexed-memory
seam, but sub-opcode 0xBE (CP A,(IY+d)) has no handler yet, so it raises
``NotImplementedError``.  This file pins FD BE 02 with one direct
deterministic unit test: PC=0x2000, IY=0x5000, A=0xF0,
memory[0x5002]=0x0F.

When CP A,(IY+d) is implemented it must leave A untouched, leave IY
unchanged, set F to 0x9A (S=1 H=1 X=1 N=1), advance PC to 0x2003, latch WZ
to the effective address 0x5002, latch Q to 0x9A, and consume 19 T-states.
"""

from __future__ import annotations

from z80.cpu import Z80CPU


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


def test_fd_be_cp_a_mem_at_iy_plus_2() -> None:
    """FD BE 02 CP A,(IY+2): A=0xF0 vs 0x0F, F/WZ/PC/Q/T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    cpu.a = 0xF0
    cpu.write_byte(0x2000, 0xFD)
    cpu.write_byte(0x2001, 0xBE)
    cpu.write_byte(0x2002, 0x02)
    cpu.write_byte(0x5002, 0x0F)  # addressed memory operand

    tstates = cpu.decode_and_execute()

    # CP never writes A; 0xF0 - 0x0F flags: S=1 Z=0 Y=0 H=1 X=1 PV=0 N=1 C=0.
    assert cpu.a == 0xF0  # accumulator unchanged
    assert int(cpu.f) == 0x9A
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert cpu.wz == 0x5002  # WZ (MEMPTR) latches the effective address
    assert cpu.q == 0x9A  # Q latches the new F value (CP writes F)
    assert tstates == 19
