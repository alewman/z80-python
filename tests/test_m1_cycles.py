"""The optional ``read_m1(address, kind)`` hook: every M1 cycle, and only M1 cycles.

Each test runs a short program on a host whose ``read_m1`` logs
``("m1", kind, address)`` into the same list as its memory and port accesses,
so a test reads the whole bus story of a step in order. The sources for which
cycles are M1 cycles are in docs/issues/0001-m1-cycle-signal.md.
"""

from __future__ import annotations

import pytest
from conftest import MemoryCPU

from z80_python import Z80CPU, DebugSession, M1Cycle

FETCH, HALT, NMI, ACKNOWLEDGE = M1Cycle.FETCH, M1Cycle.HALT, M1Cycle.NMI, M1Cycle.ACKNOWLEDGE


class LoggingCPU(MemoryCPU):
    """``MemoryCPU`` whose bus callbacks also append to ``log``, in order.

    The shared host records no access sequence (see its docstring). These tests
    need one for a single purpose: to tell which callback an access went
    through, ``read_m1`` or ``read_byte``. Entries are ``("r", address, value)``,
    ``("w", address, value)``, ``("in", port, value)`` and ``("out", port, value)``.
    """

    def __init__(self) -> None:
        self.log: list[tuple] = []
        super().__init__()

    def _bus_read(self, address: int) -> int:
        value = super()._bus_read(address)
        self.log.append(("r", address, value))
        return value

    def _bus_write(self, address: int, value: int) -> None:
        super()._bus_write(address, value)
        self.log.append(("w", address, value))

    def _port_in(self, port: int) -> int:
        value = super()._port_in(port)
        self.log.append(("in", port, value))
        return value

    def _port_out(self, port: int, value: int) -> None:
        super()._port_out(port, value)
        self.log.append(("out", port, value))


class M1Host(LoggingCPU):
    """``LoggingCPU`` plus a ``read_m1`` that logs the cycle and fetches from ``memory``."""

    def __init__(self, program: bytes, origin: int = 0) -> None:
        super().__init__()
        self.memory[origin : origin + len(program)] = program
        self.pc = origin
        self.sp = 0xF000
        self.read_m1 = self._m1

    def _m1(self, address: int, kind: M1Cycle) -> int:
        assert 0 <= address <= 0xFFFF, address
        self.log.append(("m1", kind, address))
        return self.memory[address]

    def m1_cycles(self) -> list[tuple[M1Cycle, int]]:
        return [(kind, address) for tag, kind, address in self.log if tag == "m1"]


def step_log(program: str, origin: int = 0, **registers: int) -> tuple[M1Host, list]:
    cpu = M1Host(bytes.fromhex(program), origin)
    for name, value in registers.items():
        setattr(cpu, name, value)
    cpu.step()
    return cpu, cpu.log


@pytest.mark.parametrize(
    ("program", "fetches", "reads"),
    [
        ("00", [0], []),  # NOP: one opcode fetch
        ("3e42", [0], [1]),  # LD A,n: the operand is a data read
        ("cb00", [0, 1], []),  # RLC B: CB prefix and opcode
        ("ed44", [0, 1], []),  # NEG: ED prefix and opcode
        ("dd210010", [0, 1], [2, 3]),  # LD IX,nn: DD prefix and opcode, two operands
        ("fd210010", [0, 1], [2, 3]),  # LD IY,nn
        ("fddd210010", [0, 1, 2], [3, 4]),  # a stray FD is its own M1 (Young 3.7)
        ("dded44", [0, 1, 2], []),  # DD before ED is a stray prefix
        ("dd7e05", [0, 1], [2, 0x1005]),  # LD A,(IX+5): displacement is a data read
    ],
)
def test_each_opcode_and_prefix_byte_is_one_fetch_and_operands_are_reads(
    program: str, fetches: list[int], reads: list[int]
) -> None:
    cpu, log = step_log(program, ix=0x1000)

    assert cpu.m1_cycles() == [(FETCH, address) for address in fetches]
    assert [address for tag, address, _ in log if tag == "r"] == reads


