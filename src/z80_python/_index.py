"""IX/IY instruction handlers: every handler here names an IX or IY operand.

Base-set instructions that a DD/FD prefix merely decorates live with their own
instruction group; ``_index_dispatch.py`` routes them and adds the prefix cost.
"""


class IndexMixin:
    """Private IX/IY helper and instruction implementation."""

    def _get_index(self, prefix: int) -> int:
        return self.ix if prefix == 0xDD else self.iy

    def _set_index(self, prefix: int, value: int) -> None:
        value &= 0xFFFF
        if prefix == 0xDD:
            self.ix = value
        else:
            self.iy = value

    def _index_high_byte(self, prefix: int) -> int:
        return (self._get_index(prefix) >> 8) & 0xFF

    def _index_low_byte(self, prefix: int) -> int:
        return self._get_index(prefix) & 0xFF

    def _set_index_high_byte(self, prefix: int, value: int) -> None:
        self._set_index(prefix, ((value & 0xFF) << 8) | self._index_low_byte(prefix))

    def _set_index_low_byte(self, prefix: int, value: int) -> None:
        self._set_index(prefix, (self._index_high_byte(prefix) << 8) | (value & 0xFF))

    def _op_add_index_rr(self, prefix: int, sub_opcode: int) -> int:
        """ADD IX/IY,rr -- rr = BC, DE, the index register itself, or SP."""
        pair_index = (sub_opcode >> 4) & 0x03
        index = self._get_index(prefix)
        value = index if pair_index == 2 else self._read_pair(pair_index)
        self.wz = (index + 1) & 0xFFFF
        result = index + value
        self.f.c = 1 if result > 0xFFFF else 0
        result &= 0xFFFF
        self.f.n = 0
        self.f.h = ((index ^ value ^ result) & 0x1000) >> 12
        self.f.set_xy((result >> 8) & 0xFF)
        self._set_index(prefix, result)
        self._update_q(True)
        return 15

    def _op_ld_index_nn(self, prefix: int) -> int:
        """LD IX/IY,nn"""
        self._set_index(prefix, self._read_operand_word())
        self._update_q(False)
        return 14

    def _op_ld_nn_index(self, prefix: int) -> int:
        """LD (nn),IX/IY"""
        addr = self._read_operand_word()
        index = self._get_index(prefix)
        self.write_byte(addr, index & 0xFF)
        self.wz = (addr + 1) & 0xFFFF
        self.write_byte(self.wz, index >> 8)
        self._update_q(False)
        return 20

    def _op_ld_index_nn_from_mem(self, prefix: int) -> int:
        """LD IX/IY,(nn)"""
        addr = self._read_operand_word()
        low = self.read_byte(addr)
        self.wz = (addr + 1) & 0xFFFF
        self._set_index(prefix, low | (self.read_byte(self.wz) << 8))
        self._update_q(False)
        return 20

    def _op_ld_a_index_h(self, prefix: int) -> int:
        """LD A,IXH/IYH"""
        self.a = self._index_high_byte(prefix)
        self._update_q(False)
        return 4

    def _op_ld_a_index_l(self, prefix: int) -> int:
        """LD A,IXL/IYL"""
        self.a = self._index_low_byte(prefix)
        self._update_q(False)
        return 4

    def _op_ld_r_index_byte(self, prefix: int, sub_opcode: int) -> int:
        """LD r,IXH/IXL/IYH/IYL"""
        value = (
            self._index_high_byte(prefix)
            if (sub_opcode & 0x07) == 4
            else self._index_low_byte(prefix)
        )
        self._write_reg((sub_opcode >> 3) & 0x07, value)
        self._update_q(False)
        return 4

    def _op_ld_index_byte_index_byte(self, prefix: int, sub_opcode: int) -> int:
        """LD IXH/IXL,IXH/IXL (and the IY forms)"""
        value = (
            self._index_high_byte(prefix)
            if (sub_opcode & 0x07) == 4
            else self._index_low_byte(prefix)
        )
        if ((sub_opcode >> 3) & 0x07) == 4:
            self._set_index_high_byte(prefix, value)
        else:
            self._set_index_low_byte(prefix, value)
        self._update_q(False)
        return 4

    def _op_ld_index_byte_r(self, prefix: int, sub_opcode: int) -> int:
        """LD IXH/IXL/IYH/IYL,r"""
        value = self._read_reg(sub_opcode & 0x07)
        if ((sub_opcode >> 3) & 0x07) == 4:
            self._set_index_high_byte(prefix, value)
        else:
            self._set_index_low_byte(prefix, value)
        self._update_q(False)
        return 4

    def _op_ld_index_byte_n(self, prefix: int, sub_opcode: int) -> int:
        """LD IXH/IXL/IYH/IYL,n"""
        value = self._read_operand_byte()
        if ((sub_opcode >> 3) & 0x07) == 4:
            self._set_index_high_byte(prefix, value)
        else:
            self._set_index_low_byte(prefix, value)
        self._update_q(False)
        return 7

    def _op_inc_dec_index_byte(self, prefix: int, sub_opcode: int) -> int:
        """INC/DEC IXH/IXL/IYH/IYL"""
        is_high_byte = ((sub_opcode >> 3) & 0x07) == 4
        value = self._index_high_byte(prefix) if is_high_byte else self._index_low_byte(prefix)
        result = self._inc(value) if (sub_opcode & 0x07) == 4 else self._dec(value)
        if is_high_byte:
            self._set_index_high_byte(prefix, result)
        else:
            self._set_index_low_byte(prefix, result)
        self._update_q(True)
        return 4

    def _op_add_a_index_h(self, prefix: int) -> int:
        """ADD A,IXH/IYH"""
        self._alu_a(0, self._index_high_byte(prefix))
        self._update_q(True)
        return 4

    def _op_add_a_index_l(self, prefix: int) -> int:
        """ADD A,IXL/IYL"""
        self._alu_a(0, self._index_low_byte(prefix))
        self._update_q(True)
        return 4

    def _op_adc_a_index_h(self, prefix: int) -> int:
        """ADC A,IXH/IYH"""
        self._alu_a(1, self._index_high_byte(prefix))
        self._update_q(True)
        return 4

    def _op_adc_a_index_l(self, prefix: int) -> int:
        """ADC A,IXL/IYL"""
        self._alu_a(1, self._index_low_byte(prefix))
        self._update_q(True)
        return 4

    def _op_sub_a_index_h(self, prefix: int) -> int:
        """SUB A,IXH/IYH"""
        self._alu_a(2, self._index_high_byte(prefix))
        self._update_q(True)
        return 4

    def _op_sub_a_index_l(self, prefix: int) -> int:
        """SUB A,IXL/IYL"""
        self._alu_a(2, self._index_low_byte(prefix))
        self._update_q(True)
        return 4

    def _op_sbc_a_index_h(self, prefix: int) -> int:
        """SBC A,IXH/IYH"""
        self._alu_a(3, self._index_high_byte(prefix))
        self._update_q(True)
        return 4

    def _op_sbc_a_index_l(self, prefix: int) -> int:
        """SBC A,IXL/IYL"""
        self._alu_a(3, self._index_low_byte(prefix))
        self._update_q(True)
        return 4

    def _op_and_a_index_h(self, prefix: int) -> int:
        """AND A,IXH/IYH"""
        self._alu_a(4, self._index_high_byte(prefix))
        self._update_q(True)
        return 4

    def _op_and_a_index_l(self, prefix: int) -> int:
        """AND A,IXL/IYL"""
        self._alu_a(4, self._index_low_byte(prefix))
        self._update_q(True)
        return 4

    def _op_xor_a_index_h(self, prefix: int) -> int:
        """XOR A,IXH/IYH"""
        self._alu_a(5, self._index_high_byte(prefix))
        self._update_q(True)
        return 4

    def _op_xor_a_index_l(self, prefix: int) -> int:
        """XOR A,IXL/IYL"""
        self._alu_a(5, self._index_low_byte(prefix))
        self._update_q(True)
        return 4

    def _op_or_a_index_h(self, prefix: int) -> int:
        """OR A,IXH/IYH"""
        self._alu_a(6, self._index_high_byte(prefix))
        self._update_q(True)
        return 4

    def _op_or_a_index_l(self, prefix: int) -> int:
        """OR A,IXL/IYL"""
        self._alu_a(6, self._index_low_byte(prefix))
        self._update_q(True)
        return 4

    def _op_cp_a_index_h(self, prefix: int) -> int:
        """CP A,IXH/IYH"""
        self._alu_a(7, self._index_high_byte(prefix))
        self._update_q(True)
        return 4

    def _op_cp_a_index_l(self, prefix: int) -> int:
        """CP A,IXL/IYL"""
        self._alu_a(7, self._index_low_byte(prefix))
        self._update_q(True)
        return 4

    def _op_inc_index(self, prefix: int) -> int:
        """INC IX/IY -- no flags."""
        self._set_index(prefix, self._get_index(prefix) + 1)
        self._update_q(False)
        return 10

    def _op_dec_index(self, prefix: int) -> int:
        """DEC IX/IY -- no flags."""
        self._set_index(prefix, self._get_index(prefix) - 1)
        self._update_q(False)
        return 10

    def _op_pop_index(self, prefix: int) -> int:
        """POP IX/IY"""
        self._set_index(prefix, self._pop_word())
        self._update_q(False)
        return 14

    def _op_push_index(self, prefix: int) -> int:
        """PUSH IX/IY"""
        self._push_word(self._get_index(prefix))
        self._update_q(False)
        return 15

    def _op_ex_sp_index(self, prefix: int) -> int:
        """EX (SP),IX/IY"""
        value = self.read_byte(self.sp) | (self.read_byte((self.sp + 1) & 0xFFFF) << 8)
        index = self._get_index(prefix)
        self.write_byte((self.sp + 1) & 0xFFFF, index >> 8)
        self.write_byte(self.sp, index & 0xFF)
        self._set_index(prefix, value)
        self.wz = value
        self._update_q(False)
        return 23

    def _op_jp_index(self, prefix: int) -> int:
        """JP (IX)/(IY)"""
        self.pc = self._get_index(prefix)
        self._update_q(False)
        return 8

    def _op_ld_sp_index(self, prefix: int) -> int:
        """LD SP,IX/IY"""
        self.sp = self._get_index(prefix)
        self._update_q(False)
        return 10

    def _index_displacement_addr(self, prefix: int) -> int:
        displacement = self._read_operand_byte()
        if displacement >= 0x80:
            displacement -= 0x100
        addr = (self._get_index(prefix) + displacement) & 0xFFFF
        self.wz = addr
        return addr

    def _op_index_bit(self, prefix: int, displacement: int, sub_opcode: int) -> int:
        """BIT b,(IX+d)/(IY+d)"""
        if displacement >= 0x80:
            displacement -= 0x100
        self.wz = (self._get_index(prefix) + displacement) & 0xFFFF
        value = self.read_byte(self.wz)
        bit_index = (sub_opcode >> 3) & 0x07
        bit_set = (value >> bit_index) & 1
        self.f.n = 0
        self.f.h = 1
        self.f.z = 0 if bit_set else 1
        self.f.pv = self.f.z
        self.f.s = 1 if bit_index == 7 and bit_set else 0
        self.f.set_xy(self.wz >> 8)
        self._update_q(True)
        return 20

    def _op_index_rot(self, prefix: int, displacement: int, sub_opcode: int) -> int:
        """RLC/RRC/RL/RR/SLA/SRA/SLL/SRL (IX+d)/(IY+d) -- undocumented forms also copy into r."""
        if displacement >= 0x80:
            displacement -= 0x100
        self.wz = (self._get_index(prefix) + displacement) & 0xFFFF
        value = self._rot_apply((sub_opcode >> 3) & 0x07, self.read_byte(self.wz))
        self.write_byte(self.wz, value)
        dest = sub_opcode & 0x07
        if dest != 6:
            self._write_reg(dest, value)
        self._update_q(True)
        return 23

    def _op_index_res_set(
        self, prefix: int, displacement: int, sub_opcode: int, *, set_bit: bool
    ) -> int:
        """RES/SET b,(IX+d)/(IY+d) -- the undocumented forms also copy the result into r."""
        if displacement >= 0x80:
            displacement -= 0x100
        self.wz = (self._get_index(prefix) + displacement) & 0xFFFF
        mask = 1 << ((sub_opcode >> 3) & 0x07)
        value = self.read_byte(self.wz)
        value = value | mask if set_bit else value & ~mask
        self.write_byte(self.wz, value)
        dest = sub_opcode & 0x07
        if dest != 6:
            self._write_reg(dest, value)
        self._update_q(False)
        return 23

    def _op_inc_index_mem(self, prefix: int) -> int:
        """INC (IX+d)/(IY+d)"""
        addr = self._index_displacement_addr(prefix)
        self.write_byte(addr, self._inc(self.read_byte(addr)))
        self._update_q(True)
        return 23

    def _op_dec_index_mem(self, prefix: int) -> int:
        """DEC (IX+d)/(IY+d)"""
        addr = self._index_displacement_addr(prefix)
        self.write_byte(addr, self._dec(self.read_byte(addr)))
        self._update_q(True)
        return 23

    def _op_ld_r_index_mem(self, prefix: int, sub_opcode: int) -> int:
        """LD r,(IX+d)/(IY+d)"""
        dest = (sub_opcode >> 3) & 0x07
        addr = self._index_displacement_addr(prefix)
        self._write_reg(dest, self.read_byte(addr))
        self._update_q(False)
        return 19

    def _op_ld_index_mem_r(self, prefix: int, sub_opcode: int) -> int:
        """LD (IX+d)/(IY+d),r"""
        src = sub_opcode & 0x07
        addr = self._index_displacement_addr(prefix)
        self.write_byte(addr, self._read_reg(src))
        self._update_q(False)
        return 19

    def _op_ld_index_mem_n(self, prefix: int) -> int:
        """LD (IX+d)/(IY+d),n"""
        addr = self._index_displacement_addr(prefix)
        self.write_byte(addr, self._read_operand_byte())
        self._update_q(False)
        return 19

    def _indexed_alu(self, prefix: int, group: int) -> int:
        addr = self._index_displacement_addr(prefix)
        self._alu_a(group, self.read_byte(addr))
        self._update_q(True)
        return 19

    def _op_add_a_index_mem(self, prefix: int) -> int:
        """ADD A,(IX+d)/(IY+d)"""
        return self._indexed_alu(prefix, 0)

    def _op_adc_a_index_mem(self, prefix: int) -> int:
        """ADC A,(IX+d)/(IY+d)"""
        return self._indexed_alu(prefix, 1)

    def _op_sub_a_index_mem(self, prefix: int) -> int:
        """SUB A,(IX+d)/(IY+d)"""
        return self._indexed_alu(prefix, 2)

    def _op_sbc_a_index_mem(self, prefix: int) -> int:
        """SBC A,(IX+d)/(IY+d)"""
        return self._indexed_alu(prefix, 3)

    def _op_and_a_index_mem(self, prefix: int) -> int:
        """AND A,(IX+d)/(IY+d)"""
        return self._indexed_alu(prefix, 4)

    def _op_xor_a_index_mem(self, prefix: int) -> int:
        """XOR A,(IX+d)/(IY+d)"""
        return self._indexed_alu(prefix, 5)

    def _op_or_a_index_mem(self, prefix: int) -> int:
        """OR A,(IX+d)/(IY+d)"""
        return self._indexed_alu(prefix, 6)

    def _op_cp_a_index_mem(self, prefix: int) -> int:
        """CP A,(IX+d)/(IY+d)"""
        return self._indexed_alu(prefix, 7)
