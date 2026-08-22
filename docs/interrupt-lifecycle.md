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

## Non-maskable interrupts

A device requests an NMI with `cpu.request_non_maskable_interrupt()`. The request
is latched until the next `step()` and can be cancelled before then with
`cpu.clear_non_maskable_interrupt()`. `cpu.non_maskable_interrupt_pending` exposes
the latched state. At an instruction boundary an NMI takes priority over a maskable
request, ignores `IFF1` and EI delay, wakes HALT, increments `R`, pushes the
boundary PC, copies `IFF1` to `IFF2`, clears `IFF1`, and enters `0x0066` in 11
T-states. Repeated requests while one is pending coalesce into one NMI.

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
until an accepted maskable interrupt wakes it.

## Scope

This API covers the common interrupt lifecycle needed by single-CPU machine hosts,
including arcade boards and home-computer emulators. It does not model
interrupt-acknowledge bus callbacks, daisy-chain priority, floating-bus values,
cycle-accurate timing, or memory contention.