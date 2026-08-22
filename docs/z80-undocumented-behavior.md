# Z80 Undocumented Behavior — Read This Before Touching Flags

**Read this before grepping/paging through `tests/z80_test_vectors/generation/z80_test_generator.js`.**
Every opcode-group task so far has independently re-derived the Q register, WZ
(MEMPTR), and undocumented X/Y flag mechanics from scratch by reading that file
in a dozen-plus small chunks and grepping for the same handful of symbols. That
repeated research is the single biggest cause of tasks failing on "exceeded
maximum turns" or a blown context window — not incorrect CPU logic. This
document exists to make that a one-time cost instead of a per-task cost.
**If you learn something about undocumented behavior that isn't written down
here, add it to this file before finishing your task** — that's what makes
the investment compound instead of resetting for the next task.

## Reusable infrastructure that already exists — use it, don't re-derive it

The private implementation modules under `src/z80_python/` already have the
plumbing for all three mechanisms below. The stable public API remains in
`src/z80_python/cpu.py`.
Call the existing methods; do not re-implement flag-copying logic per opcode.

- `Flags.set_xy(value)` — copies bits 3 and 5 of `value` into the undocumented
  X/Y flags. Call this with whatever byte the *general rule* below says X/Y
  should come from for your instruction.
- `self.q` + `self._update_q(flags_modified: bool)` — the Q register. Call
  `self._update_q(True)` at the end of any instruction that writes `self.f`,
  `self._update_q(False)` for every other instruction (including ones that
  read flags but don't change them). This must be called for **every**
  instruction, not just flag-affecting ones — CCF/SCF need to see a `q` of
  `0` when the *previous* instruction didn't touch flags.
- `self.wz` — the WZ/MEMPTR internal address latch, plus `self._io_data` —
  the last byte transferred by a block I/O step (read back by the repeated
  block I/O instructions for their post-repeat flag adjustment). Several load
  instructions already set `wz` correctly (see `LD A,(nn)` / `LD (nn),A` in
   `_loads.py` for the pattern) — follow that same pattern for any new
  instruction that computes a 16-bit address, rather than reasoning about WZ
  from first principles again.

## The Q register (drives CCF/SCF's undocumented X/Y behavior)

Q is not an official Zilog register name — it's the bookkeeping convention
this test oracle (and most high-accuracy emulators) uses to track "did the
immediately preceding instruction write the F register, and if so, what did
it leave behind." `CCF` and `SCF`'s undocumented X/Y flags depend on whether
the prior instruction modified flags. **The exact bit formula for CCF/SCF is
one of the hairiest corners in the entire undocumented-behavior space** (see
Patrik Rak's "Z80 SCF/CCF Flags Reloaded") — don't guess it from memory or
first-principles reasoning. Grep the generator for the exact formula (search
terms below) and, more importantly, just implement it against the `cb 00`-style
JSON vectors directly (`ed 44.json`-equivalents for whichever opcode you're
on) — the vectors are ground truth regardless of what any doc (including this
one) says.

## WZ / MEMPTR

An internal 16-bit address latch, not directly readable by any instruction,
but observable through its effect on a small number of instructions' flags.
General rule of thumb for *when it's set*: any instruction that computes a
16-bit address as part of its own operation (`LD A,(nn)`/`LD (nn),A`,
`LD dd,(nn)`/`LD (nn),dd`, `EX (SP),HL`, indexed `(IX+d)`/`(IY+d)` forms,
`JP (HL)`, block I/O port reads, relative jumps, `CALL`/`RST`) sets WZ to that
computed address (usually address+1 for the high-byte-follow-up case — see
the existing `LD A,(nn)` implementation for the exact pattern). The specific
corner that actually matters for flags: **`BIT n,(HL)` and `BIT n,(IX+d)` /
`BIT n,(IY+d)` copy the undocumented X/Y flags from the high byte of WZ, not
from the tested byte itself.** This is the single most common place a BIT-group
task gets X/Y wrong. Non-indexed `BIT n,r` (register form) has no such
exception — X/Y there just come from the general rule below.

Block transfer/search group: the non-repeated `LDI`/`LDD` leave WZ untouched,
while `CPI`/`CPD` step WZ by ±1 on every iteration.  The repeated variants
(`LDIR`/`LDDR`/`CPIR`/`CPDR`) additionally rewind PC by 2 on every non-final
iteration and set **WZ = rewound PC + 1**, also copying X/Y from PC bits 11/13
— so a multi-iteration `CPIR`/`CPDR` loop ends with WZ derived from the
instruction address (e.g. a `CPIR` at 0x1000 finishes at WZ 0x1002), not from
whatever WZ held before the loop.  Each repeated step costs 21 T-states; the
final (non-rewinding) step costs 16.

## X/Y flags (bits 3 and 5) — the general rule, then the named exceptions

**General rule**: for the large majority of flag-affecting instructions
(8-bit ALU ops, INC/DEC, rotates/shifts, `AND`/`OR`/`XOR`, `CP`, `DAA`, `NEG`),
X and Y are a direct copy of bits 3 and 5 of the instruction's own 8-bit
result — call `self.f.set_xy(result)` with that result byte and you're done.
Named exceptions that need special-casing (grep the generator for each,
don't assume the general rule applies):

1. **`BIT n,(HL)` / `BIT n,(IX+d)` / `BIT n,(IY+d)`** — X/Y come from WZ's
   high byte (see above), not from the tested value. Register-form `BIT n,r`
   is NOT an exception.
2. **`CCF` / `SCF`** — depend on `self.q` (see above). Verify the exact
   formula against the vectors, don't guess it.
3. **Block LD group** (`LDI`/`LDD`/`LDIR`/`LDDR`) — X/Y come from
   `A + transferred_byte`, not from any flag-style "result." Bit 3 of that
   sum goes to the undocumented X-equivalent slot and bit 1 to the
   Y-equivalent slot (the bit positions are shuffled relative to a normal
   `set_xy` call for this group specifically — verify against `ed a0.json`
   (`LDI`) directly rather than assuming `set_xy` applies as-is).
4. **Block CP group** (`CPI`/`CPD`/`CPIR`/`CPDR`) — X/Y come from
   `A - (HL) - half_carry_bit`, with the same bit-position shuffle as the
   block LD group. Verify against `ed a1.json` (`CPI`) directly.

## Efficient research protocol (if this doc doesn't cover your opcode)

1. Check this file and the instruction-family modules under `src/z80/` first —
   most of the mechanism you need probably already exists. Core state and
   register helpers are in `_core.py`; arithmetic helpers are in `_alu.py`.
2. If you must consult `z80_test_generator.js`, use a **specific** grep
   pattern and read only the matched region once — don't page through broad
   line ranges speculatively. Patterns that have reliably found the relevant
   code in this codebase so far: `set_q|sq|this\.Q`, `WZH|WZL`,
   `setXY|parity\(`, plus the instruction's own mnemonic (e.g. `BIT_o|RES_o`).
3. Once you've found the formula, **implement and verify it against the
   actual JSON vectors** (`tests/z80_test_vectors/v1/<opcode>.json`) — that's
   the real ground truth this whole project is validated against, not the
   generator source or this document.
4. If you find a real discrepancy between this document and the vectors, the
   vectors win — fix this document to match before finishing your task.
