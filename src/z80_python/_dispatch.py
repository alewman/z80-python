"""Top-level, base, CB, and ED opcode dispatch."""


class DispatchMixin:
    """Private instruction fetch and dispatch implementation."""

    def decode_and_execute(self) -> int:
        opcode = self._fetch_byte()
        if opcode == 0xCB:
            return self._execute_cb(self._fetch_byte())
        if opcode == 0xED:
            return self._execute_ed(self._fetch_byte())
        if opcode in (0xDD, 0xFD):
            return self._execute_index(opcode, self._fetch_byte())
        return self._execute_main(opcode)

    def _execute_cb(self, sub_opcode: int) -> int:
        if sub_opcode <= 0x3F:
            return self._op_rot(sub_opcode)
        if sub_opcode <= 0x7F:
            return self._op_bit(sub_opcode)
        if sub_opcode <= 0xBF:
            return self._op_res(sub_opcode)
        return self._op_set(sub_opcode)

    def _execute_main(self, opcode: int) -> int:
        if opcode == 0x00:
            return self._op_nop()
        if opcode in (0x01, 0x11, 0x21, 0x31):
            return self._op_ld_rr_nn(opcode)
        if opcode == 0x08:
            return self._op_ex_af_af()
        if opcode == 0x10:
            return self._op_djnz()
        if opcode == 0x76:
            return self._op_halt()
        if 0x40 <= opcode <= 0x7F and opcode != 0x76:
            return self._op_ld_r_r(opcode)
        if opcode in (0x06, 0x0E, 0x16, 0x1E, 0x26, 0x2E, 0x36, 0x3E):
            return self._op_ld_r_n(opcode)
        if opcode in (0x0A, 0x1A):
            return self._op_ld_a_irr(self._bc() if opcode == 0x0A else self._de())
        if opcode in (0x02, 0x12):
            return self._op_ld_irr_a(self._bc() if opcode == 0x02 else self._de())
        if opcode == 0x3A:
            return self._op_ld_a_inn()
        if opcode == 0x32:
            return self._op_ld_inn_a()
        if opcode in (0x37, 0x3F):
            return self._op_scf_ccf(opcode, prefixed=False)
        if opcode == 0x22:
            return self._op_ld_nn_hl()
        if opcode == 0x2A:
            return self._op_ld_hl_nn_from_mem()
        if opcode == 0xDB:
            return self._op_in_a_n()
        if opcode == 0xD3:
            return self._op_out_n_a()
        if 0x80 <= opcode <= 0xBF:
            return self._op_alu_r(opcode)
        if opcode in (0xC6, 0xCE, 0xD6, 0xDE, 0xE6, 0xEE, 0xF6, 0xFE):
            return self._op_alu_n(opcode)
        if opcode in (0x04, 0x0C, 0x14, 0x1C, 0x24, 0x2C, 0x3C):
            return self._op_inc_r(opcode)
        if opcode in (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x3D):
            return self._op_dec_r(opcode)
        if opcode == 0x34:
            return self._op_inc_hl()
        if opcode == 0x35:
            return self._op_dec_hl()
        if opcode == 0x27:
            return self._op_daa()
        if opcode == 0x2F:
            return self._op_cpl()
        if opcode == 0x07:
            return self._op_rlca()
        if opcode == 0x0F:
            return self._op_rrca()
        if opcode == 0x17:
            return self._op_rla()
        if opcode == 0x1F:
            return self._op_rra()
        if opcode in (0x09, 0x19, 0x29, 0x39):
            return self._op_add_hl_rr(opcode)
        if opcode in (0x03, 0x13, 0x23, 0x33):
            return self._op_inc_rr(opcode)
        if opcode in (0x0B, 0x1B, 0x2B, 0x3B):
            return self._op_dec_rr(opcode)
        if opcode in (0x18, 0x20, 0x28, 0x30, 0x38):
            return self._op_jr(opcode)
        if opcode in (0xC0, 0xC8, 0xD0, 0xD8, 0xE0, 0xE8, 0xF0, 0xF8):
            return self._op_ret_cc(opcode)
        if opcode == 0xC9:
            return self._op_ret()
        if opcode in (0xC2, 0xCA, 0xD2, 0xDA, 0xE2, 0xEA, 0xF2, 0xFA, 0xC3):
            return self._op_jp(opcode)
        if opcode in (0xC4, 0xCC, 0xD4, 0xDC, 0xE4, 0xEC, 0xF4, 0xFC, 0xCD):
            return self._op_call(opcode)
        if opcode in (0xC7, 0xCF, 0xD7, 0xDF, 0xE7, 0xEF, 0xF7, 0xFF):
            return self._op_rst(opcode)
        if opcode in (0xC1, 0xD1, 0xE1):
            return self._op_pop_rr(opcode)
        if opcode in (0xC5, 0xD5, 0xE5):
            return self._op_push_rr(opcode)
        if opcode == 0xF1:
            return self._op_pop_af()
        if opcode == 0xF5:
            return self._op_push_af()
        if opcode == 0xF9:
            return self._op_ld_sp_hl()
        if opcode == 0xD9:
            return self._op_exx()
        if opcode == 0xE3:
            return self._op_ex_sp_hl()
        if opcode == 0xE9:
            return self._op_jp_hl()
        if opcode == 0xEB:
            return self._op_ex_de_hl()
        if opcode == 0xF3:
            return self._op_interrupt_enable(False)
        if opcode == 0xFB:
            return self._op_interrupt_enable(True)
        raise NotImplementedError(
            f"unhandled opcode 0x{opcode:02X} at PC 0x{(self.pc - 1) & 0xFFFF:04X}"
        )

    def _execute_ed(self, opcode: int) -> int:
        # Explicit dispatch avoids rebuilding a dictionary of bound methods on
        # every ED instruction while keeping each opcode directly traceable.
        match opcode:
            case 0x47:
                return self._op_ld_i_a()
            case 0x4F:
                return self._op_ld_r_a()
            case 0x57:
                return self._op_ld_a_i()
            case 0x5F:
                return self._op_ld_a_r()
            case 0x67:
                return self._op_rrd()
            case 0x6F:
                return self._op_rld()
            case 0x77 | 0x7F:
                return self._op_ed_nop()
            case 0xA0:
                return self._op_ldi()
            case 0xA1:
                return self._op_cpi()
            case 0xA2:
                return self._op_ini()
            case 0xA3:
                return self._op_outi()
            case 0xA8:
                return self._op_ldd()
            case 0xA9:
                return self._op_cpd()
            case 0xAA:
                return self._op_ind()
            case 0xAB:
                return self._op_outd()
            case 0xB0:
                return self._op_ldir()
            case 0xB1:
                return self._op_cpir()
            case 0xB2:
                return self._op_inir()
            case 0xB3:
                return self._op_otir()
            case 0xB8:
                return self._op_lddr()
            case 0xB9:
                return self._op_cpdr()
            case 0xBA:
                return self._op_indr()
            case 0xBB:
                return self._op_otdr()
        if opcode in (0x45, 0x55, 0x65, 0x75):
            return self._op_retn()
        if opcode in (0x4D, 0x5D, 0x6D, 0x7D):
            return self._op_reti()
        if opcode in (0x4A, 0x5A, 0x6A, 0x7A):
            return self._op_adc_hl_rr(opcode)
        if opcode in (0x42, 0x52, 0x62, 0x72):
            return self._op_sbc_hl_rr(opcode)
        if opcode in (0x43, 0x53, 0x63, 0x73):
            return self._op_ld_nn_rr((opcode >> 4) & 0x03)
        if opcode in (0x4B, 0x5B, 0x6B, 0x7B):
            return self._op_ld_rr_nn_from_mem((opcode >> 4) & 0x03)
        if opcode in (0x46, 0x4E, 0x66, 0x6E):
            return self._op_im(0)
        if opcode in (0x56, 0x76):
            return self._op_im(1)
        if opcode in (0x5E, 0x7E):
            return self._op_im(2)
        if opcode in (0x44, 0x4C, 0x54, 0x5C, 0x64, 0x6C, 0x74, 0x7C):
            return self._op_neg()
        if 0x40 <= opcode <= 0x78 and (opcode & 0x07) == 0:
            return self._op_in_r_c(opcode)
        if 0x41 <= opcode <= 0x79 and (opcode & 0x07) == 1:
            return self._op_out_c_r(opcode)
        # Every ED-prefixed byte not otherwise defined is a genuine Z80 instruction
        # on real silicon: a 2-byte, 8 T-state no-op. Only 0x77/0x7F fell inside the
        # documented 0x40-0x7F block; the rest of the ED space needs the same rule.
        return self._op_ed_nop()
