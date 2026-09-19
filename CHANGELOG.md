# Changelog

All notable changes to `z80-python` are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries for 0.1.x through 0.3.0 were reconstructed from git history after the
fact; entries from 0.4.0 onward are written as the work lands.

## [Unreleased] — 0.4.0.dev0

### Added

- **Memory bus transaction certification.** `VectorCPU` records every
  `read_byte`/`write_byte` an instruction performs, and `run_test_case`
  compares that sequence against the pin strobes in each SingleStepTests
  case's `cycles` array — `r-m-` for a read, whose data byte latches on the
  following entry, and `-wm-` for a write, which carries its value inline.
  **1,604,000 of 1,604,000 cases agree.** Port strobes are excluded because
  `VectorCPU` already feeds port reads from the vector's `ports` array in
  oracle order and verifies every write.
- `expected_memory_transactions()` and a keyword-only `verify_memory_bus`
  argument to `run_test_case()`, for callers that replace
  `decode_and_execute` with a stub performing no memory access.
- FUSE 1.6.0's Z80 core test set as a fourth oracle: 1,356 single-instruction
  cases, 1,350 agreeing, with the six divergences pinned as strict expected
  failures, each naming the hardware-derived source the core follows instead.
- Conformance kit: manifests, one shared host, reference traces, and a
  lockstep diff, with checkpointing so a multi-hour ZEXALL run can be split
  into segments.
- Runs of DD/FD prefixes, and DD/FD before ED, now execute as they do on
  hardware.

### Fixed

- **`EX (SP),HL` and `EX (SP),IX/IY` wrote the low byte to `(SP)` before the
  high byte to `(SP+1)`.** Hardware writes `(SP+1)` first. The resulting
  memory is identical either way, so no state-comparing oracle could see it:
  ZEXALL, z80test, and this corpus's own register/RAM comparison all passed
  both orderings. Caught by FUSE's bus events, adjudicated against
  SingleStepTests' pin traces, and now gated by the transaction check above.
  Bus transaction sequence: 1,601,000 → 1,604,000 of 1,604,000.

### Changed

- **The bus claim is stated in two parts instead of one.** Which memory
  accesses happen — kind, address, value, and order — is certified. Which
  T-state each access occupies, the internal cycles, and the `I << 8 | R`
  refresh address asserted during M1 are not claimed, and the boundary is
  architectural rather than evidential: `cycles` carries the per-T-state data
  and would support the stronger claim whenever `step()` can emit at that
  granularity. Previously a single sentence disclaimed both, which understated
  what the core does correctly.
- CI now runs the FUSE oracle on every push, and a separate scheduled workflow
  runs the SingleStepTests, z80test, and FUSE gates against their pinned
  corpora. See [CI coverage](README.md#ci-coverage) for what each badge means.

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

[Unreleased]: https://github.com/alewman/z80-python/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/alewman/z80-python/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/alewman/z80-python/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/alewman/z80-python/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/alewman/z80-python/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/alewman/z80-python/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/alewman/z80-python/releases/tag/v0.1.0
