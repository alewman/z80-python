"""CPU state, fetch, stack, and register-selection helpers."""

from z80_python._flags import Flags


class CoreMixin:
    """Private implementation of CPU state and core helpers."""

    def __init__(self) -> None:
        self.a = 0
        self.f = Flags()
        self.b = 0
        self.c = 0
        self.d = 0
        self.e = 0
        self.h = 0
        self.l = 0
        self.ix = 0
        self.iy = 0
        self.sp = 0
        self.pc = 0
        self.wz = 0
        self.i = 0
        self.r = 0
        self.iff1 = False
        self.iff2 = False
        self.im = 0
        self.af_ = 0
        self.bc_ = 0
        self.de_ = 0
        self.hl_ = 0
        self.q = 0
        self._io_data = 0
        self.halted = False

    def _inc_r(self) -> None:
        self.r = (self.r & 0x80) | ((self.r + 1) & 0x7F)

    def _update_q(self, flags_modified: bool) -> None:
        self.q = self.f.byte if flags_modified else 0

    def _fetch_byte(self) -> int:
        value = self.read_byte(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        self._inc_r()
        return value

    def _read_operand_byte(self) -> int:
        value = self.read_byte(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def _read_operand_word(self) -> int:
        low = self._read_operand_byte()
        high = self._read_operand_byte()
        return (high << 8) | low

    def _push_word(self, value: int) -> None:
        self.sp = (self.sp - 1) & 0xFFFF
        self.write_byte(self.sp, (value >> 8) & 0xFF)
        self.sp = (self.sp - 1) & 0xFFFF
        self.write_byte(self.sp, value & 0xFF)

    def _pop_word(self) -> int:
        low = self.read_byte(self.sp)
        self.sp = (self.sp + 1) & 0xFFFF
        high = self.read_byte(self.sp)
        self.sp = (self.sp + 1) & 0xFFFF
        return (high << 8) | low

    def _hl(self) -> int:
        return (self.h << 8) | self.l

    def _bc(self) -> int:
        return (self.b << 8) | self.c

    def _de(self) -> int:
        return (self.d << 8) | self.e

    def _read_pair(self, index: int) -> int:
        if index == 0:
            return self._bc()
        if index == 1:
            return self._de()
        if index == 2:
            return self._hl()
        return self.sp

    def _write_pair(self, index: int, value: int) -> None:
        value &= 0xFFFF
        if index == 0:
            self.b = (value >> 8) & 0xFF
            self.c = value & 0xFF
        elif index == 1:
            self.d = (value >> 8) & 0xFF
            self.e = value & 0xFF
        elif index == 2:
            self.h = (value >> 8) & 0xFF
            self.l = value & 0xFF
        else:
            self.sp = value

    def _read_reg(self, index: int) -> int:
        if index == 0:
            return self.b
        if index == 1:
            return self.c
        if index == 2:
            return self.d
        if index == 3:
            return self.e
        if index == 4:
            return self.h
        if index == 5:
            return self.l
        if index == 7:
            return self.a
        raise ValueError("register index 6 ((HL)) has no direct register backing")

    def _write_reg(self, index: int, value: int) -> None:
        value &= 0xFF
        if index == 0:
            self.b = value
        elif index == 1:
            self.c = value
        elif index == 2:
            self.d = value
        elif index == 3:
            self.e = value
        elif index == 4:
            self.h = value
        elif index == 5:
            self.l = value
        elif index == 7:
            self.a = value
        else:
            raise ValueError("register index 6 ((HL)) has no direct register backing")
