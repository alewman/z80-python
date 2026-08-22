"""Lifecycle tests for host-requested Z80 maskable interrupts."""

import pytest

from z80_python import Z80CPU


class MemoryCPU(Z80CPU):
    """Concrete host with a flat 64 KiB memory image."""

    def __init__(self) -> None:
        super().__init__()
        self.memory = bytearray(0x10000)

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        return 0xFF

    def write_port(self, addr: int, value: int) -> None:
        pass


def test_im1_interrupt_pushes_instruction_boundary_and_clears_flip_flops() -> None:
    cpu = MemoryCPU()
    cpu.im, cpu.iff1, cpu.iff2, cpu.pc, cpu.sp, cpu.r = 1, True, True, 0x1234, 0x4000, 0x7E
    cpu.request_maskable_interrupt()

    assert cpu.step() == 13
    assert (cpu.pc, cpu.sp, cpu.read_byte(0x3FFE), cpu.read_byte(0x3FFF)) == (
        0x0038,
        0x3FFE,
        0x34,
        0x12,
    )
    assert (cpu.iff1, cpu.iff2, cpu.maskable_interrupt_pending, cpu.halted, cpu.r) == (
        False,
        False,
        False,
        False,
        0x7F,
    )


def test_ei_defers_a_pending_interrupt_until_one_following_instruction_completes() -> None:
    cpu = MemoryCPU()
    cpu.im, cpu.sp = 1, 0x4000
    cpu.memory[:2] = bytes((0xFB, 0x00))  # EI; NOP
    cpu.request_maskable_interrupt()

    assert cpu.step() == 4  # EI
    assert (cpu.pc, cpu.iff1, cpu.maskable_interrupt_pending) == (1, True, True)
    assert cpu.step() == 4  # required post-EI instruction
    assert cpu.pc == 2
    assert cpu.step() == 13  # interrupt boundary after NOP
    assert (cpu.pc, cpu.sp) == (0x0038, 0x3FFE)


def test_di_masks_a_pending_interrupt_until_ei_delay_has_elapsed() -> None:
    cpu = MemoryCPU()
    cpu.im, cpu.sp = 1, 0x4000
    cpu.memory[:3] = bytes((0xF3, 0xFB, 0x00))  # DI; EI; NOP
    cpu.request_maskable_interrupt()

    assert (cpu.step(), cpu.step(), cpu.step()) == (4, 4, 4)
    assert (cpu.pc, cpu.maskable_interrupt_pending) == (3, True)
    assert cpu.step() == 13
    assert cpu.pc == 0x0038


def test_halt_idles_until_accepted_interrupt_wakes_the_cpu() -> None:
    cpu = MemoryCPU()
    cpu.im, cpu.iff1, cpu.iff2, cpu.sp = 1, True, True, 0x4000
    cpu.memory[0] = 0x76  # HALT

    assert cpu.step() == 4
    assert (cpu.pc, cpu.halted, cpu.r) == (1, True, 1)
    assert cpu.step() == 4
    assert (cpu.pc, cpu.halted, cpu.r) == (1, True, 2)

    cpu.request_maskable_interrupt()
    assert cpu.step() == 13
    assert (cpu.pc, cpu.sp, cpu.halted, cpu.r) == (0x0038, 0x3FFE, False, 3)
    assert (cpu.read_byte(0x3FFE), cpu.read_byte(0x3FFF)) == (1, 0)


def test_im2_uses_i_register_and_device_vector_byte() -> None:
    cpu = MemoryCPU()
    cpu.im, cpu.i, cpu.iff1, cpu.iff2, cpu.pc, cpu.sp = 2, 0x80, True, True, 0x1234, 0x4000
    cpu.memory[0x80FE:0x8100] = bytes((0x78, 0x56))
    cpu.request_maskable_interrupt(0xFE)

    assert cpu.step() == 19
    assert (cpu.pc, cpu.wz, cpu.sp) == (0x5678, 0x5678, 0x3FFE)


def test_im0_accepts_device_rst_opcode_only() -> None:
    cpu = MemoryCPU()
    cpu.im, cpu.iff1, cpu.iff2, cpu.pc, cpu.sp = 0, True, True, 0x1234, 0x4000
    cpu.request_maskable_interrupt(0xEF)  # RST 28h

    assert cpu.step() == 13
    assert (cpu.pc, cpu.wz) == (0x0028, 0x0028)

    cpu = MemoryCPU()
    cpu.im, cpu.iff1 = 0, True
    cpu.request_maskable_interrupt(0x00)
    with pytest.raises(NotImplementedError, match="RST opcodes"):
        cpu.step()
    assert cpu.maskable_interrupt_pending is True


def test_interrupt_request_validates_and_can_be_cleared() -> None:
    cpu = MemoryCPU()
    with pytest.raises(ValueError, match=r"0x00\.\.0xFF"):
        cpu.request_maskable_interrupt(0x100)

    cpu.request_maskable_interrupt()
    cpu.clear_maskable_interrupt()
    assert cpu.maskable_interrupt_pending is False
