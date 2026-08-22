# Validation evidence and scope

## Claim

`z80-python` is a **SingleStep-complete, ZEXDOC/ZEXALL-certified pure-Python
Z80 instruction core**. The claim covers instruction-level semantic state and
long execution sequences. It does not claim cycle-accurate external bus
signaling, a complete Z80 machine, CP/M, interrupt acceptance/service,
EI-delay behavior, HALT wakeup, device scheduling, or memory contention.

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

To reproduce, download `zexdoc.com` and `zexall.com` from
https://github.com/agn453/ZEXALL into an external directory, verify the hashes,
then run:

```text
Z80_PYTHON_ZEX_DIR=<directory> python -m pytest tests/test_zex_integration.py -m integration -q --durations=2
```

On PowerShell, set `$env:Z80_PYTHON_ZEX_DIR` first. The tests use a finite
10,000,000,000-instruction budget. Run them for release candidates or changes
to instruction semantics, not ordinary documentation-only edits.

## Performance record

On Windows 11, PyPy 7.3.20 / Python 3.11.13 produced warmed median rates of
55.55M instructions/s for the base workload, 4.11M for indexed/CB, and 56.33M
for block I/O. These are workload-specific benchmark results, not a universal
performance guarantee. PyPy is an optional, measured interpreter; CPython and
PyPy are both supported by the current validation evidence.