@pytest.mark.parametrize("prefix", ["dd", "fd"])
def test_index_cb_fourth_byte_is_read_outside_m1(prefix: str) -> None:
    # DD CB d op: two M1 cycles; d and op are ordinary reads (UM0080 p. 217's
    # 23 (4, 4, 3, 5, 4, 3); Young 6.1: R advances by 2).
    cpu, log = step_log(prefix + "cb0506", ix=0x1000, iy=0x1000)  # RLC (IX+5)

    assert log[:4] == [
        ("m1", FETCH, 0),
        ("m1", FETCH, 1),
        ("r", 2, 0x05),
        ("r", 3, 0x06),
    ]
    assert log[4:] == [("r", 0x1005, 0), ("w", 0x1005, 0)]
    assert cpu.r == 2


def test_repeating_block_instruction_fetches_both_bytes_on_every_repeat() -> None:
    cpu, _ = step_log("edb0", b=0, c=2, h=0x20, l=0, d=0x30, e=0)  # LDIR, BC=2

    cpu.step()
    assert cpu.m1_cycles() == [(FETCH, 0), (FETCH, 1), (FETCH, 0), (FETCH, 1)]


def test_halt_fetches_once_then_reports_one_halt_cycle_per_idle_step() -> None:
    cpu = M1Host(bytes.fromhex("76"), origin=0x0100)

    assert cpu.step() == 4  # HALT itself: an ordinary opcode fetch
    assert (cpu.halted, cpu.pc) == (True, 0x0101)
    for _ in range(3):
        assert cpu.step() == 4
    # Each idle cycle re-fetches the HALT opcode, data ignored (UM0080 p. 14).
    assert cpu.m1_cycles() == [(FETCH, 0x0100)] + [(HALT, 0x0100)] * 3
    assert [entry for entry in cpu.log if entry[0] != "m1"] == []
    assert cpu.r == 4


def test_nmi_response_is_one_nmi_cycle_at_pc_before_the_push() -> None:
    cpu = M1Host(bytes.fromhex("00"), origin=0x1234)
    cpu.request_non_maskable_interrupt()

    assert cpu.step() == 11
    assert cpu.log == [("m1", NMI, 0x1234), ("w", 0xEFFF, 0x12), ("w", 0xEFFE, 0x34)]
    cpu.step()
    assert cpu.log[-1] == ("m1", FETCH, 0x0066)


def test_nmi_waking_halt_reports_the_nmi_cycle_and_no_halt_cycle() -> None:
    cpu = M1Host(bytes.fromhex("76"), origin=0x0200)
    cpu.step()
    cpu.step()  # one idle cycle
    cpu.request_non_maskable_interrupt()

    assert cpu.step() == 11
    assert cpu.m1_cycles() == [(FETCH, 0x0200), (HALT, 0x0200), (NMI, 0x0201)]


@pytest.mark.parametrize(
    ("mode", "vector", "t_states", "target"),
    [(0, 0xCF, 13, 0x0008), (1, 0xFF, 13, 0x0038), (2, 0x40, 19, 0x3456)],
)
def test_interrupt_acknowledge_is_one_cycle_in_every_mode(
    mode: int, vector: int, t_states: int, target: int
) -> None:
    cpu = M1Host(bytes.fromhex("00"), origin=0x0A50)
    cpu.memory[0x2040:0x2042] = bytes((0x56, 0x34))  # IM 2 table entry at I:vector
    cpu.i = 0x20
    cpu.im = mode
    cpu.iff1 = cpu.iff2 = True
    cpu.request_maskable_interrupt(vector)

    assert cpu.step() == t_states
    assert cpu.pc == target
    pushes = [("w", 0xEFFF, 0x0A), ("w", 0xEFFE, 0x50)]
    table = [("r", 0x2040, 0x56), ("r", 0x2041, 0x34)] if mode == 2 else []
    # The acknowledge comes first, PC on the address bus (UM0080 Figure 9);
    # the IM 2 table is read through read_byte, as before.
    assert cpu.log == [("m1", ACKNOWLEDGE, 0x0A50), *pushes, *table]


