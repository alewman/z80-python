# Changelog

All notable changes to `z80-python` are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries for 0.1.x through 0.3.0 were reconstructed from git history after the
fact; entries from 0.4.0 onward are written as the work lands.

## [Unreleased]

## [0.4.0] — 2026-09-18

The polish release: the family's reference core made faster, smaller to test,
cited line by line, and honest about the tier of every claim.

### Breaking

- **`Z80CPU` takes its bus as callables and is no longer an abstract base
  class.** The constructor is `Z80CPU(read_byte, write_byte, *,
  read_port=None, write_port=None)`, the embedding contract m6800-python
  already uses. The port callables default to an unconnected bus (`IN`
  reads 0xFF, `OUT` is discarded). A class that still defines the bus as
  methods raises a `TypeError` naming the new form when it is defined.
  Migration: instead of subclassing and defining `read_byte`, `write_byte`,
  `read_port` and `write_port`, pass them in, for example
  `Z80CPU(memory.__getitem__, memory.__setitem__)`. The core now promises
  16-bit addresses and 8-bit values, so hosts need no masking; the
  SingleStepTests host fails any case that breaks the promise. Under PyPy
  the callable bus costs 14-32% on the plain workloads against the old
  class methods (the JIT inlined those); the speed work below repays it.
- **CPython 3.11 is no longer tested.** CI runs CPython 3.12, 3.13 and 3.14
  and PyPy 3.11 (CI never ran PyPy before). `requires-python` stays
  `>=3.11` because PyPy's newest release is Python 3.11: the floor follows
  PyPy and rises when PyPy supports 3.12. Nothing uses syntax newer than
  3.11. Migration: none on PyPy; on CPython, use 3.12 or later.

### Changed

- **2.5x faster on CPython, 2x on PyPy (22x for IX/IY code).** An ablation
  ladder, one commit per change, every oracle green at each, each measured
  with `benchmarks/compare_revisions.py`: one 256-entry table per opcode page
  (A); F kept as one int and computed in one expression per instruction (B);
  Q written in place (D); the 26 near-identical IX/IY ALU and LD handlers
  folded into three (E); opcode fetch and dispatch inside `step()` (F). A
  register file read through `getattr` (C) measured slower and was reverted.
  Pre-polish `651b7bf` against `695e47f`: CPython 3.14 base 1.08 -> 2.73 M
  instr/s, indexed_cb 0.54 -> 1.42, block_io 0.93 -> 1.93; PyPy base 34 ->
  67, indexed_cb 1.5 -> 33, block_io 42 -> 47. `cpu.f` is now a `Flags`
  view over the CPU's F; `cpu.f.byte`, `cpu.f.c = 1` and `int(cpu.f)` work
  as before. Full table in docs/validation.md, "Speed".
- **The test suite is 30 files and 5,951 lines, from 178 and 15,252.** The
  191 hand-written single-instruction test files became nine family files
  of data rows, `Row(program, t_states, initial, changes)`, each checked in
  full by `conftest.check_step`: every register, every byte of memory, every
  port write and the T-states. The rows were recorded from the old tests and
  reproduce each of their 910 steps exactly. The 161 copies of `MemoryCPU`
  are one shared host in `tests/conftest.py`. `pytest -m "not slow"` is the
  quick loop.
- **Every claim names its oracle's tier.** docs/validation.md ranks the
  oracles (hardware-captured > hardware-corrected > emulator-derived >
  documentation) and README's Validation list names the tier in each
  bullet. Settling the tiers corrected two statements: ZEXDOC/ZEXALL are
  hardware-captured (their CRCs were "found empirically on a real Z80"), and
  SingleStepTests is emulator-derived, not hardware-corrected. The order of
  memory accesses has no hardware-captured oracle at all, so the bus claim
  is now "checked against emulator-derived pin traces", not "certified";
  which T-state each access occupies is not claimed.
- Certified at `b1720b6` on CPython 3.14 and PyPy 3.11: SingleStepTests,
  z80test, ZEXDOC/ZEXALL, FUSE and the interrupt cross-check, with commands
  and timings in docs/validation.md.
