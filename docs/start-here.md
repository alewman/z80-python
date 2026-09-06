# Start here: the Z80 as this core models it

This page is for someone who knows what a CPU is, has perhaps written a 6502
or ARM interpreter, and has never touched a Z80. It gives you the one key the
source assumes you already hold: the register file, the flag byte, the way an
opcode byte is split into fields, and the prefix model. With that, every
handler under `src/z80_python/` reads as a direct statement of hardware
behavior. Nothing here is a substitute for the code; the code is the reference.

## Register file

| Name | Width | In this core | Notes |
| --- | --- | --- | --- |
| A, F | 8 | `cpu.a`, `cpu.f` (a `Flags` object; `cpu.f.byte` is the raw value) | Accumulator and flags; together the pair AF |
| B, C, D, E, H, L | 8 | `cpu.b` ... `cpu.l` | General registers; pairs BC, DE, HL |
| AF', BC', DE', HL' | 16 | `cpu.af_`, `cpu.bc_`, `cpu.de_`, `cpu.hl_` | Alternate set. `EX AF,AF'` swaps AF; `EXX` swaps the other three |
| IX, IY | 16 | `cpu.ix`, `cpu.iy` | Index registers. Their halves IXH/IXL/IYH/IYL are usable as 8-bit registers (undocumented but universal) |
| SP, PC | 16 | `cpu.sp`, `cpu.pc` | Stack grows down; `PUSH` writes high byte then low byte |
| I | 8 | `cpu.i` | High byte of the IM 2 vector table address |
| R | 8 | `cpu.r` | Memory refresh counter, see below |
| IFF1, IFF2, IM | flags | `cpu.iff1`, `cpu.iff2`, `cpu.im` | Interrupt enable, its shadow, and the interrupt mode (0, 1, 2) |
| WZ, Q | 16, 8 | `cpu.wz`, `cpu.q` | Internal, not architecturally visible, see below |

HL is the "memory pointer" register: `(HL)` appears wherever an instruction
takes a register operand, occupying the slot a seventh register would. BC and
DE can also address memory but only for `LD A,(BC)` / `LD (DE),A` style loads.
The complete processor-owned state, and nothing else, is the field list of
`CPUState` in `state.py`.

## The F byte

```text
bit:   7   6   5   4   3   2    1   0
flag:  S   Z   Y   H   X   P/V  N   C
```

- **S** sign, bit 7 of the result. **Z** zero. **C** carry or borrow out of bit 7.
- **H** half-carry, the carry out of bit 3. **N** is 1 after a subtraction.
  Both exist only so `DAA` can correct BCD arithmetic afterwards.
- **P/V** is overloaded. Add and subtract set it to signed overflow. Logic
  ops, rotates, and `IN r,(C)` set it to even parity of the result. Block
  instructions set it to "BC is not yet zero". `LD A,I` and `LD A,R` set it to
  IFF2, the only way software can read the interrupt-enable state.
- **X** and **Y** (bits 3 and 5) are undocumented. Most instructions copy bits
  3 and 5 of their result into them. The exceptions are the whole subject of
  [undocumented-behavior](undocumented-behavior.md).

`_flags.py` is the whole implementation: one byte with named accessors and
`set_xy(value)`, which copies bits 3 and 5 of `value`.

## How an opcode byte is decoded

Every unprefixed opcode is three bit fields, and the handlers decode with
shifts and masks rather than a lookup table because the fields are that
regular:

```text
opcode = xx yyy zzz        x = opcode >> 6      y = (opcode >> 3) & 7      z = opcode & 7
```

| x | Meaning | Example |
| --- | --- | --- |
| 01 | `LD r[y], r[z]` for every pair of registers, except 0x76 which is `HALT` | 0x78 = `LD A,B` |
| 10 | `alu[y] A, r[z]` | 0x91 = `SUB C` |
| 00, 11 | Mixed: loads, 16-bit ops, jumps, calls, stack, selected by z and y | 0xC3 = `JP nn` |

The tables the fields index, exactly as the code orders them:

| Table | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | Where in code |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r | B | C | D | E | H | L | (HL) | A | `_core.py` `_read_reg` / `_write_reg` |
| rp (16-bit) | BC | DE | HL | SP | | | | | `_core.py` `_read_pair`, index is `(opcode >> 4) & 3` |
| rp2 (stack) | BC | DE | HL | AF | | | | | `PUSH`/`POP` handlers in `_loads.py` |
| cc (condition) | NZ | Z | NC | C | PO | PE | P | M | `_control.py` `_cond_true` |
| alu | ADD | ADC | SUB | SBC | AND | XOR | OR | CP | `_alu.py` `_alu_a` |
| rot | RLC | RRC | RL | RR | SLA | SRA | SLL | SRL | `_rotate.py` `_rot_apply` |

So when you read `dest = (opcode >> 3) & 0x07` in a handler, that is y, and
`src = opcode & 0x07` is z. Register index 6 is `(HL)` and is why every
register-operand handler has an `if src == 6:` branch that reads memory and
costs 3 more T-states. `RST p` jumps to `y * 8`. Conditional jumps, calls, and
returns use y as cc. The same reading applies to the disassembler's tables at
the top of `disasm.py`, which are the same lists.

