"""Unit tests for the Z80 jump/call/return/restart group (src/z80/cpu.py).

The authoritative check for this group is the per-opcode SingleStepTests/z80
vector suite run by ``tests/test_z80.py`` (46 vector files, 1000 cases each,
covering JR e / JR cc,e, JP nn / JP cc,nn / JP (HL), CALL nn / CALL cc,nn,
RET / RET cc, RETI, RETN and RST p).  The tests here are a fast, readable
complement that pins down the documented semantics -- condition evaluation
against the flag register, WZ (MEMPTR) updates, push/pop of the return
address, the RETI/RETN IFF1 <- IFF2 restore, the T-state counts and the fact
that none of the group writes the F register (so Q is cleared) -- so a
regression is visible in a single test name instead of a 1000-case vector
diff.
"""

from __future__ import annotations

import pytest

from z80.cpu import Z80CPU


class MemoryCPU(Z80CPU):
    """Concrete Z80CPU backed by a flat 64 KiB bytearray."""

    def __init__(self, memory: bytes = bytes(0x10000)) -> None:
        super().__init__()
        self.memory = bytearray(memory)

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        raise NotImplementedError("test MemoryCPU does not model I/O ports")

    def write_port(self, addr: int, value: int) -> None:
        raise NotImplementedError("test MemoryCPU does not model I/O ports")


def _program(cpu: MemoryCPU, pc: int, *bytes_: int) -> None:
    """Write a little program at ``pc`` and point the CPU at it."""
    for offset, value in enumerate(bytes_):
        cpu.write_byte(pc + offset, value)
    cpu.pc = pc


def _push(cpu: MemoryCPU, value: int) -> None:
    """Push a 16-bit value using the CPU's own stack helper."""
    cpu._push_word(value)


# --- JR e / JR cc,e --------------------------------------------------------


def test_jr_forward_jump() -> None:
    cpu = MemoryCPU()
    _program(cpu, 0x1000, 0x18, 0x05)  # JR +5 (skips 5 bytes after the operand)
    assert cpu.decode_and_execute() == 12
    assert cpu.pc == 0x1007  # 0x1002 + 5
    assert cpu.wz == 0x1007
    assert cpu.q == 0  # flags untouched -> Q cleared
    assert cpu.f.byte == 0


def test_jr_backward_jump_wraps_signed_displacement() -> None:
    cpu = MemoryCPU()
    _program(cpu, 0x1003, 0x18, 0xFD)  # JR -3
    cpu.decode_and_execute()
    assert cpu.pc == 0x1002  # 0x1005 - 3
    assert cpu.wz == 0x1002


def test_jr_takes_eight_bit_negative_boundary() -> None:
    cpu = MemoryCPU()
    _program(cpu, 0x0002, 0x18, 0x80)  # JR -128
    cpu.decode_and_execute()
    assert cpu.pc == 0xFF84  # 0x0004 - 128, wrapped to 16 bits
    assert cpu.wz == 0xFF84


@pytest.mark.parametrize(
    ("opcode", "flag_attr", "flag_value", "taken"),
    [
        (0x20, "z", 0, True),  # JR NZ,e
        (0x20, "z", 1, False),
        (0x28, "z", 1, True),  # JR Z,e
        (0x28, "z", 0, False),
        (0x30, "c", 0, True),  # JR NC,e
        (0x30, "c", 1, False),
        (0x38, "c", 1, True),  # JR C,e
        (0x38, "c", 0, False),
    ],
)
def test_jr_cc_condition_and_t_states(
    opcode: int, flag_attr: str, flag_value: int, taken: bool
) -> None:
    cpu = MemoryCPU()
    setattr(cpu.f, flag_attr, flag_value)
    _program(cpu, 0x2000, opcode, 0x04)
    assert cpu.decode_and_execute() == (12 if taken else 7)
    if taken:
        assert cpu.pc == 0x2006  # 0x2002 + 4
        assert cpu.wz == 0x2006
    else:
        assert cpu.pc == 0x2002  # just past the displacement
        assert cpu.wz == 0  # WZ is only loaded when the branch is taken
    assert cpu.q == 0


# --- JP nn / JP cc,nn / JP (HL) --------------------------------------------


def test_jp_nn_sets_pc_and_wz() -> None:
    cpu = MemoryCPU()
    _program(cpu, 0x1000, 0xC3, 0x34, 0x12)  # JP 0x1234
    assert cpu.decode_and_execute() == 10
    assert cpu.pc == 0x1234
    assert cpu.wz == 0x1234
    assert cpu.q == 0


