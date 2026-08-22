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

    A newly constructed CPU has zeroed processor state.  The host owns memory,
    devices, and any reset policy; construct a new instance to obtain the
    package's defined initial state.  Host methods must mask addresses to 16
    bits and values to 8 bits when their backing storage requires it.
    """

    def step(self) -> int:
        """Execute one instruction and return its documented T-state count.

        T-states describe instruction timing totals, not externally observable
        bus cycles.  ``decode_and_execute()`` remains supported as the
        historical compatibility name.
        """
        return self.decode_and_execute()

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
