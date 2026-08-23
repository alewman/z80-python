"""Public Z80 CPU API.

Implementation details are split across private instruction-family mixins. This
module remains the stable import surface for ``Z80CPU``, ``Flags``, and flag masks.
"""

from abc import ABC, abstractmethod

from z80_python._alu import ALUMixin
from z80_python._blocks import BlockMixin
from z80_python._control import ControlMixin
from z80_python._core import CoreMixin
from z80_python._dispatch import DispatchMixin
from z80_python._flags import (
    FLAG_C,
    FLAG_H,
    FLAG_N,
    FLAG_PV,
    FLAG_S,
    FLAG_X,
    FLAG_Y,
    FLAG_Z,
    Flags,
)
from z80_python._index import IndexMixin
from z80_python._index_dispatch import IndexDispatchMixin
from z80_python._io import IOMixin
from z80_python._loads import LoadMixin
from z80_python._rotate import RotateBitMixin

# Preserve the historical public identity even though the implementation lives
# in a private module.
Flags.__module__ = __name__

__all__ = [
    "FLAG_C",
    "FLAG_H",
    "FLAG_N",
    "FLAG_PV",
    "FLAG_S",
    "FLAG_X",
    "FLAG_Y",
    "FLAG_Z",
    "Z80CPU",
    "Flags",
]


class Z80CPU(
    DispatchMixin,
    IndexDispatchMixin,
    IndexMixin,
    LoadMixin,
    ALUMixin,
    RotateBitMixin,
    BlockMixin,
    IOMixin,
    ControlMixin,
    CoreMixin,
    ABC,
):
    """Abstract Z80 instruction core with memory and I/O supplied by a host.

    A newly constructed CPU has zeroed processor state. The host owns memory and
    devices, and may use :meth:`request_reset` for a board-level reset while
    retaining those devices. Host methods must mask addresses to 16 bits and
    values to 8 bits when their backing storage requires it.
    """

    def step(self) -> int:
        """Advance one instruction boundary and return its documented T-state count.

        An asserted RESET takes priority over NMI and an accepted maskable interrupt;
        each is serviced before instruction fetch. A halted CPU consumes a four-T-state
        idle cycle until an accepted interrupt wakes it. T-states are
        instruction/lifecycle totals, not externally observable bus cycles.
        ``decode_and_execute()`` remains the historical instruction-only compatibility
        entry point.
        """
        if self._reset_pending:
            return self._accept_reset()
        if self._non_maskable_interrupt_pending:
            return self._accept_non_maskable_interrupt()
        if self._can_accept_maskable_interrupt():
            return self._accept_maskable_interrupt()

        delay_was_active = self._ei_delay > 0
        if self.halted:
            self._inc_r()
            self._update_q(False)
            t_states = 4
        else:
            t_states = self.decode_and_execute()
        if delay_was_active:
            self._ei_delay -= 1
        return t_states

    @property
    def reset_pending(self) -> bool:
        """Whether the host has asserted RESET.

        RESET is modeled as a level-sensitive input. It remains asserted until
        :meth:`clear_reset` is called, and each :meth:`step` while asserted services
        the documented reset state instead of fetching an instruction.
        """

        return self._reset_pending

    def request_reset(self) -> None:
        """Assert RESET for servicing at the next instruction boundary.

        RESET has priority over NMI and maskable-interrupt requests. The host must
        call :meth:`clear_reset` to release the reset line before instruction
        execution resumes.
        """

        self._reset_pending = True

    def clear_reset(self) -> None:
        """Release the host-controlled RESET line."""

        self._reset_pending = False

    @property
    def maskable_interrupt_pending(self) -> bool:
        """Whether a device has requested a maskable interrupt not yet accepted."""

        return self._pending_maskable_interrupt is not None

    def request_maskable_interrupt(self, vector_byte: int = 0xFF) -> None:
        """Assert the maskable-interrupt request line between instruction boundaries.

        The request remains pending through ``DI`` or an EI-delay window and is
        accepted by a later :meth:`step` when ``IFF1`` permits it. ``vector_byte`` is
        ignored by IM 1, supplies the low vector byte for IM 2, and must be an RST
        opcode for the intentionally bounded IM 0 implementation.
        """

        if not isinstance(vector_byte, int) or not 0 <= vector_byte <= 0xFF:
            raise ValueError("vector_byte must be an integer in range 0x00..0xFF")
        self._pending_maskable_interrupt = vector_byte

    def clear_maskable_interrupt(self) -> None:
        """Deassert a previously requested but not-yet-accepted interrupt."""

        self._pending_maskable_interrupt = None

    @property
    def non_maskable_interrupt_pending(self) -> bool:
        """Whether a device has requested a non-maskable interrupt not yet accepted."""

        return self._non_maskable_interrupt_pending

    def request_non_maskable_interrupt(self) -> None:
        """Latch an NMI request for service at the next instruction boundary.

        NMIs ignore ``IFF1`` and an EI-delay window. On acceptance they preserve the
        old ``IFF1`` in ``IFF2``, clear ``IFF1``, push the boundary PC, and enter
        address ``0x0066``. Repeated requests while pending coalesce into one NMI.
        """

        self._non_maskable_interrupt_pending = True

    def clear_non_maskable_interrupt(self) -> None:
        """Cancel a requested NMI that has not yet reached an instruction boundary."""

        self._non_maskable_interrupt_pending = False

    @abstractmethod
    def read_byte(self, addr: int) -> int:
        """Read one byte from the 16-bit memory address space.

        The host must mask ``addr`` to 16 bits and return an 8-bit value.
        """

    @abstractmethod
    def write_byte(self, addr: int, value: int) -> None:
        """Write one byte to the 16-bit memory address space.

        The host must mask ``addr`` to 16 bits and ``value`` to 8 bits.
        """

    @abstractmethod
    def read_port(self, addr: int) -> int:
        """Read one byte from the 16-bit I/O port address space.

        The host must mask ``addr`` to 16 bits and return an 8-bit value.
        """

    @abstractmethod
    def write_port(self, addr: int, value: int) -> None:
        """Write one byte to the 16-bit I/O port address space.

        The host must mask ``addr`` to 16 bits and ``value`` to 8 bits.
        """
