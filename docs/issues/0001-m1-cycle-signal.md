# 0001: An M1-cycle signal for boards

Status: implemented on branch `m1-fetch-hook` (local), approved by the owner
on 2026-11-12. This repository had no issue or decision records before this
one; this file starts `docs/issues/`, numbered from 0001.

## The request

Two boards of the family cannot be built without seeing the Z80's M1 cycles.
At 0.4.0 the core fetches every opcode through the same `read_byte` callable
as every data read, so a host cannot tell an M1 cycle from a memory read, and
the M1 cycles that read nothing the CPU uses (HALT, the NMI response, the
interrupt acknowledge) are invisible to it.

**ColecoVision** (`colecovision-python`, handoff brief, open decision 3;
memory map, "The M1 wait state"). A 74LS74 held reset while `/M1` is high pulls
`/WAIT` low for one clock in every M1 cycle, so every opcode fetch takes 5
clocks, not 4. Every prefix byte is its own M1 cycle; `DD CB d op` gains 2,
not 4. On the board's drawings the interrupt acknowledge, the NMI response
and each HALT cycle are M1 cycles too and get the wait; MAME 0.285 gives the
wait to fetches and HALT but not to the acknowledges. The board keeps both
behind a parameter (its item C11), so it needs the M1 cycles of HALT, the NMI
response and the interrupt acknowledge **counted separately** from opcode
fetches. Its I/O decoder also has no `/M1` term (item U3): an interrupt
acknowledge, which is an `/IORQ` cycle with PC on the address bus, strobes
the VDP's read when PC's low byte is in `A0-BF`. The board therefore needs
the acknowledge cycle's address too.

**CPS-1 QSound** (`cps1-python`, handoff brief, open decision 8; sound.md,
"Kabuki"). The QSound Z80 is a Kabuki: on-chip decryption that decodes an
opcode fetch with one key and every other read with another, so the same
address yields different bytes for an opcode fetch and a data read. The board
needs an optional callable used by the M1 fetch only, prefix bytes included,
and not the `op` byte of `DD CB d op`, which the CPU reads outside M1.

## What the sources establish

