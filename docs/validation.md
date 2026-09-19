# Validation evidence and scope

## Claim

`z80-python` is a pure-Python Z80 instruction core that agrees with every
oracle below, each named with its tier. Against **hardware-captured** values it
passes raxoft z80test's `z80full`, `z80memptr` and `z80ccf` (every flag, WZ and
the SCF/CCF Q rule for the instructions z80test covers) and ZEXDOC/ZEXALL
(long-sequence CRCs found on a real Z80). Against **emulator-derived** values it
passes all 1,604,000 SingleStepTests cases (registers, flags, WZ, Q, R, memory,
I/O, T-states and memory-access order for every opcode), 1,350 of FUSE's 1,356
cases with the six others explained, and an interrupt-lifecycle cross-check
against an independent core. Runs of DD/FD prefixes rest on **documentation**
alone. The model includes RESET, maskable interrupts, NMI, the EI delay and
HALT wakeup at instruction boundaries. It does not claim cycle-accurate bus
signalling, a complete machine, CP/M, device scheduling or memory contention.

The specific lifecycle contract, mode coverage, and remaining exclusions are in
[interrupt-lifecycle.md](interrupt-lifecycle.md).

## Oracle tiers

Oracles are ranked by where their expected values came from:
**hardware-captured > hardware-corrected > emulator-derived > documentation**.
A lower-tier oracle is a detector, never a judge: when two disagree, the higher
tier decides, and a claim is only as strong as the highest tier that checks it.

