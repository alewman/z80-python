"""Headless runner for raxoft/z80test's ``.tap`` programs.

z80test's expected values were captured from a real 48K ZX Spectrum with a
genuine Zilog Z80 -- a hardware oracle, not another emulator. Its programs are
launched via ``RANDOMIZE USR 32768`` from a BASIC loader and only depend on
the Spectrum ROM for two things: printing a character (``RST 0x10``) and
selecting the output channel (``CHAN-OPEN`` at ``0x1601``). Neither touches
tested CPU state, so this runner replaces both with a tiny stub instead of
requiring a real 48K ROM image:

- ``0x0010``: ``OUT (0xFF),A`` ; ``RET`` -- captures the printed character on
  a private port instead of going through the ROM's screen/channel code.
- ``0x1601``: a bare ``RET`` -- CHAN-OPEN's caller only needs it to return.

The one other hardware dependency, a single ``IN A,(0xFE)`` guard the driver
uses to skip the IN-instruction group when the keyboard port can't be
trusted, is satisfied by always returning ``0xBF`` (no key pressed, EAR/MIC
forced low) -- matching the state the driver itself sets up immediately
before the check.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from z80_python.cpu import Z80CPU

_LOAD_STUB_RST10 = bytes((0xD3, 0xFF, 0xC9))  # OUT (0xFF),A ; RET
_LOAD_STUB_CHANOPEN = bytes((0xC9,))  # RET
_RST10_ADDRESS = 0x0010
_CHANOPEN_ADDRESS = 0x1601
_SENTINEL_RETURN = 0x0000


class Z80TestRunError(RuntimeError):
    """Raised when a z80test program does not terminate as expected."""


def _parse_tap_code_block(data: bytes) -> tuple[bytes, int]:
    """Extract the CODE block payload and load address from a z80test ``.tap``."""
    pos = 0
    blocks: list[bytes] = []
    while pos < len(data):
        (length,) = struct.unpack_from("<H", data, pos)
        pos += 2
        blocks.append(data[pos : pos + length])
        pos += length
    if len(blocks) < 4:
        raise Z80TestRunError(f"expected a BASIC+CODE tap file, found {len(blocks)} blocks")
    code_header = blocks[2]
    if code_header[0] != 0x00 or code_header[1] != 3:
        raise Z80TestRunError("expected a CODE header as the third tap block")
    length, load_addr = struct.unpack_from("<HH", code_header, 12)
    code_data = blocks[3]
    if code_data[0] != 0xFF:
        raise Z80TestRunError("expected a data block as the fourth tap block")
    payload = code_data[1 : 1 + length]
    if len(payload) != length:
        raise Z80TestRunError(
            f"CODE block length mismatch: header says {length}, got {len(payload)}"
        )
    return payload, load_addr


class _SpectrumHostCPU(Z80CPU):
    """Flat 64 KiB memory implementation used only by :class:`Z80TestRunner`."""

    def __init__(self) -> None:
        super().__init__()
        self.memory = bytearray(0x10000)
        self.out_chars: list[str] = []

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        if (addr & 0xFF) == 0xFE:
            return 0xBF
        return 0xFF

    def write_port(self, addr: int, value: int) -> None:
        if (addr & 0xFF) == 0xFF:
            self.out_chars.append(chr(value & 0xFF))


@dataclass(frozen=True)
class Z80TestResult:
    """Completed z80test execution transcript and accounting information."""

    output: str
    instructions: int

    @property
    def passed(self) -> bool:
        """Whether the suite's own summary line reports a clean sweep."""
        return "Result: all tests passed." in self.output


class Z80TestRunner:
    """Run a raxoft/z80test ``.tap`` program to its own completion."""

    def __init__(self, tap_bytes: bytes) -> None:
        code, load_addr = _parse_tap_code_block(tap_bytes)
        self.cpu = _SpectrumHostCPU()
        self.cpu.memory[load_addr : load_addr + len(code)] = code
        self.cpu.memory[_RST10_ADDRESS : _RST10_ADDRESS + len(_LOAD_STUB_RST10)] = (
            _LOAD_STUB_RST10
        )
        self.cpu.memory[_CHANOPEN_ADDRESS : _CHANOPEN_ADDRESS + len(_LOAD_STUB_CHANOPEN)] = (
            _LOAD_STUB_CHANOPEN
        )
        self.cpu.sp = 0xFFFC
        self.cpu.memory[0xFFFC] = _SENTINEL_RETURN & 0xFF
        self.cpu.memory[0xFFFD] = (_SENTINEL_RETURN >> 8) & 0xFF
        self.cpu.pc = load_addr

    @classmethod
    def from_file(cls, path: Path | str) -> Z80TestRunner:
        """Load a z80test ``.tap`` program from ``path``."""
        return cls(Path(path).read_bytes())

    def run(self, *, max_instructions: int = 2_000_000_000) -> Z80TestResult:
        """Execute until the program returns to its BASIC caller (PC == 0)."""
        if max_instructions < 1:
            raise ValueError("max_instructions must be positive")
        instructions = 0
        while self.cpu.pc != _SENTINEL_RETURN:
            self.cpu.step()
            instructions += 1
            if instructions >= max_instructions:
                raise Z80TestRunError(
                    f"z80test did not terminate within {max_instructions:,} instructions"
                )
        return Z80TestResult("".join(self.cpu.out_chars), instructions)
