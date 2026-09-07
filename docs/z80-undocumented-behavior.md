# Z80 undocumented behavior: mechanism first, then the rules

The Z80 has behavior Zilog never documented that real software depends on:
two flag bits that copy whatever happened to be on an internal bus, an
address latch that leaks into one instruction's flags, and a refresh counter
games use as a random source. This core models all of it, and the vector
corpus checks all of it. This page explains *why* each effect exists, so the
rules below read as consequences instead of trivia. Each rule names the line
of source that encodes it; the comment on that line says the same thing in
one sentence.

Read [start-here](start-here.md) first if the register names are new to you.

## The mechanisms

### X and Y: bits 3 and 5 of F copy the internal bus

Bits 3 and 5 of the flag register have no defined meaning. On hardware they
are simply latched from whatever byte the ALU's result bus carries at the
moment flags are written. For ordinary arithmetic, logic, rotates, `INC`,
`DEC`, `DAA`, and `NEG` that byte is the result, so **X/Y are bits 3 and 5 of
the result**. `Flags.set_xy(value)` does the copy; `_set_xysz` in `_alu.py`
is the common path.

Every exception is a case where the byte on the bus is *not* the result:

- **`CP`** is a subtraction whose result is discarded. The operand is what
  remains on the bus, so X/Y come from the operand (`_alu.py`, `_cp`).
- **16-bit `ADD`/`ADC`/`SBC HL,rr`** finish with the high byte, so X/Y come from
  the high byte of the result (`_alu.py`, `_add16`, `_sub16`, `_op_add_hl_rr`).
- **`BIT n,(HL)`** reads memory through the address latch; X/Y come from the
  high byte of WZ, not from the byte tested (`_rotate.py`, `_op_bit`). The
  register form `BIT n,r` has no such exception. The indexed forms
  `BIT n,(IX+d)` behave the same way with WZ = IX+d (`_index.py`,
  `_op_index_bit`).
- **Block loads `LDI`/`LDD`** put A + transferred byte on the bus, and the two
  bits land in positions 3 and **1**, not 3 and 5 (`_blocks.py`, `_block_ld`).
- **Block compares `CPI`/`CPD`** use A - (HL) - H, the intermediate before the
  final correction, with the same 3-and-1 placement (`_blocks.py`,
  `_block_cp`).
- **Block I/O `INI`/`IND`/`OUTI`/`OUTD`** take S, Z, X, and Y from the new B,
  with N, H, C, and PV from sums involving the byte moved (`_io.py`,
  `_block_ini`, `_block_outi`).
- **Repeating forms** (`LDIR`, `CPIR`, `INIR`, `OTIR`, and the D variants)
  rewind PC by 2 and re-fetch. On each such repeat X/Y come from bits 3 and 5
  of the rewound PC's high byte, and WZ becomes PC + 1 (`_blocks.py`,
  `_block_repeat`). The I/O repeats additionally correct PV and H from B
  (`_io.py`, `_post_in_o_r`).
- **`SCF`/`CCF`** depend on Q, next.

### Q: what the previous instruction did to F

`SCF` and `CCF` write only C, H, and N; on hardware their X/Y still come from
the internal bus, which at that moment carries A OR-ed with whatever the flag
latch still holds. Whether the latch holds F or nothing depends on whether
the *previous* M1 cycle wrote flags. Emulators model this with a byte called
Q: equal to F after any instruction that writes flags, 0 after any that does
not. The rule is then:

```text
X/Y = bits 3 and 5 of  (A | F)   if Q == 0   (previous instruction left flags alone)
X/Y = bits 3 and 5 of   A        if Q != 0   (previous instruction wrote flags)
```

That is the genuine Zilog NMOS behavior, verified by raxoft's `z80ccf` test
against real silicon; CMOS Zilog parts and NEC clones differ, and this core
does not model them. `_core.py` `_update_q` is the whole Q model and is
called at the end of every instruction, including ones that do not touch
flags, because the "0" case is what `CCF` needs to see. A DD or FD prefix is
its own M1 cycle that writes no flags, so a prefixed `SCF`/`CCF` always sees
Q = 0; `_op_scf_ccf` takes a `prefixed` flag for that (`_alu.py`).

### WZ (MEMPTR): the address latch

The Z80 has one internal 16-bit temporary through which every computed
address and every 16-bit operand passes. It is called WZ in Zilog's own
terminology and MEMPTR in the community's. It is not readable by any
instruction; its only architectural leak is `BIT n,(HL)` above. But because
that leak is observable, the vectors check WZ after every instruction, and a
port has to track it exactly.

The pattern: an instruction that reads or writes through a 16-bit address
leaves WZ at **address + 1**, because the last thing the latch did was step to
the high byte (`LD A,(nn)`, `LD HL,(nn)`, `LD (nn),rr`, `IN A,(n)`, `ADD HL,rr`,
`RLD`/`RRD`). Jumps, calls, `RST`, and returns leave WZ at the **target**
(`JP` even when not taken, because the operand fetch itself loads the latch;
`JR` only when taken, because the target is never computed otherwise).
`EX (SP),HL` leaves the value read from the stack. Two forms are odd:
`LD (BC)/(DE)/(nn),A` and `OUT (n),A` step only the low byte of the address
and overwrite the high byte with A, the value that was on the data bus, giving
WZ = A:(addr+1 & 0xFF) (`_loads.py`, `_io.py`). `CPI`/`CPD` step WZ by +/-1
each iteration; `LDI`/`LDD` leave it alone; the repeats set it to PC + 1 as
above. Every WZ write in the source has a comment naming which of these it is.

