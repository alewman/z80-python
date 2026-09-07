# Interrupt Lifecycle

`z80-python` models maskable interrupts and NMIs as deterministic state
transitions at instruction boundaries. It deliberately does not attempt to expose
individual interrupt-acknowledge bus cycles or memory-contention timing.

## Host protocol

1. A device calls `cpu.request_maskable_interrupt(vector_byte)` between calls to
   `step()`. The default vector byte is `0xff`.
2. The request remains asserted while `IFF1` is clear or the instruction following
   `EI` is still required.
3. A later `step()` accepts the request before fetching another instruction. It
   returns the interrupt's T-state total rather than an instruction's total.
4. The host may cancel an unaccepted request with
   `cpu.clear_maskable_interrupt()`.

`cpu.maskable_interrupt_pending` exposes whether the request line is still asserted.
Hosts should schedule devices from the returned T-state totals; they must not alter
`PC`, `SP`, flags, or interrupt flip-flops to synthesize an interrupt.

## RESET

A host asserts RESET with `cpu.request_reset()` and releases it with
`cpu.clear_reset()`. `cpu.reset_pending` exposes the line level. RESET is modeled
as level-sensitive: every `step()` while it remains asserted returns 3 T-states
without fetching an instruction or accessing the stack. It takes priority over
NMI and maskable-interrupt requests, sets `PC` to `0x0000`, selects IM 0, clears
`IFF1` and `IFF2`, exits HALT, and cancels a pending EI delay.

This instruction core deliberately defines only those processor-state effects.
It preserves general registers, `SP`, `I`, `R`, `WZ`, and device request state;
the host owns device resets and decides when to release RESET. This models the
useful board-level lifecycle without claiming cycle-accurate reset-pin timing.

## Non-maskable interrupts

A device requests an NMI with `cpu.request_non_maskable_interrupt()`. The request
is latched until the next `step()` and can be cancelled before then with
`cpu.clear_non_maskable_interrupt()`. `cpu.non_maskable_interrupt_pending` exposes
the latched state. At an instruction boundary an NMI takes priority over a maskable
request, ignores `IFF1` and EI delay, wakes HALT, increments `R`, pushes the
boundary PC, copies `IFF1` to `IFF2`, clears `IFF1`, and enters `0x0066` in 11
T-states. Repeated requests while one is pending coalesce into one NMI.

That NMI ignoring `IFF1` and the EI delay is a certified claim, not a guess:
the Zilog manual's one-instruction acceptance delay is stated only for the
maskable interrupt, real ZX Spectrum hardware test ROMs (e.g. `EI48K`) probe
this exact ordering, and `validation.interrupt_crosscheck` confirms this
core's code path (NMI acceptance in `step()` is never gated by `_ei_delay`)
against an independent implementation.

### The "EI+NMI" IFF2 erratum (opt-in, unconfirmed on hardware)

`cpu.ei_nmi_iff2_erratum` (default `False`) models a reported NMOS-specific
quirk: when an NMI lands *inside* the one-instruction window right after
`EI` (i.e. `_ei_delay` is still nonzero at the moment the NMI is accepted),
`IFF2` is reset to `False` along with `IFF1`, instead of preserving `EI`'s
`IFF1` value for a later `RETN` to restore. The practical consequence: a
`RETN` after such an NMI cannot re-enable interrupts, even if they were
enabled (or had just been re-enabled by that same `EI`) beforehand.

This is sourced from gate-level ("Visual Z80" transistor-netlist) simulation
of the real NMOS chip, not a direct hardware measurement -- the researcher
who found it explicitly flagged it as possibly a simulator artifact pending
confirmation on real silicon. It does not affect this core's certified
default behavior (SingleStepTests/ZEXALL/z80test all pass with it left off,
and it is off by default) and should only be enabled by hosts deliberately
chasing NMOS authenticity for this specific corner, with that sourcing
caveat in mind. It has no effect outside the exact EI-then-immediate-NMI
window; ordinary NMI acceptance is unchanged.

## Acceptance behavior

Acceptance pushes the current instruction-boundary `PC`, clears `IFF1` and `IFF2`,
clears `halted`, increments the refresh register, and clears the pending request.

| Mode | Vector source | Result | T-states |
| --- | --- | --- | ---: |
| IM 0 | Device byte | RST opcode only | 13 |
| IM 1 | Fixed | `0x0038` | 13 |
| IM 2 | `I:vector_byte` table | Little-endian target from memory | 19 |

IM 0 is intentionally bounded to the eight device-supplied RST opcodes. A non-RST
byte raises `NotImplementedError` while leaving the request pending, rather than
silently pretending that arbitrary injected opcodes have correct bus semantics.

`EI` delays acceptance until one following instruction has completed; `DI` cancels
that delay and masks a pending request. A halted CPU performs 4-T-state idle steps
until an accepted maskable interrupt wakes it. A run of DD/FD prefixes and the
opcode that ends it is one `step()`, so a request is accepted after the run and
never inside it, matching hardware (Young, *The Undocumented Z80 Documented*,
chapter 5: a long sequence of DDs holds interrupts off like a sequence of EIs).

## Scope

This API covers the common interrupt lifecycle needed by single-CPU machine hosts,
including arcade boards and home-computer emulators. It does not model
interrupt-acknowledge bus callbacks, daisy-chain priority, floating-bus values,
cycle-accurate timing, or memory contention.