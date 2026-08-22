"""Input/output instruction implementation."""


class IOMixin:
    """Private immediate, register, and block I/O implementation."""

    def _in_flags(self, value: int) -> None:
        self.f.n = self.f.h = 0
        self._set_parity(value)
        self._set_xysz(value)

    def _op_in_a_n(self) -> int:
        self.wz = (self.a << 8) | self._read_operand_byte()
        self.a = self.read_port(self.wz)
        self.wz = (self.wz + 1) & 0xFFFF
        self._update_q(False)
        return 11

    def _op_out_n_a(self) -> int:
        self.wz = (self.a << 8) | self._read_operand_byte()
        self.write_port(self.wz, self.a)
        self.wz = (self.wz & 0xFF00) | ((self.wz + 1) & 0xFF)
        self._update_q(False)
        return 11

    def _op_in_r_c(self, opcode: int) -> int:
        dest = (opcode >> 3) & 0x07
        self.wz = (self._bc() + 1) & 0xFFFF
        value = self.read_port(self._bc())
        self._in_flags(value)
        if dest != 6:
            self._write_reg(dest, value)
        self._update_q(True)
        return 12

    def _op_out_c_r(self, opcode: int) -> int:
        src = (opcode >> 3) & 0x07
        addr = self._bc()
        value = 0 if src == 6 else self._read_reg(src)
        self.write_port(addr, value)
        self.wz = (addr + 1) & 0xFFFF
        self._update_q(False)
        return 12

    def _block_ini(self, increment: bool) -> bool:
        if increment:
            self.wz = (self._bc() + 1) & 0xFFFF
            data = self.read_port((self.wz - 1) & 0xFFFF)
            adj = (self.c + 1) & 0xFF
        else:
            self.wz = (self._bc() - 1) & 0xFFFF
            data = self.read_port((self.wz + 1) & 0xFFFF)
            adj = (self.c - 1) & 0xFF
        self._io_data = data
        self.b = (self.b - 1) & 0xFF
        self.write_byte(self._hl(), data)
        hl = (self._hl() + 1) & 0xFFFF if increment else (self._hl() - 1) & 0xFFFF
        self.h, self.l = (hl >> 8) & 0xFF, hl & 0xFF
        carry = 1 if (adj + data) > 0xFF else 0
        self.f.c = carry
        self.f.n = (data >> 7) & 1
        self._set_parity(((adj + data) & 7) ^ self.b)
        self._set_xysz(self.b)
        self.f.h = carry
        return self.b != 0

    def _block_outi(self, increment: bool) -> bool:
        hl = self._hl()
        data = self.read_byte(hl)
        self._io_data = data
        hl = (hl + 1) & 0xFFFF if increment else (hl - 1) & 0xFFFF
        self.h, self.l = (hl >> 8) & 0xFF, hl & 0xFF
        self.b = (self.b - 1) & 0xFF
        addr = self._bc()
        self.write_port(addr, data)
        self.wz = (addr + 1) & 0xFFFF if increment else (addr - 1) & 0xFFFF
        carry = 1 if (self.l + data) > 0xFF else 0
        self.f.c = carry
        self.f.n = (data >> 7) & 1
        self._set_parity(((self.l + data) & 7) ^ self.b)
        self._set_xysz(self.b)
        self.f.h = carry
        return self.b != 0

    def _post_in_o_r(self) -> None:
        self.f.x = (self.pc >> 11) & 1
        self.f.y = (self.pc >> 13) & 1
        if self.f.c:
            if self._io_data & 0x80:
                self.f.pv ^= 1 - self._parity((self.b - 1) & 7)
                self.f.h = 1 if (self.b & 0x0F) == 0 else 0
            else:
                self.f.pv ^= 1 - self._parity((self.b + 1) & 7)
                self.f.h = 1 if (self.b & 0x0F) == 0x0F else 0
        else:
            self.f.pv ^= 1 - self._parity(self.b & 7)

    def _op_ini(self) -> int:
        self._block_ini(True)
        self._update_q(True)
        return 16

    def _op_ind(self) -> int:
        self._block_ini(False)
        self._update_q(True)
        return 16

    def _op_outi(self) -> int:
        self._block_outi(True)
        self._update_q(True)
        return 16

    def _op_outd(self) -> int:
        self._block_outi(False)
        self._update_q(True)
        return 16

    def _op_inir(self) -> int:
        repeat = self._block_ini(True)
        if repeat:
            self._block_repeat()
            self._post_in_o_r()
        self._update_q(True)
        return 21 if repeat else 16

    def _op_indr(self) -> int:
        repeat = self._block_ini(False)
        if repeat:
            self._block_repeat()
            self._post_in_o_r()
        self._update_q(True)
        return 21 if repeat else 16

    def _op_otir(self) -> int:
        repeat = self._block_outi(True)
        if repeat:
            self._block_repeat()
            self._post_in_o_r()
        self._update_q(True)
        return 21 if repeat else 16

    def _op_otdr(self) -> int:
        repeat = self._block_outi(False)
        if repeat:
            self._block_repeat()
            self._post_in_o_r()
        self._update_q(True)
        return 21 if repeat else 16