def test_reset_makes_no_m1_call() -> None:
    cpu = M1Host(bytes.fromhex("00"))
    cpu.request_reset()

    assert cpu.step() == 3
    assert cpu.log == []


def test_a_host_without_the_hook_sees_every_fetch_through_read_byte_as_before() -> None:
    # Fetches, operands, HALT and the lifecycle cycles: the same read_byte
    # accesses, order, T-states and state as at 0.4.0, and the hook defaults
    # to None so a later replacement of read_byte is followed.
    program = bytes.fromhex("dd210010 ddcb0506 ed44 fb 76")
    plain = LoggingCPU()
    plain.memory[: len(program)] = program
    plain.sp = 0xF000
    plain.im = 1
    assert plain.read_m1 is None

    t_states = [plain.step() for _ in range(6)]  # ... EI, HALT, one idle cycle
    plain.request_maskable_interrupt()
    t_states.append(plain.step())

    assert t_states == [14, 23, 8, 4, 4, 4, 13]
    assert [entry for entry in plain.log if entry[0] == "r"] == [
        ("r", 0, 0xDD),
        ("r", 1, 0x21),
        ("r", 2, 0x00),
        ("r", 3, 0x10),
        ("r", 4, 0xDD),
        ("r", 5, 0xCB),
        ("r", 6, 0x05),
        ("r", 7, 0x06),
        ("r", 0x1005, 0x00),
        ("r", 8, 0xED),
        ("r", 9, 0x44),
        ("r", 10, 0xFB),
        ("r", 11, 0x76),
    ]
    assert plain.pc == 0x0038


def test_a_hook_that_fetches_from_the_same_memory_changes_nothing_else() -> None:
    program = bytes.fromhex("dd210010 ddcb0506 ed44 cb11 fb 76 00")
    machines = []
    for hooked in (False, True):
        cpu = M1Host(program) if hooked else LoggingCPU()
        if not hooked:
            cpu.memory[: len(program)] = program
            cpu.sp = 0xF000
        cpu.im = 1
        t_states = [cpu.step() for _ in range(7)]
        cpu.request_maskable_interrupt()
        t_states.append(cpu.step())
        machines.append((cpu.capture_state(), t_states, cpu.log))

    (plain_state, plain_t, plain_log), (hooked_state, hooked_t, hooked_log) = machines
    assert hooked_state == plain_state
    assert hooked_t == plain_t
    # Replace each FETCH by the read it stands for and drop the cycles that
    # read nothing: the result is the unhooked host's log exactly.
    as_reads = [
        ("r", entry[2], program[entry[2]]) if entry[0] == "m1" else entry
        for entry in hooked_log
        if entry[0] != "m1" or entry[1] is FETCH
    ]
    assert as_reads == plain_log


class KabukiStyleHost(Z80CPU):
    """Opcode fetches and data reads of one address return different bytes.

    ``opcodes`` is what an M1 fetch sees and ``data`` what every other read
    sees, as on the QSound Z80, which decodes the two with different keys.
    """

    def __init__(self, opcodes: bytes, data: bytes) -> None:
        self.opcodes = bytearray(0x10000)
        self.data = bytearray(0x10000)
        self.opcodes[: len(opcodes)] = opcodes
        self.data[: len(data)] = data
        super().__init__(self.data.__getitem__, self.data.__setitem__, read_m1=self._fetch)

    def _fetch(self, address: int, kind: M1Cycle) -> int:
        return self.opcodes[address]