### R: the refresh counter

R increments once per M1 cycle in its low 7 bits; bit 7 is preserved and only
`LD R,A` can set it (`_core.py`, `_inc_r`). "Per M1 cycle" means once per
opcode fetch **and once per prefix byte**, never for operand or displacement
bytes. So an unprefixed instruction adds 1, `ED xx` and `DD xx` add 2, and
`DD CB d xx` adds 2, not 4, because the trailing opcode byte is fetched as an
operand (`_index_dispatch.py`). A `HALT`ed CPU keeps fetching and adds 1 per
idle step. Interrupt and NMI acceptance add 1.

### Prefix runs: DD and FD are flags, not instructions

A DD or FD byte does not execute anything. It sets a flag that says "use IX
(or IY) instead of HL" for the opcode that follows, and the flag is reset by
whatever byte comes next. Three consequences, all in `_index_dispatch.py`,
`_execute_index`:

- **A run of DD/FD bytes is one instruction.** Each stray prefix is its own
  M1 cycle, so it costs 4 T-states and increments R, and does nothing else;
  the last prefix in the run decides the register. `FD DD 21 00 10` is
  `LD IX,1000h` in 18 T-states with R advanced by 3.
- **DD/FD before ED is a stray.** ED opens an instruction set that never uses
  the substitution, so `DD ED 44` is `NEG` in 12 T-states with R advanced by
  3. (`DD CB` is different: it opens its own table, section above.)
- **No interrupt is accepted inside the run.** Hardware samples INT only at
  the end of an instruction, and the flag would be lost if it accepted one
  after a prefix; a run of DDs holds interrupts off exactly as a run of EIs
  does. This core gets that for free, because the run is one `step()`.

The disassembler (`disasm.py`, `_decode_index`) follows the same rule, so an
instruction's bytes in a trace include its stray prefixes.

This is the one rule on this page with no hardware-captured vector behind it.
The SingleStepTests corpus has no file for these sequences and z80test does
not execute them. The rule is Sean Young's, *The Undocumented Z80 Documented*
v0.91, section 3.7 ("In a large sequence of DD and FD bytes, it is the last
one that counts. Also any other byte (or instruction) resets this flag"),
section 6.1 ("Just a stray DD or FD increases the R by one"), and chapter 5
(no interrupts during a run). The only vector any test set holds is FUSE's
`ddfd00` (DD FD 00 00 costs 16 T-states over two instructions and leaves R at
4), which is emulator-derived and which `tests/test_prefix_sequences.py`
replays. Real software does emit these sequences, which is why the rule is
implemented rather than left as an error.

### Other undocumented instructions the core implements

- IXH/IXL/IYH/IYL as 8-bit registers in every DD/FD form that names H or L
  outside an `(IX+d)` operand (`_index.py`).
- `DD CB`/`FD CB` rotates, `RES`, and `SET` with z != 6 also copy the result
  into `r[z]` (`_index.py`, `_op_index_rot`, `_op_index_res_set`).
- `SLL` (CB 30-37): shift left and set bit 0 (`_rotate.py`, `_sll`).
- `IN (C)` / `IN F,(C)` (ED 70): sets flags, stores nothing (`_io.py`).
- `OUT (C),0` (ED 71): NMOS parts output 0 (`_io.py`).
- Every undefined ED opcode is an 8-T-state NOP (`_dispatch.py`).
- `NEG`, `RETN`, and `IM` have several aliases in the ED table.

## Where the truth lives

The rules above are derived from the code, and the code is derived from
oracles, in this order of authority:

1. The pinned SingleStepTests corpus checks every rule on this page for every
   opcode, including WZ, Q, R, and T-states. If this page and a vector
   disagree, the vector wins; fix the page.
2. raxoft/z80test checks flags, including `SCF`/`CCF`, against a real Zilog
   NMOS Z80.
3. ZEXALL checks the same X/Y behavior across long sequences.

Sources cited on this page and in the handlers' comments:

- Sean Young, *The Undocumented Z80 Documented*, version 0.91, 18 September
  2005 (GNU FDL): <http://www.z80.info/zip/z80-documented.pdf>. Section 4.3
  for the block I/O flags, 3.7 and 6.1 for prefix runs, chapter 5 for
  interrupts.
- FUSE, the Free Unix Spectrum Emulator, `z80/tests/tests.in` and
  `tests.expected` (GPL-2.0): 1,242 emulator-derived cases, of which
  `ddfd00` is the one prefix-run vector.

If you need a rule that is not here, look at the comment on the handler first;
the generator inside the fetched corpus
(`tests/z80_test_vectors/generation/z80_test_generator.js`) is the last resort
and is not part of this repository. When you learn something new, add it to
this page and to the line of code that implements it.