@pytest.mark.parametrize(
    ("opcode", "flag_attr", "flag_value"),
    [
        (0xC2, "z", 0),  # JP NZ,nn
        (0xCA, "z", 1),  # JP Z,nn
        (0xD2, "c", 0),  # JP NC,nn
        (0xDA, "c", 1),  # JP C,nn
        (0xE2, "pv", 0),  # JP PO,nn
        (0xEA, "pv", 1),  # JP PE,nn
        (0xF2, "s", 0),  # JP P,nn
        (0xFA, "s", 1),  # JP M,nn
    ],
)
def test_jp_cc_all_conditions_taken(opcode: int, flag_attr: str, flag_value: int) -> None:
    cpu = MemoryCPU()
    setattr(cpu.f, flag_attr, flag_value)
    _program(cpu, 0x0000, opcode, 0x78, 0x56)  # JP cc,0x5678
    assert cpu.decode_and_execute() == 10
    assert cpu.pc == 0x5678
    assert cpu.wz == 0x5678


@pytest.mark.parametrize(
    ("opcode", "flag_attr", "flag_value"),
    [
        (0xC2, "z", 1),  # JP NZ,nn with Z set -> not taken
        (0xCA, "z", 0),  # JP Z,nn with Z clear
        (0xD2, "c", 1),  # JP NC,nn with C set
        (0xDA, "c", 0),  # JP C,nn with C clear
        (0xE2, "pv", 1),  # JP PO,nn with PV set
        (0xEA, "pv", 0),  # JP PE,nn with PV clear
        (0xF2, "s", 1),  # JP P,nn with S set
        (0xFA, "s", 0),  # JP M,nn with S clear
    ],
)
def test_jp_cc_not_taken_keeps_pc_but_still_loads_wz(
    opcode: int, flag_attr: str, flag_value: int
) -> None:
    cpu = MemoryCPU()
    setattr(cpu.f, flag_attr, flag_value)
    _program(cpu, 0x0000, opcode, 0x78, 0x56)  # JP cc,0x5678
    assert cpu.decode_and_execute() == 10
    assert cpu.pc == 0x0003  # falls through past the operand
    assert cpu.wz == 0x5678  # WZ is loaded from the operand regardless
    assert cpu.q == 0


def test_jp_hl_uses_hl_and_leaves_wz_untouched() -> None:
    cpu = MemoryCPU()
    cpu.h = 0xAB
    cpu.l = 0xCD
    cpu.wz = 0x1234
    _program(cpu, 0x0000, 0xE9)  # JP (HL)
    assert cpu.decode_and_execute() == 4
    assert cpu.pc == 0xABCD
    assert cpu.wz == 0x1234  # not affected
    assert cpu.q == 0


# --- CALL nn / CALL cc,nn --------------------------------------------------


def test_call_pushes_return_address_and_jumps() -> None:
    cpu = MemoryCPU()
    cpu.sp = 0xFFFE
    _program(cpu, 0x1000, 0xCD, 0x00, 0x80)  # CALL 0x8000
    assert cpu.decode_and_execute() == 17
    assert cpu.pc == 0x8000
    assert cpu.wz == 0x8000
    assert cpu.sp == 0xFFFC  # two bytes pushed
    # The return address is the byte after the operand, high byte at SP+1.
    assert cpu.read_byte(0xFFFC) == 0x03  # low byte of 0x1003
    assert cpu.read_byte(0xFFFD) == 0x10  # high byte of 0x1003
    assert cpu.q == 0


def test_call_cc_not_taken_does_not_touch_stack() -> None:
    cpu = MemoryCPU()
    cpu.sp = 0xFFFE
    cpu.f.z = 1
    _program(cpu, 0x1000, 0xC4, 0x00, 0x80)  # CALL NZ,0x8000 (Z set)
    assert cpu.decode_and_execute() == 10
    assert cpu.pc == 0x1003
    assert cpu.wz == 0x8000  # operand still loads WZ
    assert cpu.sp == 0xFFFE  # nothing pushed
    assert cpu.q == 0


def test_call_cc_taken_pushes_return_address() -> None:
    cpu = MemoryCPU()
    cpu.sp = 0x1000
    cpu.f.c = 1
    _program(cpu, 0x0000, 0xDC, 0x20, 0x40)  # CALL C,0x4020
    assert cpu.decode_and_execute() == 17
    assert cpu.pc == 0x4020
    assert cpu.wz == 0x4020
    assert cpu.sp == 0x0FFE
    assert cpu.read_byte(0x0FFE) == 0x03  # low byte of the return address 0x0003
    assert cpu.read_byte(0x0FFF) == 0x00


# --- RET / RET cc ----------------------------------------------------------


def test_ret_pops_return_address() -> None:
    cpu = MemoryCPU()
    cpu.sp = 0x2000
    _push(cpu, 0x3456)  # leaves SP at 0x1FFE with 0x56 at 0x1FFE, 0x34 at 0x1FFF
    _program(cpu, 0x0000, 0xC9)  # RET
    assert cpu.decode_and_execute() == 10
    assert cpu.pc == 0x3456
    assert cpu.wz == 0x3456
    assert cpu.sp == 0x2000  # SP restored to its pre-push value
    assert cpu.q == 0