def test_opcode_fetch_and_data_read_of_one_address_can_differ() -> None:
    # Instructions at 0 (LD A,n), 2 (LD B,(IX+d)), 5 (LD A,(nn)), 8 (DD CB d op).
    # Every byte the CPU executes is in `opcodes`; every operand is in `data`.
    cpu = KabukiStyleHost(
        opcodes=bytes.fromhex("3e00 dd4600 3a0000 ddcb0000"),
        data=bytes.fromhex("aa55 7711ff cc0000 eeee0346"),
    )
    cpu.ix = 0x0003

    cpu.step()  # opcode 3E from `opcodes`, its operand data[1]
    assert cpu.a == 0x55
    cpu.step()  # d = data[4] = 0xFF (-1), so B = data[IX - 1] = data[2]
    assert cpu.b == 0x77
    cpu.step()  # nn = data[6..7] = 0000h, and A = data[0000h]
    assert cpu.a == 0xAA
    # DD CB from `opcodes`; d = data[10] = 3 and op = data[11] = 46h, BIT 0,(IX+3).
    # Had op come from `opcodes` (00h, RLC (IX+d)) it would have written memory.
    data_before = bytes(cpu.data)
    cpu.step()
    assert cpu.pc == 12
    assert cpu.f.z == 1  # bit 0 of data[6] = 00h is clear
    assert bytes(cpu.data) == data_before


def test_access_tracking_records_hooked_fetches_and_restores_the_hook() -> None:
    cpu = M1Host(bytes.fromhex("3e42 76"))
    hook = cpu.read_m1
    session = DebugSession(cpu, track_accesses=True)

    first = session.step()
    session.step()  # HALT
    idle = session.step()

    assert first.accesses == (("r", 0, 0x3E), ("r", 1, 0x42))
    assert idle.accesses == ()  # a HALT cycle is not a memory access the core makes
    session.close()
    assert cpu.read_m1 is hook


def test_read_m1_is_validated_replaceable_and_refused_as_a_method() -> None:
    memory = bytearray(0x10000)
    with pytest.raises(TypeError, match="read_m1 must be callable or None"):
        Z80CPU(memory.__getitem__, memory.__setitem__, read_m1=0x00)  # type: ignore[arg-type]

    cpu = Z80CPU(memory.__getitem__, memory.__setitem__)
    cycles: list[M1Cycle] = []
    cpu.read_m1 = lambda address, kind: cycles.append(kind) or memory[address]
    cpu.step()
    cpu.read_m1 = None
    cpu.step()
    assert cycles == [FETCH]

    with pytest.raises(TypeError, match="defines read_m1 as methods"):

        class MethodHost(Z80CPU):
            def read_m1(self, address: int, kind: M1Cycle) -> int:
                return 0


def test_a_board_counts_m1_cycles_of_each_kind_per_step() -> None:
    # The ColecoVision's use: one wait state per M1 cycle, the acknowledges
    # counted apart so the board can choose (its C11).
    memory = bytearray(0x10000)
    memory[:6] = bytes.fromhex("dd2a0000 fb 76")  # LD IX,(nn); EI; HALT
    counts = dict.fromkeys(M1Cycle, 0)

    def read_m1(address: int, kind: M1Cycle) -> int:
        counts[kind] += 1
        return memory[address]

    cpu = Z80CPU(memory.__getitem__, memory.__setitem__, read_m1=read_m1)
    cpu.sp, cpu.im = 0xF000, 1
    per_step = []
    for request in (None, None, None, None, "int", "nmi"):
        if request == "int":
            cpu.request_maskable_interrupt()
        elif request == "nmi":
            cpu.request_non_maskable_interrupt()
        before = dict(counts)
        cpu.step()
        made = {kind.value: counts[kind] - before[kind] for kind in M1Cycle}
        per_step.append({kind: n for kind, n in made.items() if n})

    assert per_step == [
        {"fetch": 2},  # DD 2A
        {"fetch": 1},  # EI
        {"fetch": 1},  # HALT
        {"halt": 1},  # idle
        {"acknowledge": 1},  # IM 1
        {"nmi": 1},  # NMI at 0038h's first boundary
    ]
