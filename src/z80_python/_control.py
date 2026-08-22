"""Control-flow and exchange instruction implementation."""


class ControlMixin:
    """Private jump, call, return, restart, and exchange implementation."""

    def _cond_true(self, cond: int) -> int:
        if cond == 0:
            return self.f.z == 0
        if cond == 1:
            return self.f.z == 1
        if cond == 2:
            return self.f.c == 0
        if cond == 3:
            return self.f.c == 1
        if cond == 4:
            return self.f.pv == 0
        if cond == 5:
            return self.f.pv == 1
        if cond == 6:
            return self.f.s == 0
        return self.f.s == 1

    def _op_jr(self, opcode: int) -> int:
        displacement = self._read_operand_byte()
        if displacement >= 0x80:
            displacement -= 0x100
        if opcode == 0x18:
            taken = True
        elif opcode == 0x20:
            taken = self.f.z == 0
        elif opcode == 0x28:
            taken = self.f.z == 1
        elif opcode == 0x30:
            taken = self.f.c == 0
        else:
            taken = self.f.c == 1
        if not taken:
            self._update_q(False)
            return 7
        self.wz = (self.pc + displacement) & 0xFFFF
        self.pc = self.wz
        self._update_q(False)
        return 12

    def _op_jp(self, opcode: int) -> int:
        self.wz = self._read_operand_word()
        if opcode == 0xC3 or self._cond_true((opcode >> 3) & 0x07):
            self.pc = self.wz
        self._update_q(False)
        return 10

    def _op_jp_hl(self) -> int:
        self.pc = self._hl()
        self._update_q(False)
        return 4

    def _op_ex_de_hl(self) -> int:
        de = self._de()
        self.d = self.h
        self.e = self.l
        self.h = (de >> 8) & 0xFF
        self.l = de & 0xFF
        self._update_q(False)
        return 4

    def _op_interrupt_enable(self, enabled: bool) -> int:
        """DI/EI -- update both interrupt-enable flip-flops."""
        self.iff1 = enabled
        self.iff2 = enabled
        self._ei_delay = 1 if enabled else 0
        self._update_q(False)
        return 4

    def _op_call(self, opcode: int) -> int:
        self.wz = self._read_operand_word()
        if opcode != 0xCD and not self._cond_true((opcode >> 3) & 0x07):
            self._update_q(False)
            return 10
        self._push_word(self.pc)
        self.pc = self.wz
        self._update_q(False)
        return 17

    def _op_ret(self) -> int:
        self.wz = self._pop_word()
        self.pc = self.wz
        self._update_q(False)
        return 10

    def _op_ret_cc(self, opcode: int) -> int:
        if not self._cond_true((opcode >> 3) & 0x07):
            self._update_q(False)
            return 5
        self.wz = self._pop_word()
        self.pc = self.wz
        self._update_q(False)
        return 11

    def _ret_iff(self) -> int:
        self.wz = self._pop_word()
        self.pc = self.wz
        self.iff1 = self.iff2
        self._update_q(False)
        return 14

    def _op_retn(self) -> int:
        return self._ret_iff()

    def _op_reti(self) -> int:
        return self._ret_iff()

    def _op_rst(self, opcode: int) -> int:
        self._push_word(self.pc)
        self.wz = ((opcode >> 3) & 0x07) << 3
        self.pc = self.wz
        self._update_q(False)
        return 11