def test_ret_cc_not_taken_keeps_stack() -> None:
    cpu = MemoryCPU()
    cpu.sp = 0x1FFE
    cpu.f.z = 0
    _program(cpu, 0x0000, 0xC8)  # RET Z with Z clear
    assert cpu.decode_and_execute() == 5
    assert cpu.pc == 0x0001
    assert cpu.wz == 0
    assert cpu.sp == 0x1FFE  # nothing popped
    assert cpu.q == 0


def test_ret_cc_taken_pops_return_address() -> None:
    cpu = MemoryCPU()
    cpu.sp = 0x1FFE
    _push(cpu, 0xABCD)
    cpu.f.pv = 1
    _program(cpu, 0x0000, 0xE8)  # RET PE with PV set
    assert cpu.decode_and_execute() == 11
    assert cpu.pc == 0xABCD
    assert cpu.wz == 0xABCD
    assert cpu.sp == 0x1FFE  # SP restored to its pre-push value
    assert cpu.q == 0


# --- RETI / RETN -----------------------------------------------------------


@pytest.mark.parametrize("sub", [0x45, 0x4D, 0x55, 0x5D, 0x65, 0x6D, 0x75, 0x7D])
def test_reti_retn_pop_and_restore_iff1_from_iff2(sub: int) -> None:
    cpu = MemoryCPU()
    cpu.sp = 0x1FFE
    _push(cpu, 0x2468)
    cpu.iff1 = False
    cpu.iff2 = True
    _program(cpu, 0x0000, 0xED, sub)  # RETN / RETI (any of the aliases)
    assert cpu.decode_and_execute() == 14
    assert cpu.pc == 0x2468
    assert cpu.wz == 0x2468
    assert cpu.sp == 0x1FFE  # SP restored to its pre-push value
    assert cpu.iff1 is True  # IFF1 restored from IFF2
    assert cpu.iff2 is True  # IFF2 preserved
    assert cpu.q == 0


def test_retn_can_clear_iff1_when_iff2_was_zero() -> None:
    cpu = MemoryCPU()
    cpu.sp = 0x1FFE
    _push(cpu, 0x0000)
    cpu.iff1 = True
    cpu.iff2 = False
    _program(cpu, 0x0000, 0xED, 0x45)  # RETN
    cpu.decode_and_execute()
    assert cpu.iff1 is False
    assert cpu.iff2 is False


# --- RST p -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("opcode", "vector"),
    [
        (0xC7, 0x00),
        (0xCF, 0x08),
        (0xD7, 0x10),
        (0xDF, 0x18),
        (0xE7, 0x20),
        (0xEF, 0x28),
        (0xF7, 0x30),
        (0xFF, 0x38),
    ],
)
def test_rst_pushes_return_address_and_jumps_to_vector(opcode: int, vector: int) -> None:
    cpu = MemoryCPU()
    cpu.sp = 0x3000
    _program(cpu, 0x4000, opcode)
    assert cpu.decode_and_execute() == 11
    assert cpu.pc == vector
    assert cpu.wz == vector
    assert cpu.sp == 0x2FFE
    assert cpu.read_byte(0x2FFE) == 0x01  # low byte of the return address 0x4001
    assert cpu.read_byte(0x2FFF) == 0x40
    assert cpu.q == 0


# --- group-wide invariants -------------------------------------------------


@pytest.mark.parametrize(
    "program",
    [
        (0x18, 0x00),  # JR e
        (0x20, 0x00),  # JR NZ,e
        (0xC3, 0x00, 0x00),  # JP nn
        (0xC2, 0x00, 0x00),  # JP cc,nn
        (0xE9,),  # JP (HL)
        (0xCD, 0x00, 0x00),  # CALL nn
        (0xC4, 0x00, 0x00),  # CALL cc,nn
        (0xC9,),  # RET
        (0xC0,),  # RET cc
        (0xC7,),  # RST p
        (0xED, 0x45),  # RETN
        (0xED, 0x4D),  # RETI
    ],
)
def test_group_never_modifies_flags_and_clears_q(program: tuple[int, ...]) -> None:
    cpu = MemoryCPU()
    cpu.f.byte = 0b1011_0101
    cpu.sp = 0x1FFE
    cpu.h = 0x00
    cpu.l = 0x00
    _push(cpu, 0x0000)
    _program(cpu, 0x0000, *program)
    cpu.decode_and_execute()
    assert cpu.f.byte == 0b1011_0101  # F untouched by every jump/call/ret/rst
    assert cpu.q == 0  # and because F was not written, Q is cleared
