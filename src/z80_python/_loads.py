"""Load and HALT instruction implementation."""


class LoadMixin:
    """Private load-family implementation."""

    def _op_halt(self) -> int:
        self.halted = True
        self._update_q(False)
        return 4

    def _op_ld_r_r(self, opcode: int) -> int:
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
        self.wz = reg16
        self.a = self.read_byte(self.wz)
        self.wz = (self.wz + 1) & 0xFFFF
        self._update_q(False)
        return 7

    def _op_ld_irr_a(self, reg16: int) -> int:
        self.wz = reg16
        self.write_byte(self.wz, self.a)
        self.wz = ((self.a << 8) | ((self.wz + 1) & 0xFF)) & 0xFFFF
        self._update_q(False)
        return 7

    def _op_ld_a_inn(self) -> int:
        self.wz = self._read_operand_word()
        self.a = self.read_byte(self.wz)
        self.wz = (self.wz + 1) & 0xFFFF
        self._update_q(False)
        return 13

    def _op_ld_inn_a(self) -> int:
        self.wz = self._read_operand_word()
        self.write_byte(self.wz, self.a)
        self.wz = ((self.a << 8) | ((self.wz + 1) & 0xFF)) & 0xFFFF
        self._update_q(False)
        return 13

    def _op_ld_i_a(self) -> int:
        self.i = self.a
        self._update_q(False)
        return 9

    def _op_ld_r_a(self) -> int:
        self.r = self.a
        self._update_q(False)
        return 9

    def _op_ld_a_i(self) -> int:
        value = self.i
        self.a = value
        self.f.n = self.f.h = 0
        self.f.pv = 1 if self.iff2 else 0
        self.f.set_xy(value)
        self.f.s = (value >> 7) & 1
        self.f.z = 1 if value == 0 else 0
        self._update_q(True)
        return 9

    def _op_ld_a_r(self) -> int:
        value = self.r
        self.a = value
        self.f.n = self.f.h = 0
        self.f.pv = 1 if self.iff2 else 0
        self.f.set_xy(value)
        self.f.s = (value >> 7) & 1
        self.f.z = 1 if value == 0 else 0
        self._update_q(True)
        return 9
