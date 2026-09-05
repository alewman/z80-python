# Validation evidence and scope

## Claim

`z80-python` is a **SingleStep-complete, ZEXDOC/ZEXALL-certified pure-Python
Z80 instruction core**. The claim covers instruction-level semantic state and
long execution sequences. It includes a deterministic instruction-boundary model for
RESET, maskable interrupt acceptance/service, NMI, EI delay, and HALT wakeup. It does
not claim cycle-accurate external bus signaling, a complete Z80 machine, CP/M, device
scheduling, or memory contention.

The specific lifecycle contract, mode coverage, and remaining exclusions are in
[interrupt-lifecycle.md](interrupt-lifecycle.md).

## One-step vector corpus

The complete `SingleStepTests/z80` corpus used for certification contains 1,604
opcode/prefix variants with 1,000 initial-to-final state transitions each:
**1,604,000 cases total**. It observes registers, flags, RAM effects, I/O
ordering, refresh register `R`, WZ/MEMPTR, Q, alternate registers, and returned
T-state counts. It is an instruction oracle, not a bus-pin trace.

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

The 0.2.0 release candidate was recertified under PyPy 7.3.20 / Python 3.11.13
after the RESET, state, disassembly, and debugger additions. ZEXDOC passed in
470.43 seconds and ZEXALL passed in 426.77 seconds; the combined integration run
completed with 2 passed in 897.33 seconds. The debugger layers do not alter the
instruction execution path when unused.

To reproduce, download `zexdoc.com` and `zexall.com` from
https://github.com/agn453/ZEXALL into an external directory, verify the hashes,
then run:

```text
Z80_PYTHON_ZEX_DIR=<directory> python -m pytest tests/test_zex_integration.py -m integration -q --durations=2
```

On PowerShell, set `$env:Z80_PYTHON_ZEX_DIR` first. The tests use a finite
10,000,000,000-instruction budget. Run them for release candidates or changes
to instruction semantics, not ordinary documentation-only edits.

## Hardware-oracle validation (z80test)

SingleStepTests and ZEXALL both validate against corpora ultimately derived
from other software (SingleStepTests from a corrected Ares core; ZEXALL by
construction checks internal CRC self-consistency, not an external
reference). Neither is a claim against real silicon.

[raxoft/z80test](https://github.com/raxoft/z80test) closes that gap for the
instructions and flags it covers: its expected values were captured by
executing on a real 48K ZX Spectrum with a genuine Zilog Z80. The
`validation.z80test_runner` adapter replaces the two ROM touchpoints the test
programs use for output (`RST 0x10` and `CHAN-OPEN`) with a 3-byte stub that
has no effect on tested CPU state; no ROM image is used or required. Fetch
the pinned, MIT-licensed release with `python scripts/fetch_z80test.py`, then
run `python -m pytest tests/test_z80test_suite.py -m integration -q`.

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
`python -m pytest tests/test_interrupt_crosscheck.py -m integration -q`.

Nine of ten scenarios match exactly, including T-state totals. The tenth
(IM 0 with a device-supplied RST) is a known bug in the oracle, not this
core: superzazu double-charges the interrupt-acknowledge M1 cycle (see
`tests/test_interrupt_crosscheck.py` for the full diagnosis), where this
core's single-acknowledge-cycle accounting matches the documented model in
[interrupt-lifecycle.md](interrupt-lifecycle.md).

**This is cross-implementation triangulation, not a hardware oracle.** State
it as "cross-verified against an independent implementation," never as
"verified against hardware." One corner is deliberately left unscored:
whether NMI can preempt the EI-instruction delay window. The oracle's
control flow structurally cannot service NMI during that window, while this
core's documented behavior has NMI ignore the EI delay entirely -- and there
is no hardware authority available to arbitrate which is correct.

## Performance record

On Windows 11, PyPy 7.3.20 / Python 3.11.13 produced warmed median rates of
55.55M instructions/s for the base workload, 4.11M for indexed/CB, and 56.33M
for block I/O. These are workload-specific benchmark results, not a universal
performance guarantee. PyPy is an optional, measured interpreter; CPython and
PyPy are both supported by the current validation evidence.
