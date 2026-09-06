"""8-bit and 16-bit load group, including PUSH/POP (Zilog files the stack transfers here)."""


class LoadMixin:
    """Private load-family implementation."""

    def _op_ld_r_r(self, opcode: int) -> int:
        """LD r,r' -- includes the (HL) source and destination forms."""
        dest = (opcode >> 3) & 0x07
        src = opcode & 0x07
        t_states = 4
        if src == 6:
            value = self.read_byte(self._hl())
            t_states = 7
        else:
            value = self._read_reg(src)
        if dest == 6:
            self.write_byte(self._hl(), value)
            t_states = 7
        else:
            self._write_reg(dest, value)
        self._update_q(False)
        return t_states

    def _op_ld_r_n(self, opcode: int) -> int:
        """LD r,n -- includes LD (HL),n."""
        value = self._read_operand_byte()
        dest = (opcode >> 3) & 0x07
        if dest == 6:
            self.write_byte(self._hl(), value)
            t_states = 10
        else:
            self._write_reg(dest, value)
            t_states = 7
        self._update_q(False)
        return t_states

    def _op_ld_a_irr(self, reg16: int) -> int:
        """LD A,(BC)/(DE)"""
        self.wz = reg16
        self.a = self.read_byte(self.wz)
        self.wz = (self.wz + 1) & 0xFFFF
        self._update_q(False)
        return 7

    def _op_ld_irr_a(self, reg16: int) -> int:
        """LD (BC)/(DE),A"""
        self.wz = reg16
        self.write_byte(self.wz, self.a)
        # After the write the address latch increments its low byte only, and its
        # high byte is overwritten by A (the data bus value): WZ = A:(addr+1)&FF.
        self.wz = ((self.a << 8) | ((self.wz + 1) & 0xFF)) & 0xFFFF
        self._update_q(False)
        return 7

    def _op_ld_a_inn(self) -> int:
        """LD A,(nn)"""
        self.wz = self._read_operand_word()
        self.a = self.read_byte(self.wz)
        self.wz = (self.wz + 1) & 0xFFFF
        self._update_q(False)
        return 13

    def _op_ld_inn_a(self) -> int:
        """LD (nn),A"""
        self.wz = self._read_operand_word()
        self.write_byte(self.wz, self.a)
        # After the write the address latch increments its low byte only, and its
        # high byte is overwritten by A (the data bus value): WZ = A:(addr+1)&FF.
        self.wz = ((self.a << 8) | ((self.wz + 1) & 0xFF)) & 0xFFFF
        self._update_q(False)
        return 13

    def _op_ld_i_a(self) -> int:
        """LD I,A"""
        self.i = self.a
        self._update_q(False)
        return 9

    def _op_ld_r_a(self) -> int:
        """LD R,A"""
        self.r = self.a
        self._update_q(False)
        return 9

    def _op_ld_a_i(self) -> int:
        """LD A,I -- the only load that sets flags; PV mirrors IFF2."""
        value = self.i
        self.a = value
        self.f.n = self.f.h = 0
        # PV reports IFF2, the only way software can read the interrupt-enable state.
        self.f.pv = 1 if self.iff2 else 0
        self.f.set_xy(value)
        self.f.s = (value >> 7) & 1
        self.f.z = 1 if value == 0 else 0
        self._update_q(True)
        return 9

    def _op_ld_a_r(self) -> int:
        """LD A,R -- the only load that sets flags; PV mirrors IFF2."""
        value = self.r
        self.a = value
        self.f.n = self.f.h = 0
        # PV reports IFF2, the only way software can read the interrupt-enable state.
        self.f.pv = 1 if self.iff2 else 0
        self.f.set_xy(value)
        self.f.s = (value >> 7) & 1
        self.f.z = 1 if value == 0 else 0
        self._update_q(True)
        return 9

    def _op_ld_nn_hl(self) -> int:
        """LD (nn),HL"""
        addr = self._read_operand_word()
        self.write_byte(addr, self.l)
        self.wz = (addr + 1) & 0xFFFF
        self.write_byte(self.wz, self.h)
        self._update_q(False)
        return 16

    def _op_ld_hl_nn_from_mem(self) -> int:
        """LD HL,(nn)"""
        addr = self._read_operand_word()
        self.l = self.read_byte(addr)
        self.wz = (addr + 1) & 0xFFFF
        self.h = self.read_byte(self.wz)
        self._update_q(False)
        return 16

    def _op_ld_nn_rr(self, pair_index: int) -> int:
        """LD (nn),rr for the ED-prefixed register-pair transfer forms."""
        addr = self._read_operand_word()
        value = self._read_pair(pair_index)
        self.write_byte(addr, value & 0xFF)
        self.wz = (addr + 1) & 0xFFFF
        self.write_byte(self.wz, value >> 8)
        self._update_q(False)
        return 20

    def _op_ld_rr_nn_from_mem(self, pair_index: int) -> int:
        """LD rr,(nn) for the ED-prefixed register-pair transfer forms."""
        addr = self._read_operand_word()
        low = self.read_byte(addr)
        self.wz = (addr + 1) & 0xFFFF
        self._write_pair(pair_index, low | (self.read_byte(self.wz) << 8))
        self._update_q(False)
        return 20

    def _op_ld_sp_hl(self) -> int:
        """LD SP,HL -- copy HL into SP."""
        self.sp = self._hl()
        self._update_q(False)
        return 6

    def _op_pop_rr(self, sub_opcode: int) -> int:
        """POP rr"""
        self._write_pair((sub_opcode >> 4) & 0x03, self._pop_word())
        self._update_q(False)
        return 10

    def _op_push_rr(self, sub_opcode: int) -> int:
        """PUSH rr"""
        self._push_word(self._read_pair((sub_opcode >> 4) & 0x03))
        self._update_q(False)
        return 11

    def _op_pop_af(self) -> int:
        """POP AF"""
        value = self._pop_word()
        self.a = (value >> 8) & 0xFF
        self.f.byte = value & 0xFF
        self._update_q(False)
        return 10

    def _op_push_af(self) -> int:
        """PUSH AF"""
        self._push_word((self.a << 8) | self.f.byte)
        self._update_q(False)
        return 11

    def _op_ld_rr_nn(self, opcode: int) -> int:
        """LD rr,nn -- BC, DE, HL, or SP from a 16-bit immediate."""
        self._write_pair((opcode >> 4) & 0x03, self._read_operand_word())
        self._update_q(False)
        return 10