- CI enforces `ruff format --check` (ruff pinned) and runs the FUSE oracle
  on every push;
  a scheduled workflow runs the SingleStepTests, z80test and FUSE gates. See
  [CI coverage](README.md#ci-coverage).

### Added

- **Every opcode handler cites its source.** Each docstring headline ends
  with the page of Zilog's *Z80 CPU User Manual* UM008011-0816 or the section
  of Young's *Undocumented Z80 Documented* v0.91 its rule comes from, and every
  handler that uses WZ or reads Q names the SingleStepTests file (and, where
  z80test covers the instruction, `z80memptr` or `z80ccf`) that pins the rule
  neither manual describes. `tests/test_readability.py` enforces all three.
  `scripts/fetch_reference_docs.py` fetches both manuals and checks their
  SHA-256 pins. docs/validation.md lists the one rule where the core departs
  from a cited manual: Young 4.1's `BIT b,r` X/Y, contradicted by z80test's
  hardware-captured `z80full`.
- **Debugger parity with m6800-python.** `DebugSession(track_accesses=True)`
  records every bus access a step makes, memory and I/O, in
  `StepRecord.accesses`, by wrapping the CPU's bus callables; `close()`
  restores them. `add_watchpoint(address, "r" | "w" | "rw")` stops a run
  after the step that touched the byte (`StopReason.WATCHPOINT`,
  `RunResult.hits`). `next_boundary(state)` is public. The console gains
  `over`, `continue`, `watch`/`unwatch`, `set`, `int`/`nmi`/`reset` and the
  one-letter aliases; numbers stay decimal (`$1234` is new hex shorthand).
  `python -m z80_python --load FILE@ADDR --pc ADDR -c ...` steps a binary
  without a host. The trace schema gains an optional `accesses` array and
  stays version 1.
- **Memory bus transaction check (emulator-derived tier).** `VectorCPU`
  records every `read_byte`/`write_byte` an instruction performs, and
  `run_test_case` compares that sequence against the pin strobes in each
  SingleStepTests case's `cycles` array: `r-m-` for a read, whose data byte
  latches on the following entry, and `-wm-` for a write, which carries its
  value inline. **1,604,000 of 1,604,000 cases agree.** Port strobes are
  excluded because `VectorCPU` already feeds port reads from the vector's
  `ports` array in oracle order and verifies every write.
  `expected_memory_transactions()` and a keyword-only `verify_memory_bus`
  argument to `run_test_case()` serve callers whose `step` is a stub.
- FUSE 1.6.0's Z80 core test set as a fourth oracle: 1,356 single-instruction
  cases, 1,350 agreeing, with the six divergences pinned as strict expected
  failures, each naming the higher-tier source the core follows instead.
- Conformance kit: manifests, one shared host, reference traces, and a
  lockstep diff, with checkpointing so a multi-hour ZEXALL run can be split
  into segments; `examples/conformance/zex/` has the ZEXDOC/ZEXALL manifests,
  the recipe, and the SHA-256 of every checkpoint, so a port can diff the
  segments in parallel and know its checkpoints are the reference's.
- Runs of DD/FD prefixes, and DD/FD before ED, now execute as they do on
  hardware (Young 3.7).
- `benchmarks/compare_revisions.py`, the same-process A/B the speed ladder
  was measured with.
- `.github/workflows/publish.yml`: PyPI Trusted Publishing on a release
  tag, with a `workflow_dispatch` dry run that builds, smoke-tests and runs
  `twine check` without uploading. `scripts/smoke_installed_package.py` is
  the smoke test CI and the publish workflow share.

### Fixed

- **`EX (SP),HL` and `EX (SP),IX/IY` wrote the low byte to `(SP)` before the
  high byte to `(SP+1)`.** SingleStepTests' pin traces and FUSE's bus
  events, both emulator-derived, put the `(SP+1)` write first; no
  hardware-captured oracle observes bus order, and UM0080 p. 127 gives the
  M-cycles but not their addresses. The resulting memory is identical either
  way, so no state-comparing oracle could see it: ZEXALL, z80test, and this
  corpus's own register/RAM comparison all passed both orderings. Caught by
  FUSE, adjudicated against SingleStepTests, and now gated by the transaction
  check above. Bus transaction sequence: 1,601,000 -> 1,604,000 of 1,604,000.

### Not done in this release

- IM 0 still accepts only a device-supplied `RST`. The general form (a
  device supplying `CALL nn` or any instruction) was scoped and left out:
  neither Zilog's manual nor Young gives its timing beyond `RST`, no
  executable oracle checks it, and it would need a new `CPUState` field
  type and a trace-schema change.
- The console reads plain numbers as decimal, m6800-python's as hex. Kept
  to avoid a third public break; `$1234` works in both.

## [0.3.0] — 2026-08-23

### Added

- Versioned streaming trace persistence, and a documented trace schema as a
  public contract that external producers may omit disassembly text from.
- Incremental trace divergence analysis and bounded live-session divergence
  search.

### Changed

- Hardened the public debugger contracts.
- README refocused on the reference-core identity.

## [0.2.0] — 2026-08-23

### Added

- Complete CPU state capture and restore (`capture_state` / `restore_state`).
- Structured, side-effect-free disassembly.
- Bounded structured debug sessions and a portable command debugger.
- Host-controlled reset lifecycle.

### Changed

- ZEX recertification recorded for the 0.2.0 core.

## [0.1.3] — 2026-08-21

### Fixed

- PyPI packaging metadata and pre-release installation instructions.

## [0.1.2] — 2026-08-21

### Fixed

- Distribution metadata corrections.

## [0.1.1] — 2026-08-21

### Fixed

- First PyPI release metadata.

## [0.1.0] — 2026-08-21

### Added

- Initial standalone extraction of the `z80-python` instruction core, with CI.

[Unreleased]: https://github.com/alewman/z80-python/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/alewman/z80-python/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/alewman/z80-python/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/alewman/z80-python/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/alewman/z80-python/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/alewman/z80-python/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/alewman/z80-python/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/alewman/z80-python/releases/tag/v0.1.0