## Prefixes

Four prefix bytes open larger tables. Each prefix is fetched as its own M1
cycle on hardware, which is the single fact behind three otherwise puzzling
rules: a prefix costs 4 T-states, increments R, and behaves like an
instruction that writes no flags (so Q reads as 0 afterwards).

| Prefix | Table | Rule |
| --- | --- | --- |
| CB | Rotates, `BIT`, `RES`, `SET` | Second byte is `xx yyy zzz` again: x selects rot / BIT / RES / SET, y is the rotate kind or bit number, z is r |
| ED | 16-bit loads and arithmetic, block instructions, `IN r,(C)`, `OUT (C),r`, `NEG`, `IM`, `RETN`/`RETI`, `LD A,I` and friends | Any ED byte without a definition is a real 8-T-state NOP |
| DD / FD | IX / IY | Take the unprefixed instruction and substitute: HL becomes IX (or IY), `(HL)` becomes `(IX+d)` with a signed displacement byte, and H/L become IXH/IXL, except inside a `(IX+d)` form. Opcodes that do not mention HL, H, or L run unchanged, plus the 4 T-states and the R increment |
| DD CB / FD CB | Indexed rotates and bit ops | Byte order is `DD CB d op`; the displacement comes before the final opcode. R advances by 2, not 4, because the last byte is read as an operand. The undocumented forms with z != 6 also copy the result into `r[z]` |

`_dispatch.py` and `_index_dispatch.py` are those tables written as if-chains.
The explicit shape is deliberate: it is what PyPy compiles well, and every
opcode is one grep away.

## T-states

`step()` returns the documented T-state total for the instruction it ran. The
building blocks are an M1 opcode fetch at 4, a memory read or write at 3, an
I/O read or write at 4, and a few internal cycles the manual lists per
instruction. Conditional instructions return different totals taken and not
taken; repeating block instructions return 21 per repeat and 16 for the last
iteration. Every handler's docstring states its totals where they vary. The
vector gate checks all of them, see [validation](validation.md).

## Three internal registers you have not met

**WZ (also called MEMPTR)** is the CPU's 16-bit address temporary. Any
instruction that assembles a 16-bit address, or reads a 16-bit operand, leaves
it in WZ, usually as the address plus one because the high-byte access is the
last thing the latch did. It is invisible except through one leak: `BIT n,(HL)`
takes X and Y from WZ's high byte. Emulators track it only for that.

**Q** mirrors the ALU's last flag write. It equals F after any instruction that
wrote flags and is 0 after one that did not. Only `SCF` and `CCF` read it, to
decide whether X and Y come from A alone or from F or A. `_core.py`
`_update_q` is the entire model; every handler calls it.

**R** counts M1 cycles in its low 7 bits so DRAM gets refreshed; bit 7 is only
written by `LD R,A`. Reading it is a cheap random number for games, which is
why emulators must count it exactly: one per opcode fetch, one per prefix,
none for operand bytes.

The comments on the lines that implement each of these say why the hardware
does it. [undocumented-behavior](undocumented-behavior.md) collects the rules
in one place.

## Interrupts

RESET, NMI, and maskable interrupts are modeled as transitions between
instructions, not as bus cycles. [interrupt-lifecycle](interrupt-lifecycle.md)
is complete and explains the EI delay, why NMI preserves IFF1 in IFF2, and the
one opt-in erratum.

## Suggested reading order

1. This page.
2. `_flags.py`, then `_alu.py` down to `_cp`, then `_control.py`. Registers,
   flags, and conditions.
3. `_core.py` for fetch, R, Q, and the interrupt acceptance paths, with
   [interrupt-lifecycle](interrupt-lifecycle.md) beside it.
4. `_dispatch.py` with the tables above open, then the remaining instruction
   modules in any order.
5. [undocumented-behavior](undocumented-behavior.md) and
   [validation](validation.md).

## Porting this core to another language

The state to carry is exactly the `CPUState` field list. Transcribe the
handlers module by module; they contain no Python-specific cleverness. Then
validate the way this project does, in order of cost:

1. **SingleStepTests** (`scripts/fetch_test_vectors.py`). One JSON file per
   opcode, 1,000 cases each. Each case has `initial` and `final` register
   snapshots with a `ram` list of `[address, value]` pairs, an optional
   `ports` list of `[address, value, "r" | "w"]` in access order, and a
   `cycles` array with one entry per T-state. Ignore the `ei` and `p` keys.
   A runner is about forty lines in any language; `validation/vector_utils.py`
   is the reference one.
2. **ZEXDOC / ZEXALL** for long-sequence CRC checks under a CP/M stub, see
   `validation/zex.py`.
3. **raxoft/z80test** for flags captured from real silicon, see
   `validation/z80test_runner.py`.

Passing the first gives you instruction semantics, timing, and every
undocumented flag in the corpus. The other two are what let this project say
its claims hold over millions of instructions and against hardware.
