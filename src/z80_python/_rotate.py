"""Rotate, shift, and bit-operation implementation."""


class RotateBitMixin:
    """Private rotate, shift, and bit implementation."""

    def _rlc(self, x: int) -> int:
        x = ((x << 1) | (x >> 7)) & 0xFF
        self.f.c = x & 1
        self.f.n = self.f.h = 0
        self._set_parity(x)
        self._set_xysz(x)
        return x

    def _rrc(self, x: int) -> int:
        x = ((x >> 1) | (x << 7)) & 0xFF
        self.f.c = (x >> 7) & 1
        self.f.n = self.f.h = 0
        self._set_parity(x)
        self._set_xysz(x)
        return x

    def _rl(self, x: int) -> int:
        carry = (x >> 7) & 1
        x = ((x << 1) | self.f.c) & 0xFF
        self.f.c = carry
        self.f.n = self.f.h = 0
        self._set_parity(x)
        self._set_xysz(x)
        return x

    def _rr(self, x: int) -> int:
        carry = x & 1
        x = ((x >> 1) | (self.f.c << 7)) & 0xFF
        self.f.c = carry
        self.f.n = self.f.h = 0
        self._set_parity(x)
        self._set_xysz(x)
        return x

    def _sla(self, x: int) -> int:
        carry = (x >> 7) & 1
        x = (x << 1) & 0xFF
        self.f.c = carry
        self.f.n = self.f.h = 0
        self._set_parity(x)
        self._set_xysz(x)
        return x

    def _sra(self, x: int) -> int:
        carry = x & 1
        x = (x & 0x80) | (x >> 1)
        self.f.c = carry
        self.f.n = self.f.h = 0
        self._set_parity(x)
        self._set_xysz(x)
        return x

    def _sll(self, x: int) -> int:
        carry = (x >> 7) & 1
        x = ((x << 1) | 1) & 0xFF
        self.f.c = carry
        self.f.n = self.f.h = 0
        self._set_parity(x)
        self._set_xysz(x)
        return x

    def _srl(self, x: int) -> int:
        carry = x & 1
        x >>= 1
        self.f.c = carry
        self.f.n = self.f.h = 0
        self._set_parity(x)
        self._set_xysz(x)
        return x

    def _rot_apply(self, group: int, value: int) -> int:
        operations = (
            self._rlc,
            self._rrc,
            self._rl,
            self._rr,
            self._sla,
            self._sra,
            self._sll,
            self._srl,
        )
        return operations[group](value)

    def _op_rot(self, sub_opcode: int) -> int:
        """RLC/RRC/RL/RR/SLA/SRA/SLL/SRL r -- CB-prefixed rotates and shifts, including (HL)."""
        group = (sub_opcode >> 3) & 0x07
        dest = sub_opcode & 0x07
        if dest == 6:
            addr = self._hl()
            self.write_byte(addr, self._rot_apply(group, self.read_byte(addr)))
            self._update_q(True)
            return 15
        self._write_reg(dest, self._rot_apply(group, self._read_reg(dest)))
        self._update_q(True)
        return 8

    def _op_rlca(self) -> int:
        """RLCA"""
        self.a = ((self.a << 1) | (self.a >> 7)) & 0xFF
        self.f.c = self.a & 1
        self.f.n = self.f.h = 0
        self.f.set_xy(self.a)
        self._update_q(True)
        return 4

    def _op_rrca(self) -> int:
        """RRCA"""
        self.f.c = self.a & 1
        self.a = ((self.a >> 1) | (self.a << 7)) & 0xFF
        self.f.n = self.f.h = 0
        self.f.set_xy(self.a)
        self._update_q(True)
        return 4

    def _op_rla(self) -> int:
        """RLA"""
        carry_in = self.f.c
        self.f.c = (self.a >> 7) & 1
        self.a = ((self.a << 1) | carry_in) & 0xFF
        self.f.n = self.f.h = 0
        self.f.set_xy(self.a)
        self._update_q(True)
        return 4

    def _op_rra(self) -> int:
        """RRA"""
        carry_in = self.f.c
        self.f.c = self.a & 1
        self.a = ((self.a >> 1) | (carry_in << 7)) & 0xFF
        self.f.n = self.f.h = 0
        self.f.set_xy(self.a)
        self._update_q(True)
        return 4

    def _op_bit(self, sub_opcode: int) -> int:
        """BIT b,r -- includes BIT b,(HL)."""
        bit_index = (sub_opcode >> 3) & 0x07
        src = sub_opcode & 0x07
        if src == 6:
            value = self.read_byte(self._hl())
            # X/Y sample the internal address bus during the read: WZ's high byte, not
            # the tested byte. Register forms below take them from the value itself.
            xy_source = (self.wz >> 8) & 0xFF
            t_states = 12
        else:
            value = self._read_reg(src)
            xy_source = value
            t_states = 8
        bit_set = (value >> bit_index) & 1
        self.f.n = 0
        self.f.h = 1
        self.f.z = 0 if bit_set else 1
        self.f.pv = self.f.z
        self.f.s = 1 if (bit_index == 7 and bit_set) else 0
        self.f.set_xy(xy_source)
        self._update_q(True)
        return t_states

    def _op_res(self, sub_opcode: int) -> int:
        """RES b,r -- includes RES b,(HL)."""
        bit_index = (sub_opcode >> 3) & 0x07
        dest = sub_opcode & 0x07
        mask = ~(1 << bit_index) & 0xFF
        if dest == 6:
            addr = self._hl()
            self.write_byte(addr, self.read_byte(addr) & mask)
            t_states = 15
        else:
            self._write_reg(dest, self._read_reg(dest) & mask)
            t_states = 8
        self._update_q(False)
        return t_states

    def _op_set(self, sub_opcode: int) -> int:
        """SET b,r -- includes SET b,(HL)."""
        bit_index = (sub_opcode >> 3) & 0x07
        dest = sub_opcode & 0x07
        mask = 1 << bit_index
        if dest == 6:
            addr = self._hl()
            self.write_byte(addr, self.read_byte(addr) | mask)
            t_states = 15
        else:
            self._write_reg(dest, self._read_reg(dest) | mask)
            t_states = 8
        self._update_q(False)
        return t_states

    def _op_rrd(self) -> int:
        """RRD -- rotate the BCD digit chain A[3:0] -> (HL)[7:4] -> (HL)[3:0] -> A[3:0] right."""
        addr = self._hl()
        self.wz = (addr + 1) & 0xFFFF
        data = self.read_byte(addr)
        self.write_byte(addr, ((data >> 4) | (self.a << 4)) & 0xFF)
        self.a = (self.a & 0xF0) | (data & 0x0F)
        self.f.n = self.f.h = 0
        self._set_parity(self.a)
        self._set_xysz(self.a)
        self._update_q(True)
        return 18

    def _op_rld(self) -> int:
        """RLD -- rotate the BCD digit chain A[3:0] -> (HL)[3:0] -> (HL)[7:4] -> A[3:0] left."""
        addr = self._hl()
        self.wz = (addr + 1) & 0xFFFF
        data = self.read_byte(addr)
        self.write_byte(addr, ((data << 4) | (self.a & 0x0F)) & 0xFF)
        self.a = (self.a & 0xF0) | (data >> 4)
        self.f.n = self.f.h = 0
        self._set_parity(self.a)
        self._set_xysz(self.a)
        self._update_q(True)
        return 18