From Zilog's *Z80 CPU User Manual* (UM0080, pinned in
[validation](../validation.md#the-sources-every-handler-cites)) and Young's
*The Undocumented Z80 Documented* v0.91, the two documents every handler
already cites:

| Cycle | What happens on the bus | Source |
| --- | --- | --- |
| Opcode fetch | `/M1` with `/MREQ` and `/RD`: "the current machine cycle is the op code fetch cycle of an instruction execution". 4 T-states, then the refresh address. | UM0080 p. 6 (pin `M1`), p. 9 (Figure 5) |
| Prefix bytes CB, ED, DD, FD, and the opcode after each | Each prefix is its own M1 cycle ("prefixes have their own M1"), so an `ED xx`, `CB xx` or `DD xx` instruction makes two M1 cycles, and each stray DD/FD of a run one more. | Young 6.1; Young 3.7; UM0080's T-state breakdowns, e.g. `LD IX,nn` 14 (4, 4, 3, 3) |
| `DD CB d op` / `FD CB d op` | Two M1 cycles (DD, CB). `d` and `op` are read in ordinary memory-read cycles: R advances by 2, "weird enough" (Young 6.1), and the manual's breakdown for `RLC (IX+d)` is 23 (4, 4, 3, 5, 4, 3): two 4-T-state M1 cycles, a 3-T-state read of `d`, and a 5-T-state cycle reading `op` (a 3-T-state read plus 2 internal states), where an M1 would be 4. | Young 6.1; UM0080 p. 217 |
| HALT | "Each cycle in the HALT state is a normal M1 (fetch) cycle except that the data received from the memory is ignored and an NOP instruction is forced internally", and "The HALT instruction is repeated". Young: the CPU "does not increase the PC so that the instruction is re-executed". So each 4-T-state idle cycle is an M1 cycle at HALT's own address. | UM0080 p. 14 (HALT Exit, Figure 11); Young 5.4 |
| NMI response | "similar to a normal memory read operation. The only difference is that the contents of the data bus are ignored"; Figure 10 shows `/M1`, `/MREQ` and `/RD` with PC on the address bus. One M1 cycle, then the push. | UM0080 p. 13-14 (Figure 10) |
| Maskable interrupt acknowledge, IM 0/1/2 | "a special M1 cycle is generated. During this special M1 cycle, the IORQ signal becomes active (instead of the normal MREQ) ... Two wait states are automatically added to this cycle." Figure 9 shows PC on the address bus. One such cycle in every mode; IM 0 takes the instruction from the data bus in it, and IM 2 the low vector byte. | UM0080 p. 12-13 (Figure 9), p. 19-20 (modes 0, 1, 2) |

What the repository's timing documents say about the `DD CB` fourth byte: the
docs on `main` (`docs/undocumented-behavior.md`, "R: the refresh counter";
`docs/start-here.md`, the prefix table) state that it "is fetched as an
operand" and that R therefore advances by 2, and the core has always read it
with `_read_operand_byte`. The SingleStepTests pin traces agree on order and
spacing: the access-timing table derived from them on `origin/main`
(`_access_timing.py`, not on this branch's base) puts the reads of
`DD CB d 06` (`RLC (IX+d)`) at T-state offsets 1, 5, 9, 12, 17: the `op` byte is read 3
T-states after `d`, which is an ordinary read cycle, not a 4-T-state M1. No
source here observes the `/M1` pin itself (the corpus's pin strings carry only
RD, WR, MREQ and IORQ), so the claim rests on the manual's breakdown, Young's
R count and the emulator-derived spacing, which agree. Both requesters
reached the same reading independently (MAME's measured `+2` on the
ColecoVision; Kabuki's data key for operands).

Two points the sources leave open, recorded rather than guessed:

- **HALT's address.** UM0080 and Young say the HALT opcode is re-fetched,
  that is, at HALT's own address. This core advances PC past HALT when it
  executes it (the pushed return address is the same either way), so the
  idle cycles report `(pc - 1) & 0xFFFF`. Sources outside the repository's
  citations that put the halted fetch at the following byte would change only
  that address, not the count.
- **The acknowledge address when an interrupt wakes HALT.** Young 5.4: "The
  PC is increased before the interrupt routine is called", without saying
  whether that is before or after the acknowledge cycle. The core reports its
  PC (the address it pushes). A board that cares (the ColecoVision's U3 when
  the spinner interrupt arrives during HALT) can subtract one.

## Options

1. **A per-step count attribute** (`cpu.m1_cycles` after each `step()`).
   Serves the ColecoVision's count but not Kabuki's byte, and the core would
   pay a counter increment on every fetch whether or not anyone reads it.
2. **A constructor option that adds N T-states per M1.** Puts machine
   policy (the board's wait logic, and its C11 choice) in the core, and does
   nothing for Kabuki. Rejected by the core's boundary: waits are the host's.
3. **`read_opcode(address)` alone**, defaulting to `read_byte`, as the CPS-1
   brief sketched. Serves Kabuki and lets the ColecoVision count fetches, but
   the HALT, NMI and acknowledge cycles read nothing the CPU uses and would
   either stay invisible or arrive as reads indistinguishable from fetches.
4. **Two callables**: `read_opcode(address)` for fetches and a second
   notification for the other three kinds. Works, but splits one hardware
   signal (`/M1`) across two hooks with different shapes.
5. **One callable per M1 cycle that says which kind it is** (chosen). The
   core calls `read_m1(address, kind)` for every M1 cycle and, for an opcode
   fetch, executes the byte it returns. Kabuki returns its opcode image;
   the ColecoVision counts calls by kind and reads the acknowledge's address.

Either default from options 3-5 must not be a copy of `read_byte` taken at
construction: the embedding contract lets a host replace `read_byte` at any
time (`tests/test_public_api.py`, and the debugger's access tracking does it),
and a copied default would keep fetching from the old callable.

## Design

`Z80CPU(read_byte, write_byte, *, read_port=None, write_port=None,
read_m1=None)`.

- `read_m1(address, kind) -> int`, optional, a plain attribute like the
  other four, replaceable or set to `None` at any time. When it is `None`
  (the default), nothing changes: opcode fetches go through `read_byte` as
  before, and HALT, NMI and the acknowledge make no call, exactly as at 0.4.0.
- `kind` is an `M1Cycle` (exported from `z80_python`):

  | `M1Cycle` | When | `address` | Return value |
  | --- | --- | --- | --- |
  | `FETCH` | every opcode byte, each prefix byte (CB, ED, DD, FD, stray DD/FD of a run) and the opcode after it; not `d` or `op` of `DD CB d op`, which stay `read_byte` reads | PC of the byte | the byte the CPU executes |
  | `HALT` | each 4-T-state idle `step()` of a halted CPU (not the HALT instruction's own fetch, which is a `FETCH`) | HALT's address, `(pc - 1) & 0xFFFF` | ignored, as the CPU ignores it |
  | `NMI` | the first cycle of an accepted NMI, before the push | PC (the address pushed) | ignored |
  | `ACKNOWLEDGE` | the acknowledge cycle of an accepted maskable interrupt, in IM 0, 1 and 2, before the push | PC (the address pushed) | ignored: the vector or RST opcode still comes from `request_maskable_interrupt(vector_byte)` |

- One call per M1 cycle, in bus order with the other accesses: a host counts
  M1 cycles of each kind per step (or per cycle, as it likes) and adds its
  own wait states; the core's T-states are unchanged (the acknowledge's two
  automatic wait states were always in its 13 or 19). The `DD CB` fourth
  byte, the IM 2 table read and every operand stay `read_byte` reads.
- RESET makes no call: the core models it as no fetch at all.
- `DebugSession(track_accesses=True)` wraps `read_m1` too when it is set and
  records each `FETCH` as the `("r", address, value)` it always recorded, so a
  step's access list is the same whether a host fetches through `read_byte`
  or `read_m1`. HALT, NMI and acknowledge calls are not recorded: the core
  never recorded a memory access for them.
- A subclass that defines `read_m1` as a method is refused, as the four bus
  methods are, since the instance attribute would silently shadow it.

Cost when unused: each fetch site loads `self.read_m1` and tests it for
`None` before calling `read_byte`; the lifecycle paths test it once per
HALT, NMI or acknowledge step. Measured below.

This does not open the scope boundaries the README states: the core still
passes the IM 0/IM 2 byte through `request_maskable_interrupt`, models no
daisy chain and no `WAIT` pin; it says when an M1 cycle happens and lets the
host decide what that costs.

## Results

To be filled in after the gate runs (before: `main` at `500608c`; after: this
branch).
