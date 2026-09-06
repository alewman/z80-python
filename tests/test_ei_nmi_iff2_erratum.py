"""Opt-in NMOS "EI+NMI" IFF2 erratum.

See docs/interrupt-lifecycle.md for the full citation and caveats: this
models a quirk reported from gate-level ("Visual Z80") simulation of the
real chip, not a confirmed real-hardware measurement, so it defaults off and
must never affect the certified default behavior.
"""

from __future__ import annotations

from z80.cpu import Z80CPU


class MemoryCPU(Z80CPU):
    """Concrete Z80CPU backed by a flat 64 KiB bytearray."""

    def __init__(self) -> None:
        super().__init__()
        self.memory = bytearray(0x10000)

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        raise NotImplementedError("unit-test CPU does not model I/O ports")

    def write_port(self, addr: int, value: int) -> None:
        raise NotImplementedError("unit-test CPU does not model I/O ports")


def _cpu_with_pending_nmi_after_ei(*, iff1_before_ei: bool) -> MemoryCPU:
    cpu = MemoryCPU()
    cpu.pc, cpu.sp = 0x2000, 0xFFF0
    cpu.iff1 = iff1_before_ei
    cpu.iff2 = iff1_before_ei
    cpu.write_byte(cpu.pc, 0xFB)  # EI
    cpu.decode_and_execute()  # iff1/iff2 -> True, _ei_delay -> 1, pc -> 0x2001
    cpu.request_non_maskable_interrupt()
    return cpu


def test_erratum_disabled_by_default() -> None:
    cpu = MemoryCPU()
    assert cpu.ei_nmi_iff2_erratum is False


def test_default_behavior_preserves_iff1_across_ei_then_nmi() -> None:
    """Without the erratum, IFF2 keeps EI's IFF1 value for a later RETN."""
    cpu = _cpu_with_pending_nmi_after_ei(iff1_before_ei=False)

    cpu.step()  # services the NMI (never executes a "shadow" instruction)

    assert cpu.pc == 0x0066
    assert cpu.iff1 is False
    assert cpu.iff2 is True  # EI's effect, preserved for RETN


def test_erratum_resets_iff2_when_nmi_lands_in_ei_delay_window() -> None:
    """With the erratum, an NMI inside EI's delay window also clears IFF2."""
    cpu = _cpu_with_pending_nmi_after_ei(iff1_before_ei=False)
    cpu.ei_nmi_iff2_erratum = True

    cpu.step()

    assert cpu.pc == 0x0066
    assert cpu.iff1 is False
    assert cpu.iff2 is False  # corrupted, per the erratum


def test_erratum_leaves_retn_disabling_interrupts_even_if_previously_enabled() -> None:
    """The erratum's actual consequence: RETN can't re-enable interrupts."""
    cpu = _cpu_with_pending_nmi_after_ei(iff1_before_ei=True)
    cpu.ei_nmi_iff2_erratum = True
    cpu.step()  # NMI -> pc=0x0066, iff1=False, iff2=False (erratum)

    cpu.write_byte(0x0066, 0xED)
    cpu.write_byte(0x0067, 0x45)  # RETN
    cpu.decode_and_execute()

    assert cpu.iff1 is False  # would be True without the erratum


def test_erratum_does_not_affect_nmi_outside_the_ei_delay_window() -> None:
    """The erratum only applies to an NMI landing inside the delay window."""
    cpu = MemoryCPU()
    cpu.pc, cpu.sp = 0x2000, 0xFFF0
    cpu.iff1 = cpu.iff2 = True
    cpu.ei_nmi_iff2_erratum = True
    cpu.write_byte(cpu.pc, 0xFB)  # EI
    cpu.write_byte(cpu.pc + 1, 0x00)  # NOP: the instruction EI's delay requires

    cpu.step()  # EI -> pc=0x2001, delay window opens
    cpu.step()  # executes the NOP; delay window closes, no NMI pending yet
    cpu.request_non_maskable_interrupt()
    cpu.step()  # now services the NMI, well outside the delay window

    assert cpu.iff1 is False
    assert cpu.iff2 is True  # normal behavior: erratum did not apply
