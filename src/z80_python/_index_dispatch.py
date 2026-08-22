"""DD/FD index-prefix dispatcher."""


class IndexDispatchMixin:
    """Private dispatcher for currently implemented DD/FD opcodes."""

    def _execute_index(self, prefix: int, sub_opcode: int) -> int:
        if sub_opcode == 0xCB:
            displacement = self._read_operand_byte()
            cb_opcode = self._read_operand_byte()
            if cb_opcode <= 0x3F:
                return self._op_index_rot(prefix, displacement, cb_opcode)
            if 0x40 <= cb_opcode <= 0x7F:
                return self._op_index_bit(prefix, displacement, cb_opcode)
            if 0x80 <= cb_opcode <= 0xBF:
                return self._op_index_res_set(prefix, displacement, cb_opcode, set_bit=False)
            if cb_opcode >= 0xC0:
                return self._op_index_res_set(prefix, displacement, cb_opcode, set_bit=True)
            prefix_addr = (self.pc - 4) & 0xFFFF
            self.pc = (prefix_addr + 1) & 0xFFFF
            raise NotImplementedError(
                f"unhandled DDCB/FDCB opcode 0x{cb_opcode:02X} at PC 0x{prefix_addr:04X}"
            )
        if sub_opcode == 0x76:
            return self._op_halt() + 4
        if sub_opcode in (0x00, 0x01, 0x08, 0x10, 0x11, 0x31):
            return self._op_prefix_ignored_basic(sub_opcode) + 4
        if sub_opcode in (
            0x40,
            0x41,
            0x42,
            0x43,
            0x47,
            0x48,
            0x49,
            0x4A,
            0x4B,
            0x4F,
            0x50,
            0x51,
            0x52,
            0x53,
            0x57,
            0x58,
            0x59,
            0x5A,
            0x5B,
            0x5F,
            0x78,
            0x79,
            0x7A,
            0x7B,
            0x7F,
        ):
            return self._op_ld_r_r(sub_opcode) + 4
        if sub_opcode == 0x7C:
            return self._op_ld_a_index_h(prefix) + 4
        if sub_opcode == 0x7D:
            return self._op_ld_a_index_l(prefix) + 4
        if sub_opcode in (0x44, 0x45, 0x4C, 0x4D, 0x54, 0x55, 0x5C, 0x5D):
            return self._op_ld_r_index_byte(prefix, sub_opcode) + 4
        if sub_opcode in (0x64, 0x65, 0x6C, 0x6D):
            return self._op_ld_index_byte_index_byte(prefix, sub_opcode) + 4
        if sub_opcode in (0x60, 0x61, 0x62, 0x63, 0x67, 0x68, 0x69, 0x6A, 0x6B, 0x6F):
            return self._op_ld_index_byte_r(prefix, sub_opcode) + 4
        if sub_opcode in (0x26, 0x2E):
            return self._op_ld_index_byte_n(prefix, sub_opcode) + 4
        if sub_opcode in (0x24, 0x25, 0x2C, 0x2D):
            return self._op_inc_dec_index_byte(prefix, sub_opcode) + 4
        if sub_opcode in (0x04, 0x0C, 0x14, 0x1C, 0x3C):
            return self._op_inc_r(sub_opcode) + 4
        if sub_opcode in (0x05, 0x0D, 0x15, 0x1D, 0x3D):
            return self._op_dec_r(sub_opcode) + 4
        if sub_opcode in (0x03, 0x13, 0x33):
            return self._op_inc_rr(sub_opcode) + 4
        if sub_opcode in (0x0B, 0x1B, 0x3B):
            return self._op_dec_rr(sub_opcode) + 4
        if sub_opcode in (0x06, 0x0E, 0x16, 0x1E, 0x3E):
            return self._op_ld_r_n(sub_opcode) + 4
        if sub_opcode in (0x0A, 0x1A):
            return self._op_ld_a_irr(self._bc() if sub_opcode == 0x0A else self._de()) + 4
        if sub_opcode in (0x02, 0x12):
            return self._op_ld_irr_a(self._bc() if sub_opcode == 0x02 else self._de()) + 4
        if sub_opcode == 0x3A:
            return self._op_ld_a_inn() + 4
        if sub_opcode == 0x32:
            return self._op_ld_inn_a() + 4
        if sub_opcode == 0xDB:
            return self._op_in_a_n() + 4
        if sub_opcode == 0xD3:
            return self._op_out_n_a() + 4
        if sub_opcode in (0x18, 0x20, 0x28, 0x30, 0x38):
            return self._op_jr(sub_opcode) + 4
        if sub_opcode == 0x27:
            return self._op_daa() + 4
        if sub_opcode == 0x2F:
            return self._op_cpl() + 4
        if sub_opcode in (0x37, 0x3F):
            return self._op_scf_ccf(sub_opcode, prefixed=True) + 4
        if sub_opcode == 0x07:
            return self._op_rlca() + 4
        if sub_opcode == 0x0F:
            return self._op_rrca() + 4
        if sub_opcode == 0x17:
            return self._op_rla() + 4
        if sub_opcode == 0x1F:
            return self._op_rra() + 4

        plain_alu = {
            0x80,
            0x81,
            0x82,
            0x83,
            0x87,
            0x88,
            0x89,
            0x8A,
            0x8B,
            0x8F,
            0x90,
            0x91,
            0x92,
            0x93,
            0x97,
            0x98,
            0x99,
            0x9A,
            0x9B,
            0x9F,
            0xA0,
            0xA1,
            0xA2,
            0xA3,
            0xA7,
            0xA8,
            0xA9,
            0xAA,
            0xAB,
            0xAF,
            0xB0,
            0xB1,
            0xB2,
            0xB3,
            0xB7,
            0xB8,
            0xB9,
            0xBA,
            0xBB,
            0xBF,
        }
        if sub_opcode in plain_alu:
            return self._op_alu_r(sub_opcode) + 4
        indexed_register_alu = {
            0x84: self._op_add_a_index_h,
            0x85: self._op_add_a_index_l,
            0x8C: self._op_adc_a_index_h,
            0x8D: self._op_adc_a_index_l,
            0x94: self._op_sub_a_index_h,
            0x95: self._op_sub_a_index_l,
            0x9C: self._op_sbc_a_index_h,
            0x9D: self._op_sbc_a_index_l,
            0xA4: self._op_and_a_index_h,
            0xA5: self._op_and_a_index_l,
            0xAC: self._op_xor_a_index_h,
            0xAD: self._op_xor_a_index_l,
            0xB4: self._op_or_a_index_h,
            0xB5: self._op_or_a_index_l,
            0xBC: self._op_cp_a_index_h,
            0xBD: self._op_cp_a_index_l,
        }
        if sub_opcode in indexed_register_alu:
            return indexed_register_alu[sub_opcode](prefix) + 4

        if sub_opcode in (0x09, 0x19, 0x29, 0x39):
            return self._op_add_index_rr(prefix, sub_opcode)
        if sub_opcode == 0x21:
            return self._op_ld_index_nn(prefix)
        if sub_opcode == 0x22:
            return self._op_ld_nn_index(prefix)
        if sub_opcode == 0x23:
            return self._op_inc_index(prefix)
        if sub_opcode == 0x2A:
            return self._op_ld_index_nn_from_mem(prefix)
        if sub_opcode == 0x2B:
            return self._op_dec_index(prefix)
        if sub_opcode == 0x34:
            return self._op_inc_index_mem(prefix)
        if sub_opcode == 0x35:
            return self._op_dec_index_mem(prefix)
        if sub_opcode == 0x36:
            return self._op_ld_index_mem_n(prefix)
        if sub_opcode in (0x46, 0x4E, 0x56, 0x5E, 0x66, 0x6E, 0x7E):
            return self._op_ld_r_index_mem(prefix, sub_opcode)
        if sub_opcode in (0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x77):
            return self._op_ld_index_mem_r(prefix, sub_opcode)

        indexed_memory_alu = {
            0x86: self._op_add_a_index_mem,
            0x8E: self._op_adc_a_index_mem,
            0x96: self._op_sub_a_index_mem,
            0x9E: self._op_sbc_a_index_mem,
            0xA6: self._op_and_a_index_mem,
            0xAE: self._op_xor_a_index_mem,
            0xB6: self._op_or_a_index_mem,
            0xBE: self._op_cp_a_index_mem,
        }
        if sub_opcode in indexed_memory_alu:
            return indexed_memory_alu[sub_opcode](prefix)
        if sub_opcode in (0xC0, 0xC8, 0xD0, 0xD8, 0xE0, 0xE8, 0xF0, 0xF8):
            return self._op_ret_cc(sub_opcode) + 4
        if sub_opcode in (0xC2, 0xCA, 0xD2, 0xDA, 0xE2, 0xEA, 0xF2, 0xFA, 0xC3):
            return self._op_jp(sub_opcode) + 4
        if sub_opcode in (0xC4, 0xCC, 0xD4, 0xDC, 0xE4, 0xEC, 0xF4, 0xFC, 0xCD):
            return self._op_call(sub_opcode) + 4
        if sub_opcode == 0xC9:
            return self._op_ret() + 4
        if sub_opcode in (0xC7, 0xCF, 0xD7, 0xDF, 0xE7, 0xEF, 0xF7, 0xFF):
            return self._op_rst(sub_opcode) + 4
        if sub_opcode in (0xC6, 0xCE, 0xD6, 0xDE, 0xE6, 0xEE, 0xF6, 0xFE):
            return self._op_alu_n(sub_opcode) + 4
        if sub_opcode == 0xEB:
            return self._op_ex_de_hl() + 4
        if sub_opcode == 0xD1:
            return self._op_pop_rr(sub_opcode) + 4
        if sub_opcode == 0xD5:
            return self._op_push_rr(sub_opcode) + 4
        if sub_opcode == 0xD9:
            return self._op_exx() + 4
        if sub_opcode == 0xE1:
            return self._op_pop_index(prefix)
        if sub_opcode == 0xE3:
            return self._op_ex_sp_index(prefix)
        if sub_opcode == 0xE5:
            return self._op_push_index(prefix)
        if sub_opcode == 0xE9:
            return self._op_jp_index(prefix)
        if sub_opcode == 0xF1:
            return self._op_pop_af() + 4
        if sub_opcode == 0xF5:
            return self._op_push_af() + 4
        if sub_opcode == 0xF9:
            return self._op_ld_sp_index(prefix)
        if sub_opcode == 0xF3:
            return self._op_interrupt_enable(False) + 4
        if sub_opcode == 0xFB:
            return self._op_interrupt_enable(True) + 4

        if sub_opcode == 0xC1:
            return self._op_pop_rr(sub_opcode) + 4
        if sub_opcode == 0xC5:
            return self._op_push_rr(sub_opcode) + 4

        prefix_addr = (self.pc - 2) & 0xFFFF
        self.pc = (prefix_addr + 1) & 0xFFFF
        raise NotImplementedError(
            f"unhandled DD/FD opcode 0x{sub_opcode:02X} at PC 0x{prefix_addr:04X}"
        )