| Oracle | Tier | Where its expected values came from | What it checks here | What it cannot see |
| --- | --- | --- | --- | --- |
| raxoft z80test 1.2a: `z80full`, `z80memptr`, `z80ccf` | hardware-captured | CRCs recorded on a 48K ZX Spectrum's Zilog NMOS Z80 | every flag (X/Y included) and register for most instructions; WZ through a following `BIT n,(HL)`; SCF/CCF after every instruction (Q) | T-states, bus order, interrupts, R, `RST`, prefix runs |
| ZEXDOC / ZEXALL (Cringle 1994) | hardware-captured | per-group CRCs "found empirically on a real Z80" (the program's own source) | long sequences of register, flag (ZEXALL: X/Y too) and memory state | WZ, Q, R, I/O, HALT, T-states, interrupts; a CRC names a group, not a case |
| (none for the Z80) | hardware-corrected | -- | -- | -- |
| SingleStepTests/z80, pinned revision | emulator-derived | a generator its README calls "a semi-port from Ares" | every opcode: registers, flags, WZ, Q, R, memory, I/O, T-states, and each memory access's kind, address, value and order | anything its generator gets wrong; interrupts |
| FUSE 1.6.0 `z80/tests` | emulator-derived | FUSE's own core | 1,356 single-instruction cases with bus events | where FUSE predates later findings (six cases, listed below) |
| superzazu/z80 cross-check | emulator-derived | an independent C core | the interrupt lifecycle: IM 0/1/2, NMI, EI delay, HALT | its own IM 0 bug (one xfail) |
| UM0080; Young v0.91 | documentation | Zilog's manual; Young's measurements and reading | every handler's rule, cited in its docstring; prefix runs (Young 3.7) | behaviour neither describes (WZ, Q) |

**Bus-transaction order has no hardware oracle at all.** Every hardware-tier
oracle compares state, not the sequence of accesses that produced it, so the
order claim below rests on SingleStepTests' pin traces and FUSE's bus events,
two emulator-derived sources that agree.

## Certification record: commit `9e15acc` (2026-09-06)

Reproduced on Linux x86_64 under both supported interpreters, CPython 3.14.4
and PyPy 7.3.20 / Python 3.11.13, against the pinned oracles named in the
sections below. The instruction core is byte-identical between `50125da` and
`9e15acc`; the CPython ZEX runs were started on the former and the later
commit changed only `scripts/fetch_z80test.py`.

| Gate | Result | CPython 3.14.4 | PyPy 7.3.20 |
| --- | --- | ---: | ---: |
| SingleStepTests, 1,604 files, 1,604,000 cases, registers + RAM + I/O + **T-states** + **bus transactions** | all passed | 28 s | 110 s (with fast suite) |
| Fast suite incl. `tests/test_readability.py` | 3,089 passed | 2 s | (included above) |
| ZEXDOC | `Tests complete`, no `ERROR` | 5,523.8 s | 358.4 s |
| ZEXALL | `Tests complete`, no `ERROR` | 5,623.7 s | 340.8 s |
| z80test `z80full` / `z80ccf` / `z80memptr` | all tests passed | 221.9 / 116.8 / 104.8 s | 8.9 / 4.0 / 6.3 s |
| Interrupt cross-check vs superzazu/z80 | 9 match, 1 xfail (oracle's known IM 0 double-charge) | < 1 s | < 1 s |

PyPy was installed from the official `pypy3.11-v7.3.20-linux64` tarball
(SHA-256 `1410db3a…ccb3e`, matching pypy.org's checksum page), the same
interpreter version as the 0.2.0/0.3.0 record.

Reproduction defect fixed on the way: `scripts/fetch_z80test.py` extracted the
release into a nested `z80test-1.2a/` directory, so the documented
`pytest tests/test_z80test_suite.py -m integration` reported three skips
rather than running. The script now flattens the archive and fails if the
programs are missing.

## One-step vector corpus

The complete `SingleStepTests/z80` corpus used for certification contains 1,604
opcode/prefix variants with 1,000 initial-to-final state transitions each:
**1,604,000 cases total**. It observes registers, flags, RAM effects, I/O
ordering, refresh register `R`, WZ/MEMPTR, Q, alternate registers, returned
T-state counts, and the memory bus transactions each instruction performs.

Every case also carries a `cycles` array with one `[address, data, pins]` entry
per T-state the oracle spent on the instruction. The vector gate reads it twice.
Its length is compared against the value `Z80CPU.step()` returns, so the T-state
claim below is checked by the same 1,604,000 cases as the state claim: taken
versus not-taken conditional branches, 21-versus-16 block repeats, and the 4
T-states every DD/FD prefix adds. Its entries are then compared against the
memory accesses the core actually performed — see
[Bus transactions](#bus-transactions) below. Earlier harness revisions compared
registers, RAM, and I/O only; T-states were then pinned by per-opcode unit tests
alone, and the `cycles` entries were read for their count and discarded.

The corpus is external, MIT-licensed, and deliberately not bundled. The pinned
source is:

- repository: https://github.com/SingleStepTests/z80
- revision: `ebe1875d48f374bcfd4b505d8eb8ee751568b5f7`
- license: MIT, Copyright (c) 2024 SingleStepTests

Fetch it, then execute the complete gate:

```text
python scripts/fetch_test_vectors.py
python -m pytest -q
```

Certified result under CPython 3.12.10 and PyPy 7.3.20 / Python 3.11.13:

```text
FILES: 1604 passed, 0 not implemented (skipped), 0 failed
TOTAL: 1604000 passed, 0 failed, 0 not implemented / 1604000 cases
```

## Bus transactions

Two claims are separated here, because the evidence supports one and not the
other.

**Checked against emulator-derived pin traces: which accesses happen, and in
what order.** No hardware-captured oracle observes bus order (see
[Oracle tiers](#oracle-tiers)); this claim is exactly as strong as
SingleStepTests' generator, cross-checked by FUSE's bus events. Each SingleStepTests
case's `cycles` array marks a memory read with the pin string `r-m-`, whose data
byte latches on the following entry, and a memory write with `-wm-`, which
carries its value inline. `VectorCPU` records every `read_byte`/`write_byte` the
instruction performs and `run_test_case` compares the two sequences exactly, on
kind, address, value and order:

```text
1,604,000 of 1,604,000 cases agree
```

Port strobes (`r--i` / `-w-i`) are excluded from that comparison because they
were already covered: `VectorCPU` feeds port reads from the vector's own `ports`
array in oracle order and refuses a read at an unexpected address, and verifies
every port write against the expected entry.

**Not claimed: which T-state each access occupies.** `step()` returns an
instruction total, so a host learns that `EX (SP),HL` took 19 T-states but not
that its two writes land at T13 and T16. Entries in `cycles` without a memory
strobe -- internal cycles, and the `I << 8 | R` refresh address the Z80 asserts
during M1 -- are skipped rather than modelled. This boundary is architectural,
not evidential: the `cycles` array carries the per-T-state data, and would
support the stronger claim whenever the core can emit at that granularity.

The distinction is not academic. Two write orderings that leave identical memory
are indistinguishable to every state-comparing oracle -- ZEXALL, z80test, and
this corpus's own register/RAM comparison all pass either one -- yet a host with
memory-mapped registers or contended-memory timing observes the difference.
`EX (SP),HL` and its `IX`/`IY` forms wrote the low byte first until commit
`2afb3f9`; the whole suite passed before and after that fix, and only the pin
traces could tell them apart.

## ZEX long-sequence certification

The separate `validation.zex` adapter supplies only the CP/M startup convention
and BDOS functions 0, 2, and 9 used by ZEX. It is not a CP/M implementation.
The GPL-2.0 ZEX binaries are external and intentionally not bundled.

| Program | SHA-256 | CPython 3.12.10 | PyPy 7.3.20 / Python 3.11.13 |
| --- | --- | ---: | ---: |
| `zexdoc.com` | `34923A7ED82285D3038B2D54BD64899E12173EEBB61F9D07B4FC72E78AF2AE8F` | 5,465.39s | 345.50s |
| `zexall.com` | `6E2DA55147A04F28D303D5DA6A1E6B771557AC244653590A0F24A2D39C8537E8` | 5,563.26s | 331.88s |

Both programs reported `Tests complete` with no `ERROR ****` report. The
post-refactor CPython combined run passed in 11,028.71 seconds; the PyPy run
passed in 677.50 seconds.

**Recertified at `695e47f` (2026-09-18)**, after the 0.4.0 speed ladder
changed the dispatch, the flag representation and the fetch path. PyPy
7.3.20 / Python 3.11.13, each program run alone on one pinned core of a
shared, loaded machine, through `validation.zex.ZexRunner` driven by
`step()`: ZEXDOC 67/67 tests `OK`, `Tests complete`, 5,764,169,474
instructions, 278.2 s; ZEXALL 67/67 `OK`, `Tests complete`, 5,764,169,474
instructions, 276.5 s. Same SHA-256 as above. CPython was not rerun; the
certification policy needs one interpreter per semantic change, and the
SingleStepTests, z80test and FUSE gates ran on CPython at every rung.

The 0.2.0 release candidate was recertified under PyPy 7.3.20 / Python 3.11.13
after the RESET, state, disassembly, and debugger additions. ZEXDOC passed in
470.43 seconds and ZEXALL passed in 426.77 seconds; the combined integration run
completed with 2 passed in 897.33 seconds. The debugger layers do not alter the
instruction execution path when unused.

To reproduce, download `zexdoc.com` and `zexall.com` from
https://github.com/agn453/ZEXALL into an external directory, verify the hashes,
then run:

```text
Z80_PYTHON_ZEX_DIR=<directory> python -m pytest tests/test_zex_integration.py -q --durations=2
```

On PowerShell, set `$env:Z80_PYTHON_ZEX_DIR` first. The tests use a finite
10,000,000,000-instruction budget. Run them for release candidates or changes
to instruction semantics, not ordinary documentation-only edits.

## Prefix runs: documentation-derived, stated as such

Runs of DD/FD prefixes (`DD DD 21 ..`, `FD DD ..`) and DD/FD before ED are
implemented from Sean Young's *The Undocumented Z80 Documented* v0.91
(sections 3.7 and 6.1, chapter 5), not from a hardware-captured corpus:
SingleStepTests has no file for them, z80test does not execute them, and
ZEXALL does not emit them. The one vector in any published test set is
FUSE's `ddfd00`, which is emulator-derived; `tests/test_prefix_sequences.py`
replays it and pins the rest of the rule, and
`examples/conformance/prefix-sequences.json` carries a reference trace for
ports. This claim is therefore a tier below the rest of this page, and says
so here rather than in the code.

## Hardware-oracle validation (z80test)

SingleStepTests is emulator-derived: its generator is, in its README's words,
"a semi-port from Ares". ZEXDOC and ZEXALL are hardware-captured but coarse:
each compares one CRC per instruction group with "an expected value that was
found empirically on a real Z80" (zexall.z80's header), so a failure names a
group, not a case, and WZ, Q, R, I/O and T-states never reach the CRC.

[raxoft/z80test](https://github.com/raxoft/z80test) is hardware-captured at a
finer grain, for the instructions and flags it covers: its expected values
were captured by executing on a real 48K ZX Spectrum with a genuine Zilog Z80. The
`validation.z80test_runner` adapter replaces the two ROM touchpoints the test
programs use for output (`RST 0x10` and `CHAN-OPEN`) with a 3-byte stub that
has no effect on tested CPU state; no ROM image is used or required. Fetch
the pinned, MIT-licensed release with `python scripts/fetch_z80test.py`, then
run `python -m pytest tests/test_z80test_suite.py -q`.

`z80full`, `z80memptr`, and `z80ccf` all report `Result: all tests passed.`
(`z80full` subsumes `z80doc`, `z80flags`, and `z80docflags`; `z80ccfscr` is a
visual demo, not a pass/fail check). `z80ccf` in particular checks SCF/CCF's
undocumented X/Y-flag behavior against the genuine NMOS Zilog convention --
the specific corner where NMOS, CMOS, and NEC-clone Z80s are all known to
disagree with each other.

The precise claim this adds: **instruction semantics and flags, including
the documented undocumented ones, are verified against real Zilog Z80
hardware for the covered instruction groups.** It does not extend to
interrupt sequencing or cycle/bus timing -- z80test verifies flags and
registers, not T-states, and none of its programs exercise interrupts.

## FUSE core tests (emulator-derived, six explained divergences)

FUSE, the Free Unix Spectrum Emulator, ships a Z80 core test set
(`z80/tests/tests.in` and `tests.expected`, GPL-2.0) of 1,356
single-instruction cases whose expected values come from FUSE's own core.
It is an emulator-derived oracle, a tier below the two above, and is run
because it holds a few sequences neither of them covers: `ddfd00`, a run of
prefixes, is one. `validation/fuse_runner.py` reproduces `coretest.c`'s
machine (RAM filled with `DE AD BE EF`, port reads returning the high byte
of the port address, whole instructions until the requested T-states have
elapsed) and compares registers, MEMPTR, I, R, IFF1, IFF2, IM, the halted
flag, the T-state total, and every listed memory byte. The bus events in
the expected file are not compared here: transaction order is certified
against SingleStepTests' pin traces instead, which is the same property
measured by a hardware-corrected oracle rather than an emulator-derived one.
FUSE is the weaker witness for it and adds nothing once the stronger gate
runs -- though it is what first surfaced the `EX (SP),rr` ordering defect,
which is the proper use of a tier-3 oracle: a detector, never a judge.

Fetch the pinned release with `python scripts/fetch_fuse_tests.py`
(`fuse-1.6.0.tar.gz`, SHA-256 `3a8fedf2…047096`), then run
`python -m pytest tests/test_fuse_suite.py -q`.

Result at commit `cab1598`: **1,350 of 1,356 agree**. The six that do not
are pinned as strict expected failures, each with the hardware-derived
source the core follows instead:

| Case | FUSE 1.6.0 expects | This core, and why |
| --- | --- | --- |
| `76` | PC stays on the HALT opcode while halted | PC past the opcode, as SingleStepTests `76.json` records |
| `edb2_1`, `edb3_1`, `edba_1`, `edbb_1` | interrupted INIR/OTIR/INDR/OTDR: MEMPTR = BC ± 1, pre-2021 flags | MEMPTR = PC + 1 and the corrected PV/H/X/Y, as SingleStepTests encodes and z80test 1.2a's `z80memptr` captured from silicon ("Fixed CRCs of interrupted INIR and INDR") |
| `edb9_2` | interrupted CPDR: X/Y not from PC | X/Y from the rewound PC's high byte, as SingleStepTests encodes |

The precise claim this adds is small: **one more independent core agrees on
1,350 single-instruction cases, and every disagreement is accounted for by a
higher-tier source.** It adds no hardware evidence.

## Independent-implementation cross-check (interrupt lifecycle)

No publicly known hardware-captured test corpus exists for interrupt
*sequencing* (IM 0/1/2 dispatch, NMI/INT priority, the EI-instruction delay,
HALT wakeup) the way SingleStepTests and z80test exist for instruction
semantics. `validation.interrupt_crosscheck` instead cross-checks against
[superzazu/z80](https://github.com/superzazu/z80), a separately written,
zexdoc/zexall-certified Z80 core, across ten deliberately adversarial
scenarios spanning all three interrupt modes, NMI/HALT interaction, RETN's
IFF1 restoration, the EI delay, DI-masking without losing a pending request,
and NMI-vs-maskable priority. Fetch and build the pinned oracle with
`python scripts/fetch_interrupt_oracle.py`, then run
`python -m pytest tests/test_interrupt_crosscheck.py -q`.

Nine of ten scenarios match exactly, including T-state totals. The tenth
(IM 0 with a device-supplied RST) is a known bug in the oracle, not this
core: superzazu double-charges the interrupt-acknowledge M1 cycle (see
`tests/test_interrupt_crosscheck.py` for the full diagnosis), where this
core's single-acknowledge-cycle accounting matches the documented model in
[interrupt-lifecycle.md](interrupt-lifecycle.md).

**This is cross-implementation triangulation, not a hardware oracle.** State
it as "cross-verified against an independent implementation," never as
"verified against hardware." The oracle also turns out to be structurally
unable to service an NMI during the EI-instruction delay window at all --
but that specific question has an independent answer: the Zilog manual
states the one-instruction delay only for the maskable interrupt, and real
ZX Spectrum hardware test ROMs (`EI48K`) confirm NMI ignores it. See the
"EI+NMI" section of [interrupt-lifecycle.md](interrupt-lifecycle.md) for the
one genuinely unconfirmed corner this surfaced: an opt-in, off-by-default
NMOS erratum sourced from gate-level simulation rather than a hardware
measurement.

## The sources every handler cites

Every opcode handler's docstring ends its headline with the source of its rule,
and `tests/test_readability.py` fails the build without one. The vocabulary:

| Citation | Source | Tier |
| --- | --- | --- |
| `UM0080 p. 278` | Zilog, *Z80 CPU User Manual*, UM008011-0816 (August 2016), printed page | documentation |
| `Young 3.4` | Sean Young, *The Undocumented Z80 Documented*, v0.91 (18 September 2005), section | documentation |
| `z80full`, `z80ccf`, `z80memptr` | raxoft z80test 1.2a programs, CRCs captured from real Zilog NMOS silicon | hardware-captured |
| `SST c3.json` | the SingleStepTests/z80 file for that opcode, at the pinned revision | emulator-derived |

Neither manual describes WZ (MEMPTR) or Q, so every handler that uses WZ,
itself or through a helper, carries a `WZ:` line naming the SingleStepTests
file that pins its rule, and the one handler that reads Q (`SCF`/`CCF`) a `Q:`
line; the readability test checks both. Where z80test exercises the
instruction, the line also names `z80memptr` (WZ, observed through a following
`BIT n,(HL)`) or `z80ccf` (Q), the hardware-captured evidence for the same
rule. z80test has no `RST` test, so `RST`'s WZ rule rests on SingleStepTests
alone.

The two manuals are not redistributed. `scripts/fetch_reference_docs.py`
downloads them into the gitignored `reference/` and checks these pins:

| Document | SHA-256 |
| --- | --- |
| `um0080.pdf` (1,587,333 bytes) | `e3c83da5a5d8e372364c20fa53665e6fbb165ec6ac38c8c1eebc359603447b5e` |
| `z80-documented.pdf` (276,007 bytes) | `6413048f39c2e735373b1fb23102599133bc64ccd0ed63b16fbc1173643d7a9d` |

Every page citation was checked against the page's own heading, and every
cited SingleStepTests file against the pinned corpus, when the citations were
written (2026-09-18).

**Where the core departs from a cited manual.** One rule, decided by a
higher-tier source:

- **`BIT b,r` X/Y.** Young 4.1 gives Y as "set if n = 5 and tested bit is set"
  and X likewise for n = 3, i.e. copied from the tested bit. The core copies
  bits 5 and 3 of the register itself, whatever b is. z80test's `z80full`
  (hardware-captured; its `BIT N,[R,(HL)]` test compares every flag) agrees
  with the core, as does SingleStepTests; Young's text is the outlier.


0.4.0 made the core faster one change at a time, each change a commit that
had to pass every oracle and to measure faster, or be reverted. Six rungs were
tried: the five the polish brief named (A-E) and one more (F) added when the
base workload still sat just under the 2.5 M instructions/s target. The table
gives each rung's speed as a ratio to the commit before it.

**Method.** The machine (i9-13900K, shared) carried a 20-core job from other
users throughout, and separate benchmark runs moved by +-30%, which buries a
5-10% change. Each ratio was therefore measured with
`benchmarks/compare_revisions.py`, which imports both revisions into one
interpreter and times the three workloads alternately on one pinned
performance core, best of N samples in CPU time. Interference only ever slows
a sample, so the best sample recovers the undisturbed rate, and both sides
see the same load. CPython 3.14.4, 30 rounds of 50,000 instructions; PyPy
7.3.20 / Python 3.11.13, 12 rounds of 3,000,000.

| Rung | Commit | CPython base | indexed_cb | block_io | PyPy base | indexed_cb | block_io |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Callable bus (decision 1, not a rung) | `764ddd8` | x1.01 | x1.07 | x1.06 | x0.68-0.86 | x1.12-1.17 | x0.83 |
| A: one 256-entry table per opcode page | `090fa0c` | x1.32 | x2.33 | x1.15 | x1.59 | x15.1 | x1.32 |
| B: F as one int, one expression per instruction | `88ea008` | x1.59 | x1.20 | x1.30 | x1.10 | x0.94 | x1.05 |
| C: register file through `getattr` | reverted | x0.93 | x0.91 | x1.01 | x0.93 | x1.00 | x1.07 |
| D: Q written in place, no `_update_q` call | `c48395c` | x1.11 | x1.02 | x1.03 | x1.05 | x1.12 | x0.95 |
| E: 26 IX/IY ALU and LD handlers become three | `a48341b` | x1.00 | x1.01 | x1.00 | -- | -- | -- |
| F: opcode fetch and dispatch inside `step()` | `695e47f` | x1.23 | x1.11 | x1.15 | x1.03 | x1.09 | x1.07 |

The callable bus is the one change that cost PyPy speed (two runs shown as a
range). The old hosts' `read_byte` was a class method the JIT could inline to
an array access; a callable held in an instance attribute is loaded and
called on every access. The contract was decided for the family's sake, not
for speed, and the ladder repaid the cost several times over. Among callable
hosts, a bytearray's own methods are the fast choice on PyPy: at `695e47f`
they ran the base workload at 71 M/s against 47 M/s for Python closures over
the same bytearray. Rung C was measured and reverted: a
same-process micro-benchmark of the benchmark's register mix also put the
existing if-chain first (27-33 ns per five reads against 34-38 ns). Rung E is
a readability rung; no workload uses the forms it touched.

**End to end**, pre-polish `main` against the end of the ladder, same method:

```text
python benchmarks/compare_revisions.py 651b7bf 695e47f
```

| Workload | CPython `651b7bf` | CPython `695e47f` | Change | PyPy `651b7bf` | PyPy `695e47f` | Change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| base | 1.078 M/s | 2.729 M/s | x2.53 | 34.1 M/s | 66.6 M/s | x1.95 |
| indexed_cb | 0.543 M/s | 1.418 M/s | x2.61 | 1.50 M/s | 33.0 M/s | x22.0 |
| block_io | 0.934 M/s | 1.926 M/s | x2.06 | 41.9 M/s | 46.5 M/s | x1.11 |

The absolute rates are best samples on a loaded machine and are lower bounds;
the ratios are the result. The polish brief quoted a "base" baseline of
586,045 instructions/s; that figure was the indexed_cb workload's, and the
base workload measured 1.1 M/s before the ladder began. PyPy's 22-fold gain on
indexed_cb comes from rung A: the old DD/FD decoder rebuilt two dictionaries
of bound methods on every prefixed instruction, which the JIT could not
compile away.

## Performance record (0.3.0 and earlier)

On Windows 11, PyPy 7.3.20 / Python 3.11.13 produced warmed median rates of
55.55M instructions/s for the base workload, 4.11M for indexed/CB, and 56.33M
for block I/O. These are workload-specific benchmark results, not a universal
performance guarantee. PyPy is an optional, measured interpreter; CPython and
PyPy are both supported by the current validation evidence.

The `9e15acc` certification re-measured on a shared 32-core Linux x86_64 host
(load average about 5 from other users, so absolute figures are not comparable
to the Windows row). To isolate the effect of the handler relocation and
docstring work in `ab6ef87`, the pre-change commit `d54cad1` and `9e15acc` were
benchmarked interleaved under the same PyPy, two rounds of seven repeats each,
best median reported:

| Workload | `d54cad1` inst/s | `9e15acc` inst/s | Change |
| --- | ---: | ---: | ---: |
| base | 39,070,880 | 42,555,942 | +8.9% |
| indexed_cb | 4,187,582 | 4,722,226 | +12.8% |
| block_io | 41,914,342 | 46,263,089 | +10.4% |

Under CPython 3.14.4 the same comparison was within 1% on all three workloads.
The dispatch shape was preserved by design; the PyPy gain most likely comes
from the removed `_op_prefix_ignored_basic` indirection on NOP, LD rr,nn,
EX AF,AF' and DJNZ, which the base workload exercises heavily.
