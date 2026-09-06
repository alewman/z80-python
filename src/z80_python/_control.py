"""Jump, call, return, restart, exchange, and CPU-control (NOP/HALT/DI/EI/IM) group."""


class ControlMixin:
    """Private control-flow, exchange, and CPU-control implementation."""

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
        """JR cc,e -- relative jump; JR e is the always-taken form. 12 T-states taken, 7 not."""
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
        # Unlike JP, the target is only computed (and latched into WZ) when the
        # branch is taken; a not-taken JR leaves WZ untouched.
        self.wz = (self.pc + displacement) & 0xFFFF
        self.pc = self.wz
        self._update_q(False)
        return 12

    def _op_jp(self, opcode: int) -> int:
        """JP cc,nn -- absolute jump; JP nn is the always-taken form. 10 T-states either way."""
        # The operand fetch itself latches nn into WZ, so WZ changes even when the
        # condition fails and the jump is not taken.
        self.wz = self._read_operand_word()
        if opcode == 0xC3 or self._cond_true((opcode >> 3) & 0x07):
            self.pc = self.wz
        self._update_q(False)
        return 10

    def _op_jp_hl(self) -> int:
        """JP (HL)"""
        self.pc = self._hl()
        self._update_q(False)
        return 4

    def _op_ex_de_hl(self) -> int:
        """EX DE,HL"""
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
        """CALL cc,nn -- CALL nn is the always-taken form. 17 T-states taken, 10 not."""
        # The operand fetch itself latches nn into WZ, so WZ changes even when the
        # condition fails and the jump is not taken.
        self.wz = self._read_operand_word()
        if opcode != 0xCD and not self._cond_true((opcode >> 3) & 0x07):
            self._update_q(False)
            return 10
        self._push_word(self.pc)
        self.pc = self.wz
        self._update_q(False)
        return 17

    def _op_ret(self) -> int:
        """RET"""
        self.wz = self._pop_word()
        self.pc = self.wz
        self._update_q(False)
        return 10

    def _op_ret_cc(self, opcode: int) -> int:
        """RET cc -- 11 T-states taken, 5 not."""
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
        """RETN -- return from NMI; restores IFF1 from IFF2."""
        return self._ret_iff()

    def _op_reti(self) -> int:
        """RETI -- return from maskable interrupt; restores IFF1 from IFF2 exactly like RETN."""
        return self._ret_iff()

    def _op_rst(self, opcode: int) -> int:
        """RST p"""
        self._push_word(self.pc)
        self.wz = ((opcode >> 3) & 0x07) << 3
        self.pc = self.wz
        self._update_q(False)
        return 11

    def _op_im(self, mode: int) -> int:
        """IM n -- select Z80 interrupt mode 0, 1, or 2."""
        self.im = mode
        self._update_q(False)
        return 8

    def _op_ed_nop(self) -> int:
        """NOP (undocumented ED-prefixed form) -- 8 T-states, no state change."""
        self._update_q(False)
        return 8

    def _op_exx(self) -> int:
        """EXX"""
        bc, de, hl = self._bc(), self._de(), self._hl()
        self._write_pair(0, self.bc_)
        self._write_pair(1, self.de_)
        self._write_pair(2, self.hl_)
        self.bc_, self.de_, self.hl_ = bc, de, hl
        self._update_q(False)
        return 4

    def _op_ex_sp_hl(self) -> int:
        """EX (SP),HL"""
        value = self.read_byte(self.sp) | (self.read_byte((self.sp + 1) & 0xFFFF) << 8)
        hl = self._hl()
        self.write_byte(self.sp, hl & 0xFF)
        self.write_byte((self.sp + 1) & 0xFFFF, hl >> 8)
        self.h = (value >> 8) & 0xFF
        self.l = value & 0xFF
        self.wz = value
        self._update_q(False)
        return 19

    def _op_halt(self) -> int:
        """HALT"""
        self.halted = True
        self._update_q(False)
        return 4

    def _op_nop(self) -> int:
        """NOP"""
        self._update_q(False)
        return 4

    def _op_ex_af_af(self) -> int:
        """EX AF,AF'"""
        af = (self.a << 8) | self.f.byte
        self.a = (self.af_ >> 8) & 0xFF
        self.f.byte = self.af_ & 0xFF
        self.af_ = af
        self._update_q(False)
        return 4

    def _op_djnz(self) -> int:
        """DJNZ e -- decrement B and branch if it is not zero; 13 T-states taken, 8 not."""
        displacement = self._read_operand_byte()
        if displacement >= 0x80:
            displacement -= 0x100
        self.b = (self.b - 1) & 0xFF
        if self.b:
            self.wz = (self.pc + displacement) & 0xFFFF
            self.pc = self.wz
            self._update_q(False)
            return 13
        self._update_q(False)
        return 8
