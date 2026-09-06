"""Eight- and sixteen-bit arithmetic instruction implementation."""


class ALUMixin:
    """Private arithmetic and logic implementation."""

    def _set_sz(self, value: int) -> None:
        self.f.s = (value >> 7) & 1
        self.f.z = 1 if value == 0 else 0

    def _set_xysz(self, value: int) -> None:
        self.f.set_xy(value)
        self._set_sz(value)

    @staticmethod
    def _parity(value: int) -> int:
        value ^= value >> 4
        value ^= value >> 2
        value ^= value >> 1
        return 0 if (value & 1) else 1

    def _set_parity(self, value: int) -> None:
        self.f.pv = self._parity(value)

    def _add(self, x: int, y: int, carry: int) -> int:
        z = x + y + carry
        self.f.c = 1 if z > 0xFF else 0
        z &= 0xFF
        self.f.n = 0
        self.f.pv = ((((x ^ y) ^ 0xFF) & (x ^ z)) & 0x80) >> 7
        self.f.h = ((x ^ y ^ z) & 0x10) >> 4
        self._set_xysz(z)
        return z

    def _sub(self, x: int, y: int, carry: int) -> int:
        z = (x - y - carry) & 0x1FF
        self.f.c = 1 if z > 0xFF else 0
        z &= 0xFF
        self.f.n = 1
        self.f.pv = (((x ^ y) & (x ^ z)) & 0x80) >> 7
        self.f.h = ((x ^ y ^ z) & 0x10) >> 4
        self._set_xysz(z)
        return z

    def _and(self, x: int, y: int) -> int:
        z = x & y
        self.f.c = 0
        self.f.n = 0
        self._set_parity(z)
        self.f.h = 1
        self._set_xysz(z)
        return z

    def _or(self, x: int, y: int) -> int:
        z = x | y
        self.f.c = 0
        self.f.n = 0
        self.f.h = 0
        self._set_parity(z)
        self._set_xysz(z)
        return z

    def _xor(self, x: int, y: int) -> int:
        z = x ^ y
        self.f.c = 0
        self.f.n = 0
        self.f.h = 0
        self._set_parity(z)
        self._set_xysz(z)
        return z

    def _cp(self, x: int, y: int) -> None:
        z = (x - y) & 0x1FF
        self.f.c = 1 if z > 0xFF else 0
        z &= 0xFF
        self.f.n = 1
        # CP is a discarded SUB: X/Y sample the operand still on the internal bus,
        # not the thrown-away result.
        self.f.set_xy(y)
        self._set_sz(z)
        self.f.pv = (((x ^ y) & (x ^ z)) & 0x80) >> 7
        self.f.h = ((x ^ y ^ z) & 0x10) >> 4

    def _inc(self, x: int) -> int:
        z = (x + 1) & 0xFF
        self.f.n = 0
        self.f.pv = 1 if z == 0x80 else 0
        self._set_xysz(z)
        self.f.h = 1 if (z & 0x0F) == 0 else 0
        return z

    def _dec(self, x: int) -> int:
        z = (x - 1) & 0xFF
        self.f.n = 1
        self.f.pv = 1 if z == 0x7F else 0
        self._set_xysz(z)
        self.f.h = 1 if (z & 0x0F) == 0x0F else 0
        return z

    def _op_alu_r(self, opcode: int) -> int:
        """ADD/ADC/SUB/SBC/AND/XOR/OR/CP A,r -- 8-bit ALU with a register or (HL) operand."""
        group = (opcode >> 3) & 0x07
        src = opcode & 0x07
        if src == 6:
            value = self.read_byte(self._hl())
            t_states = 7
        else:
            value = self._read_reg(src)
            t_states = 4
        self._alu_a(group, value)
        self._update_q(True)
        return t_states

    def _op_alu_n(self, opcode: int) -> int:
        """ADD/ADC/SUB/SBC/AND/XOR/OR/CP A,n -- 8-bit ALU with an immediate operand."""
        group = {0xC6: 0, 0xCE: 1, 0xD6: 2, 0xDE: 3, 0xE6: 4, 0xEE: 5, 0xF6: 6, 0xFE: 7}[opcode]
        self._alu_a(group, self._read_operand_byte())
        self._update_q(True)
        return 7

    def _op_neg(self) -> int:
        """NEG -- replace A with its two's-complement negation."""
        self.a = self._sub(0, self.a, 0)
        self._update_q(True)
        return 8

    def _alu_a(self, group: int, value: int) -> None:
        if group == 0:
            self.a = self._add(self.a, value, 0)
        elif group == 1:
            self.a = self._add(self.a, value, self.f.c)
        elif group == 2:
            self.a = self._sub(self.a, value, 0)
        elif group == 3:
            self.a = self._sub(self.a, value, self.f.c)
        elif group == 4:
            self.a = self._and(self.a, value)
        elif group == 5:
            self.a = self._xor(self.a, value)
        elif group == 6:
            self.a = self._or(self.a, value)
        else:
            self._cp(self.a, value)

    def _op_inc_r(self, opcode: int) -> int:
        """INC r"""
        dest = (opcode >> 3) & 0x07
        self._write_reg(dest, self._inc(self._read_reg(dest)))
        self._update_q(True)
        return 4

    def _op_dec_r(self, opcode: int) -> int:
        """DEC r"""
        dest = (opcode >> 3) & 0x07
        self._write_reg(dest, self._dec(self._read_reg(dest)))
        self._update_q(True)
        return 4

    def _op_inc_hl(self) -> int:
        """INC (HL)"""
        addr = self._hl()
        self.write_byte(addr, self._inc(self.read_byte(addr)))
        self._update_q(True)
        return 11

    def _op_dec_hl(self) -> int:
        """DEC (HL)"""
        addr = self._hl()
        self.write_byte(addr, self._dec(self.read_byte(addr)))
        self._update_q(True)
        return 11

    def _op_daa(self) -> int:
        """DAA -- decimal-adjust A after a BCD ADD/SUB, steered by H, N, and C."""
        original = self.a
        # DAA: a tens digit above 9, or a carry out of it, means the BCD result
        # overflowed 99; correct by 0x60 (direction from N) and force C. The
        # second test does the same for the units digit via H and 0x06.
        if self.f.c or self.a > 0x99:
            self.a = (self.a + (-0x60 if self.f.n else 0x60)) & 0xFF
            self.f.c = 1
        if self.f.h or (self.a & 0x0F) > 0x09:
            self.a = (self.a + (-0x06 if self.f.n else 0x06)) & 0xFF
        self._set_parity(self.a)
        self._set_xysz(self.a)
        self.f.h = ((self.a ^ original) & 0x10) >> 4
        self._update_q(True)
        return 4

    def _op_cpl(self) -> int:
        """CPL -- complement A, setting H/N and X/Y from the result."""
        self.a ^= 0xFF
        self.f.h = 1
        self.f.n = 1
        self.f.set_xy(self.a)
        self._update_q(True)
        return 4

    def _op_scf_ccf(self, opcode: int, *, prefixed: bool) -> int:
        """SCF/CCF -- including their Q-sensitive undocumented X/Y behavior."""
        # Q holds F only if the previous M1 cycle wrote flags. If it did, F's X/Y
        # are masked and A alone supplies them; otherwise X/Y = (F | A). A DD/FD
        # prefix is its own M1 that writes no flags, so a prefixed SCF/CCF sees Q=0.
        if self.q and not prefixed:
            self.f.set_xy(0)
        old_carry = self.f.c
        if opcode == 0x37:
            self.f.c = 1
            self.f.h = 0
        else:
            self.f.c = old_carry ^ 1
            self.f.h = old_carry
        self.f.n = 0
        self.f.set_xy(self.f.byte | self.a)
        self._update_q(True)
        return 4

    def _add16(self, x: int, y: int, carry: int) -> int:
        result = x + y + carry
        self.f.c = 1 if result > 0xFFFF else 0
        result &= 0xFFFF
        self.f.n = 0
        self.f.h = ((x ^ y ^ result) & 0x1000) >> 12
        self.f.pv = ((((x ^ y) ^ 0xFFFF) & (x ^ result)) & 0x8000) >> 15
        self.f.s = (result >> 15) & 1
        self.f.z = 1 if result == 0 else 0
        self.f.set_xy((result >> 8) & 0xFF)
        return result

    def _sub16(self, x: int, y: int, carry: int) -> int:
        result = x - y - carry
        self.f.c = 1 if result < 0 else 0
        result &= 0xFFFF
        self.f.n = 1
        self.f.h = ((x ^ y ^ result) & 0x1000) >> 12
        self.f.pv = (((x ^ y) & (x ^ result)) & 0x8000) >> 15
        self.f.s = (result >> 15) & 1
        self.f.z = 1 if result == 0 else 0
        self.f.set_xy((result >> 8) & 0xFF)
        return result

    def _op_add_hl_rr(self, opcode: int) -> int:
        """ADD HL,rr -- only H, N, C and X/Y change; S/Z/PV are preserved."""
        pair_index = (opcode >> 4) & 0x03
        hl = self._hl()
        value = self._read_pair(pair_index)
        # 16-bit adds run through the address latch: WZ = HL + 1 (the high-byte pass).
        self.wz = (hl + 1) & 0xFFFF
        result = hl + value
        self.f.c = 1 if result > 0xFFFF else 0
        result &= 0xFFFF
        self.f.n = 0
        self.f.h = ((hl ^ value ^ result) & 0x1000) >> 12
        self.f.set_xy((result >> 8) & 0xFF)
        self._write_pair(2, result)
        self._update_q(True)
        return 11

    def _op_adc_hl_rr(self, opcode: int) -> int:
        """ADC HL,rr"""
        pair_index = (opcode >> 4) & 0x03
        hl = self._hl()
        # 16-bit adds run through the address latch: WZ = HL + 1 (the high-byte pass).
        self.wz = (hl + 1) & 0xFFFF
        self._write_pair(2, self._add16(hl, self._read_pair(pair_index), self.f.c))
        self._update_q(True)
        return 15

    def _op_sbc_hl_rr(self, opcode: int) -> int:
        """SBC HL,rr"""
        pair_index = (opcode >> 4) & 0x03
        hl = self._hl()
        # 16-bit adds run through the address latch: WZ = HL + 1 (the high-byte pass).
        self.wz = (hl + 1) & 0xFFFF
        self._write_pair(2, self._sub16(hl, self._read_pair(pair_index), self.f.c))
        self._update_q(True)
        return 15

    def _op_inc_rr(self, opcode: int) -> int:
        """INC rr -- no flags."""
        pair_index = (opcode >> 4) & 0x03
        self._write_pair(pair_index, (self._read_pair(pair_index) + 1) & 0xFFFF)
        self._update_q(False)
        return 6

    def _op_dec_rr(self, opcode: int) -> int:
        """DEC rr -- no flags."""
        pair_index = (opcode >> 4) & 0x03
        self._write_pair(pair_index, (self._read_pair(pair_index) - 1) & 0xFFFF)
        self._update_q(False)
        return 6
