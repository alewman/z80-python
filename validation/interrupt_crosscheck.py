"""Cross-check z80_python's interrupt lifecycle against an independent core.

Run ``python scripts/fetch_interrupt_oracle.py`` first to fetch and build
``superzazu/z80`` -- a separately written, zexdoc/zexall-certified Z80
core -- as the comparison oracle.

This is cross-implementation triangulation, not a hardware oracle: no
publicly known hardware-captured test corpus exists for interrupt
*sequencing* the way SingleStepTests/z80test exist for instruction
semantics. Two independently written cores landing on identical state after
deliberately adversarial scenarios raises real confidence; it is not the
same tier of evidence as z80test's real-Spectrum vectors, and should not be
described as one in public claims.

Both cores service NMI/INT/RESET only at instruction boundaries via an
explicit request-then-step protocol, but their APIs check pending requests
on opposite sides of the fetch/execute step: ``z80_python.step()`` checks
pending requests *before* fetching, so a request raised between two step()
calls is serviced on the very next call with nothing further executed;
superzazu's ``z80_step()`` always executes whatever is at the current PC
first and checks *after*, so the same request still costs one more
instruction before it's serviced. Every scenario below places a NOP
"hinge" instruction at the point where the request becomes visible so both
conventions land on identical final state: the python side executes that
NOP in its own step() call and then raises the request (so its next step()
services with nothing further executed); the C side has the request raised
first, and its one following step() call executes that same NOP and
services immediately after.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from z80_python.cpu import Z80CPU

_LIBRARY = (
    Path(__file__).resolve().parent / "interrupt_oracle_src" / "libz80sz.so"
)

_STATE_FIELDS = (
    "pc", "sp", "iff1", "iff2", "im", "halted", "r", "i", "a", "stack01", "cyc",
)


def _load_library(path: Path) -> ctypes.CDLL:
    lib = ctypes.CDLL(str(path))
    for name in ("w_reset", "w_step", "w_gen_nmi"):
        getattr(lib, name).restype = None
        getattr(lib, name).argtypes = []
    for name in (
        "w_gen_int", "w_set_mem", "w_set_pc", "w_set_sp", "w_set_i", "w_set_r",
        "w_set_a", "w_set_iff1", "w_set_iff2", "w_set_im", "w_set_halted",
        "w_set_iff_delay",
    ):
        getattr(lib, name).restype = None
        getattr(lib, name).argtypes = [ctypes.c_int]
    lib.w_get_mem.restype = ctypes.c_int
    lib.w_get_mem.argtypes = [ctypes.c_int]
    for name in (
        "w_get_pc", "w_get_sp", "w_get_i", "w_get_r", "w_get_a", "w_get_iff1",
        "w_get_iff2", "w_get_im", "w_get_halted", "w_get_iff_delay",
    ):
        getattr(lib, name).restype = ctypes.c_int
        getattr(lib, name).argtypes = []
    lib.w_get_cyc.restype = ctypes.c_ulong
    lib.w_get_cyc.argtypes = []
    return lib


class ReferenceHost:
    """ctypes handle onto the compiled superzazu/z80 oracle."""

    def __init__(self, library_path: Path = _LIBRARY) -> None:
        if not library_path.is_file():
            raise FileNotFoundError(
                f"{library_path} not found; run scripts/fetch_interrupt_oracle.py first"
            )
        self.lib = _load_library(library_path)

    def state(self) -> dict[str, int]:
        lib = self.lib
        sp = lib.w_get_sp()
        return dict(
            pc=lib.w_get_pc(), sp=sp, iff1=lib.w_get_iff1(), iff2=lib.w_get_iff2(),
            im=lib.w_get_im(), halted=lib.w_get_halted(), r=lib.w_get_r(),
            i=lib.w_get_i(), a=lib.w_get_a(),
            stack01=(lib.w_get_mem(sp), lib.w_get_mem(sp + 1)),
            cyc=lib.w_get_cyc(),
        )


class PyHost(Z80CPU):
    """Flat 64 KiB host used only by this cross-check."""

    def __init__(self) -> None:
        super().__init__()
        self.memory = bytearray(0x10000)
        self.total_cyc = 0

    def step(self) -> int:
        t = super().step()
        self.total_cyc += t
        return t

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        return 0xFF

    def write_port(self, addr: int, value: int) -> None:
        pass

    def state(self) -> dict[str, int]:
        return dict(
            pc=self.pc, sp=self.sp, iff1=self.iff1, iff2=self.iff2, im=self.im,
            halted=self.halted, r=self.r, i=self.i, a=self.a,
            stack01=(self.memory[self.sp], self.memory[(self.sp + 1) & 0xFFFF]),
            cyc=self.total_cyc,
        )


@dataclass(frozen=True)
class Scenario:
    """One adversarial interrupt-lifecycle scenario run on both cores."""

    name: str
    program: dict[int, int]
    init: dict[str, int] = field(default_factory=dict)
    python_script: Callable[[PyHost], None] = lambda cpu: None
    reference_script: Callable[[ReferenceHost], None] = lambda ref: None


@dataclass(frozen=True)
class ComparisonResult:
    name: str
    python_state: dict[str, int]
    reference_state: dict[str, int]

    @property
    def matches(self) -> bool:
        return self.python_state == self.reference_state

    @property
    def mismatches(self) -> dict[str, tuple[int, int]]:
        return {
            k: (self.python_state[k], self.reference_state[k])
            for k in _STATE_FIELDS
            if self.python_state[k] != self.reference_state[k]
        }


_DEFAULT_INIT = {"sp": 0xFFF0, "i": 0, "r": 0, "iff1": 1, "iff2": 1, "im": 1, "halted": 0, "a": 0}


def run_scenario(scenario: Scenario, library_path: Path = _LIBRARY) -> ComparisonResult:
    ref = ReferenceHost(library_path)
    lib = ref.lib
    lib.w_reset()
    cpu = PyHost()

    init = {**_DEFAULT_INIT, **scenario.init, "pc": scenario.init.get("pc", 0)}
    for addr, byte in scenario.program.items():
        lib.w_set_mem(addr, byte)
        cpu.memory[addr] = byte

    lib.w_set_pc(init["pc"]); cpu.pc = init["pc"]
    lib.w_set_sp(init["sp"]); cpu.sp = init["sp"]
    lib.w_set_i(init["i"]); cpu.i = init["i"]
    lib.w_set_r(init["r"]); cpu.r = init["r"]
    lib.w_set_iff1(init["iff1"]); cpu.iff1 = init["iff1"]
    lib.w_set_iff2(init["iff2"]); cpu.iff2 = init["iff2"]
    lib.w_set_im(init["im"]); cpu.im = init["im"]
    lib.w_set_halted(init["halted"]); cpu.halted = init["halted"]
    lib.w_set_a(init["a"]); cpu.a = init["a"]

    scenario.python_script(cpu)
    scenario.reference_script(ref)

    return ComparisonResult(scenario.name, cpu.state(), ref.state())


def _im1_running() -> Scenario:
    def py(cpu: PyHost) -> None:
        cpu.step()  # hinge NOP@0 -> pc=1
        cpu.request_maskable_interrupt(0xFF)
        cpu.step()  # services immediately

    def sz(ref: ReferenceHost) -> None:
        ref.lib.w_gen_int(0xFF)
        ref.lib.w_step()  # executes hinge NOP@0, then services

    return Scenario("IM1 accept while running", {0x0000: 0x00}, {}, py, sz)


def _im1_from_halt() -> Scenario:
    def py(cpu: PyHost) -> None:
        cpu.step()  # HALT@0 -> cpu.halted becomes True
        cpu.request_maskable_interrupt(0xFF)
        cpu.step()  # services: wakes HALT

    def sz(ref: ReferenceHost) -> None:
        ref.lib.w_gen_int(0xFF)
        ref.lib.w_step()

    return Scenario("IM1 accept from HALT", {0x0000: 0x76}, {"halted": 1}, py, sz)


def _im2_vector_table() -> Scenario:
    def py(cpu: PyHost) -> None:
        cpu.step()
        cpu.request_maskable_interrupt(0x10)
        cpu.step()

    def sz(ref: ReferenceHost) -> None:
        ref.lib.w_gen_int(0x10)
        ref.lib.w_step()

    return Scenario(
        "IM2 vector table dispatch",
        {0x0000: 0x00, 0x4010: 0x00, 0x4011: 0x90},
        {"im": 2, "i": 0x40},
        py, sz,
    )


def _im0_rst() -> Scenario:
    def py(cpu: PyHost) -> None:
        cpu.step()
        cpu.request_maskable_interrupt(0xD7)  # RST 10h
        cpu.step()

    def sz(ref: ReferenceHost) -> None:
        ref.lib.w_gen_int(0xD7)
        ref.lib.w_step()

    return Scenario("IM0 device-supplied RST 10h", {0x0000: 0x00}, {"im": 0}, py, sz)


def _nmi_running() -> Scenario:
    def py(cpu: PyHost) -> None:
        cpu.step()
        cpu.request_non_maskable_interrupt()
        cpu.step()

    def sz(ref: ReferenceHost) -> None:
        ref.lib.w_gen_nmi()
        ref.lib.w_step()

    return Scenario("NMI accept while running", {0x0000: 0x00}, {}, py, sz)


def _nmi_from_halt() -> Scenario:
    def py(cpu: PyHost) -> None:
        cpu.step()
        cpu.request_non_maskable_interrupt()
        cpu.step()

    def sz(ref: ReferenceHost) -> None:
        ref.lib.w_gen_nmi()
        ref.lib.w_step()

    return Scenario(
        "NMI accept from HALT", {0x0000: 0x76}, {"iff1": 0, "iff2": 0, "halted": 1}, py, sz
    )


def _retn_restores_iff1() -> Scenario:
    def py(cpu: PyHost) -> None:
        cpu.step()  # hinge NOP@0
        cpu.request_non_maskable_interrupt()
        cpu.step()  # services NMI -> pc=0x66, iff1=0, iff2 preserves old iff1
        cpu.step()  # RETN@0x66 -> iff1 = iff2, pops pc back

    def sz(ref: ReferenceHost) -> None:
        ref.lib.w_gen_nmi()
        ref.lib.w_step()  # hinge + service
        ref.lib.w_step()  # RETN

    return Scenario(
        "RETN restores IFF1 from IFF2",
        {0x0000: 0x00, 0x0066: 0xED, 0x0067: 0x45},  # ED 45 = RETN
        {}, py, sz,
    )


def _ei_delay_defers_one_instruction() -> Scenario:
    def py(cpu: PyHost) -> None:
        cpu.step()  # EI@0 -> pc=1
        cpu.request_maskable_interrupt(0xFF)
        cpu.step()  # must NOT service yet: executes shadow NOP@1 -> pc=2
        cpu.step()  # now services (pushes pc=2)

    def sz(ref: ReferenceHost) -> None:
        ref.lib.w_gen_int(0xFF)
        ref.lib.w_step()  # EI@0 -> pc=1 (iff_delay resolves, no accept this call)
        ref.lib.w_step()  # shadow NOP@1 -> pc=2, then services

    return Scenario(
        "EI defers acceptance for exactly one instruction",
        {0x0000: 0xFB, 0x0001: 0x00, 0x0002: 0x00},  # EI ; NOP ; NOP
        {"iff1": 0, "iff2": 0}, py, sz,
    )


def _di_masks_without_losing_request() -> Scenario:
    def py(cpu: PyHost) -> None:
        cpu.request_maskable_interrupt(0xFF)  # raised while IFF1=0 (masked)
        cpu.step()  # NOP@0 (still masked) -> pc=1
        cpu.step()  # EI@1 -> pc=2 (delay starts)
        cpu.step()  # shadow NOP@2 -> pc=3 (still deferred)
        cpu.step()  # now services

    def sz(ref: ReferenceHost) -> None:
        ref.lib.w_gen_int(0xFF)
        ref.lib.w_step()  # NOP@0, still masked
        ref.lib.w_step()  # EI@1 -> pc=2
        ref.lib.w_step()  # shadow NOP@2 -> pc=3, then services

    return Scenario(
        "DI-masked request survives until EI clears",
        {0x0000: 0x00, 0x0001: 0xFB, 0x0002: 0x00, 0x0003: 0x00},  # NOP;EI;NOP;NOP
        {"iff1": 0, "iff2": 0}, py, sz,
    )


def _nmi_priority_over_pending_maskable() -> Scenario:
    def py(cpu: PyHost) -> None:
        cpu.step()  # hinge NOP@0
        cpu.request_maskable_interrupt(0xFF)
        cpu.request_non_maskable_interrupt()
        cpu.step()  # NMI must win

    def sz(ref: ReferenceHost) -> None:
        ref.lib.w_gen_int(0xFF)
        ref.lib.w_gen_nmi()
        ref.lib.w_step()

    return Scenario(
        "NMI takes priority over a simultaneously pending maskable request",
        {0x0000: 0x00}, {}, py, sz,
    )


SCENARIOS: tuple[Scenario, ...] = (
    _im1_running(),
    _im1_from_halt(),
    _im2_vector_table(),
    _im0_rst(),
    _nmi_running(),
    _nmi_from_halt(),
    _retn_restores_iff1(),
    _ei_delay_defers_one_instruction(),
    _di_masks_without_losing_request(),
    _nmi_priority_over_pending_maskable(),
)
