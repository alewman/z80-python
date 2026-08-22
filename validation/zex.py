"""Headless CP/M runner for the ZEXDOC and ZEXALL Z80 exercisers.

The runner deliberately supplies only the tiny BDOS surface used by the
exercisers: console character output (function 2) and ``$``-terminated string
output (function 9).  It keeps CP/M emulation out of the reusable CPU core.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from z80_python.cpu import Z80CPU

_COM_LOAD_ADDRESS = 0x0100
_BDOS_ENTRY = 0x0005
_WARM_BOOT = 0x0000


class ZexRunError(RuntimeError):
    """Raised when a ZEX program exceeds its budget or requests unsupported BDOS."""


class _CPMCPU(Z80CPU):
    """Flat 64 KiB memory implementation used only by :class:`ZexRunner`."""

    def __init__(self) -> None:
        super().__init__()
        self.memory = bytearray(0x10000)

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        raise ZexRunError(f"ZEX attempted an unexpected I/O read at 0x{addr:04X}")

    def write_port(self, addr: int, value: int) -> None:
        raise ZexRunError(f"ZEX attempted an unexpected I/O write at 0x{addr:04X}")


@dataclass(frozen=True)
class ZexResult:
    """Completed ZEX execution transcript and accounting information."""

    output: str
    instructions: int
    t_states: int

    @property
    def passed(self) -> bool:
        """Whether the exerciser reached its own successful completion message."""
        return "Tests complete" in self.output and "ERROR ****" not in self.output


class ZexRunner:
    """Run a ZEX ``.COM`` image in a minimal, deterministic CP/M environment."""

    def __init__(self, program: bytes) -> None:
        if not program:
            raise ValueError("ZEX program must not be empty")
        if len(program) > 0x10000 - _COM_LOAD_ADDRESS:
            raise ValueError(f"ZEX program is too large for CP/M memory: {len(program)} bytes")
        self.cpu = _CPMCPU()
        self.cpu.memory[_COM_LOAD_ADDRESS : _COM_LOAD_ADDRESS + len(program)] = program
        # CP/M transient programs begin by loading their stack pointer from
        # 0006h.  A real CCP places a high-memory address there; ZEX uses it
        # before its first BDOS call, so a zero-filled bare machine is wrong.
        self.cpu.memory[0x0006] = 0x00
        self.cpu.memory[0x0007] = 0xF0
        self.cpu.pc = _COM_LOAD_ADDRESS
        self.cpu.sp = 0xF000
        self._output = bytearray()

    @classmethod
    def from_file(cls, path: Path | str) -> ZexRunner:
        """Load a CP/M ``.COM`` program from ``path``."""
        return cls(Path(path).read_bytes())

    def _return_from_bdos(self) -> None:
        self.cpu.pc = self.cpu._pop_word()

    def _write_string(self) -> None:
        address = self.cpu._de()
        while True:
            value = self.cpu.read_byte(address)
            address = (address + 1) & 0xFFFF
            if value == ord("$"):
                return
            self._output.append(value)

    def _handle_bdos(self) -> bool:
        function = self.cpu.c
        if function == 0:
            return True
        if function == 2:
            self._output.append(self.cpu.e)
        elif function == 9:
            self._write_string()
        else:
            raise ZexRunError(
                f"unsupported CP/M BDOS function {function} at PC 0x{self.cpu.pc:04X}"
            )
        self._return_from_bdos()
        return False

    def run(self, *, max_instructions: int = 200_000_000) -> ZexResult:
        """Execute until CP/M warm boot, BDOS exit, or the instruction budget expires."""
        if max_instructions < 1:
            raise ValueError("max_instructions must be positive")
        instructions = 0
        t_states = 0
        while instructions < max_instructions:
            if self.cpu.pc == _WARM_BOOT:
                return ZexResult(self._output.decode("latin-1"), instructions, t_states)
            if self.cpu.pc == _BDOS_ENTRY:
                if self._handle_bdos():
                    return ZexResult(self._output.decode("latin-1"), instructions, t_states)
                continue
            if self.cpu.halted:
                raise ZexRunError(f"ZEX halted unexpectedly at PC 0x{self.cpu.pc:04X}")
            t_states += self.cpu.decode_and_execute()
            instructions += 1
        raise ZexRunError(f"ZEX did not terminate within {max_instructions:,} instructions")  # noqa: W292