"""Block transfer and search instruction implementation."""


class BlockMixin:
    """Private ED block-transfer and search implementation."""

    def _block_ld(self, increment: bool) -> bool:
        src = self._hl()
        data = self.read_byte(src)
        dst = self._de()
        self.write_byte(dst, data)
        if increment:
            hl, de = (src + 1) & 0xFFFF, (dst + 1) & 0xFFFF
        else:
            hl, de = (src - 1) & 0xFFFF, (dst - 1) & 0xFFFF
        self.h, self.l = (hl >> 8) & 0xFF, hl & 0xFF
        self.d, self.e = (de >> 8) & 0xFF, de & 0xFF
        self.f.n = self.f.h = 0
        bc = (self._bc() - 1) & 0xFFFF
        self.f.pv = 1 if bc else 0
        self.b, self.c = (bc >> 8) & 0xFF, bc & 0xFF
        # LD group: X/Y come from A + transferred byte, landing in bits 3 and 1
        # (not 3 and 5). Y here is bit 1 of that sum, the documented-undocumented rule.
        self.f.x = ((self.a + data) & 0x08) >> 3
        self.f.y = ((self.a + data) & 0x02) >> 1
        return bc != 0

    def _block_cp(self, increment: bool) -> bool:
        src = self._hl()
        data = self.read_byte(src)
        if increment:
            self.wz = (self.wz + 1) & 0xFFFF
            hl = (src + 1) & 0xFFFF
        else:
            self.wz = (self.wz - 1) & 0xFFFF
            hl = (src - 1) & 0xFFFF
        self.h, self.l = (hl >> 8) & 0xFF, hl & 0xFF
        result = (self.a - data) & 0xFF
        self.f.n = 1
        bc = (self._bc() - 1) & 0xFFFF
        self.f.pv = 1 if bc else 0
        self.b, self.c = (bc >> 8) & 0xFF, bc & 0xFF
        self.f.h = ((self.a ^ data ^ result) & 0x10) >> 4
        # X/Y come from A - (HL) - H, the ALU's intermediate before the final
        # correction, and land in bits 3 and 1 (not 3 and 5) for the CP group.
        self.f.x = ((result - self.f.h) & 0x08) >> 3
        self.f.y = ((result - self.f.h) & 0x02) >> 1
        self._set_sz(result)
        return bc != 0 and self.f.z == 0

    def _block_repeat(self) -> None:
        self.pc = (self.pc - 2) & 0xFFFF
        self.wz = (self.pc + 1) & 0xFFFF
        # On a repeat the CPU rewinds PC by 2 and re-fetches; X/Y then sample bits 3
        # and 5 of the rewound PC's high byte (PC bits 11 and 13), and WZ = PC + 1.
        self.f.x = (self.pc >> 11) & 1
        self.f.y = (self.pc >> 13) & 1

    def _op_ldi(self) -> int:
        """LDI -- (DE) <- (HL); HL++, DE++, BC--."""
        self._block_ld(True)
        self._update_q(True)
        return 16

    def _op_ldd(self) -> int:
        """LDD -- (DE) <- (HL); HL--, DE--, BC--."""
        self._block_ld(False)
        self._update_q(True)
        return 16

    def _op_cpi(self) -> int:
        """CPI -- compare A with (HL); HL++, BC--."""
        self._block_cp(True)
        self._update_q(True)
        return 16

    def _op_cpd(self) -> int:
        """CPD -- compare A with (HL); HL--, BC--."""
        self._block_cp(False)
        self._update_q(True)
        return 16

    def _op_ldir(self) -> int:
        """LDIR -- LDI repeated while BC != 0; 21 T-states per repeat, 16 on the last."""
        repeat = self._block_ld(True)
        if repeat:
            self._block_repeat()
        self._update_q(True)
        return 21 if repeat else 16

    def _op_lddr(self) -> int:
        """LDDR -- LDD repeated while BC != 0; 21 T-states per repeat, 16 on the last."""
        repeat = self._block_ld(False)
        if repeat:
            self._block_repeat()
        self._update_q(True)
        return 21 if repeat else 16

    def _op_cpir(self) -> int:
        """CPIR -- CPI repeated while BC != 0 and A != (HL); 21 T-states per repeat, 16 last."""
        repeat = self._block_cp(True)
        if repeat:
            self._block_repeat()
        self._update_q(True)
        return 21 if repeat else 16

    def _op_cpdr(self) -> int:
        """CPDR -- CPD repeated while BC != 0 and A != (HL); 21 T-states per repeat, 16 last."""
        repeat = self._block_cp(False)
        if repeat:
            self._block_repeat()
        self._update_q(True)
        return 21 if repeat else 16
