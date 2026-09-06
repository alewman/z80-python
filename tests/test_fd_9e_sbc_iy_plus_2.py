"""Red-first witness for the FD indexed SBC A,(IY+d) form.

``_execute_index`` routes FD-prefixed sub-opcodes through the indexed-memory
seam, but sub-opcode 0x9E (SBC A,(IY+d)) has no handler yet, so it raises
``NotImplementedError``.  This file pins FD 9E 02 with one direct
deterministic unit test: PC=0x2000, IY=0x5000, A=0x10, carry set,
memory[0x5002]=0x0F.

When SBC A,(IY+d) is implemented it must subtract the addressed byte plus the
carry input (``_sub(A, source, F.C)``, ``_alu_a`` group 3): 0x10 - 0x0F - 1 =
0x00 -> S=0 Z=1 Y=0 H=1 X=0 PV=0 N=1 C=0 (F = 0x52), leave IY unchanged,
advance PC to 0x2003, latch WZ to the effective address 0x5002, latch Q to
0x52, and consume 19 T-states.
"""

from __future__ import annotations

from z80_python import Z80CPU


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


def test_fd_9e_sbc_a_mem_at_iy_plus_2() -> None:
    """FD 9E 02 SBC A,(IY+2): 0x10 - 0x0F - C(1) = 0x00, F/WZ/PC/Q/T-states."""
    cpu = MemoryCPU()
    cpu.pc = 0x2000
    cpu.iy = 0x5000
    cpu.a = 0x10
    cpu.f.c = 1  # carry input feeds SBC
    cpu.write_byte(0x2000, 0xFD)
    cpu.write_byte(0x2001, 0x9E)
    cpu.write_byte(0x2002, 0x02)
    cpu.write_byte(0x5002, 0x0F)  # addressed memory operand

    tstates = cpu.decode_and_execute()

    # 0x10 - 0x0F - 1 = 0x00 -> S=0 Z=1 Y=0 H=1 X=0 PV=0 N=1 C=0 (F = 0x52).
    assert cpu.a == 0x00
    assert int(cpu.f) == 0x52
    assert cpu.iy == 0x5000  # index register unchanged
    assert cpu.pc == 0x2003  # prefix + opcode + displacement
    assert cpu.wz == 0x5002  # WZ (MEMPTR) latches the effective address
    assert cpu.q == 0x52  # Q latches the new F value (SBC writes F)
    assert tstates == 19
