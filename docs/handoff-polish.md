# Handoff: polish `z80-python`, the flagship reference core

Written 2026-09-18 after a full read of the core, the tooling, the docs and
the test suite, with the suite run, the hot path profiled and the flag
representation micro-benchmarked. z80-python is the reference every other
core in this family (m6800-python, and the six briefs in `/data/emu/*-python`)
copies from, so the goal is not "good enough" but "the shape the others
should inherit". Do the items in order. Items 1-7 are the job; 8-9 are
stretch goals, only after 1-7 are green.

## The bar

Aubrey's word for the target is **defensible**: z80-python is the pinnacle
core of the family, the one every other pure-Python core will be measured
against, and it should represent the best a human-and-AI pair can do. Read
every item below against that bar, which means:

- every claim names its oracle and the oracle's tier in the sentence that
  makes it, and a reader can rerun the command that produced it;
- every handler says where its rule comes from, so a disagreement can be
  settled by opening the cited page, not by trusting the code;
- every deliberate divergence from an oracle is listed with the
  higher-tier source that decided it, and there are no undocumented ones;
- every number in the docs (tests, cases, speed, timings) is current and
  regenerated, not remembered;
- nothing is kept that does not pay: a rung, a test file, a page or a
  marker that does not move a number or settle a question is removed.

When an item as written falls short of that bar, do the better thing and say
so in the commit message; when meeting the bar would exceed the item's
scope, finish the item and record the gap in `CHANGELOG.md` under
`[Unreleased]` so it is not lost.

## Context you are inheriting

- Repository: `/data/emu/z80-python`, public as `alewman/z80-python`, HEAD
  `7c2fa30`, clean tree, version `0.4.0.dev0` (README still calls 0.3.0 the
  current release; 0.4.0 has been "in development" since 2026-09-06 and
  carries the conformance kit, FUSE and the bus-transaction certification).
- Venvs: `.venv` (CPython 3.14.4), `.venv-pypy` (PyPy 3.11); ruff at
  `~/.local/bin/ruff`. Oracles fetched locally and gitignored:
  `tests/z80_test_vectors/` (SingleStepTests, pinned), `validation/z80test_data/`,
  `validation/interrupt_oracle_src/`, ZEX binaries in `tests/zex/`
  (`Z80_PYTHON_ZEX_DIR=/data/emu/z80-python/tests/zex`).
- Baseline, verified 2026-09-18 on CPython 3.14 with the SST corpus present:
  `pytest -q --deselect tests/test_z80test_suite.py` → **6,119 passed, 2
  skipped, 7 xfailed in 77 s** (the 1,604 SST files are in that count).
  `ruff check .` clean. **`ruff format --check .` reports 18 files that would
  be reformatted**; CI does not run it.
- Speed baseline (`benchmarks/z80_core_benchmark.py --instructions 200000
  --repeats 3`, CPython 3.14): `base` 586,045 instr/s, `block_io` 1,071,006.
  For scale, m6800-python runs 3.1 M instr/s on the same interpreter with the
  same mixin architecture; the Z80 is a harder CPU but not five times harder.
- Sister project to copy shapes *from* where it is ahead:
  `/data/emu/m6800-python` (its `_dispatch.py` table build, `_core.py` packed
  CC int, `debug.py` watchpoints and access tracking, `__main__.py` CLI,
  `tests/test_readability.py` citation rule, `docs/validation.md` oracle-tier
  table, `tests/conftest.py` shared logging bus).
- Read first: `README.md`, `docs/start-here.md`, `docs/validation.md`,
  `docs/api-stability.md`, `docs/conformance.md`, then every file under
  `src/z80_python/`. The whole core is 4,884 lines; read it all before
  changing any of it.

## Two decisions Aubrey has made (2026-09-18; the second amended the same day)

Both are deliberate breaks. Nobody outside this family uses the package yet,
so 0.4.0 takes them now rather than carrying compatibility shims into six
more cores. Record both in `CHANGELOG.md` under a **Breaking** heading with
the one-line migration each needs, and amend `docs/api-stability.md` to say
that pre-1.0 minor releases may break the public surface when the changelog
says so.

1. **The family embedding contract is callables.** `Z80CPU` stops being an
   abstract base class. Its constructor becomes
   `Z80CPU(read_byte, write_byte, *, read_port=None, write_port=None)`,
   the m6800-python shape: the two memory callables are required; the port
   callables default to a documented floating bus (`read_port` returns
   `0xFF`, `write_port` discards) so a flat host needs only two arguments.
   The four `@abstractmethod`s are deleted; a host that still subclasses and
   defines the methods gets a clear `TypeError` from the constructor naming
   the new form. Update every host in the tree: `examples/minimal_z80_host.py`,
   `benchmarks/z80_core_benchmark.py`, `conformance.ConformanceHost`,
   `validation/vector_utils.py` (`VectorCPU`), `fuse_runner.py`,
   `z80test_runner.py`, `zex.py`, `interrupt_crosscheck.py`, the CI smoke
   test in `ci.yml`, the 151 test-file `MemoryCPU`s (item 3 replaces them
   with one), and the README, `start-here.md`, `interrupt-lifecycle.md`,
   `conformance.md` and `api-stability.md` prose. m6800-python's README
   claim of "the same embedding contract" becomes true; say so in both.
2. **CPython 3.11 leaves the tested matrix; PyPy sets the floor.**
   *Amended 2026-09-18 (Aubrey: "We need to support PyPy").* As first
   written this item asked for `requires-python = ">=3.12"` and 3.12
   syntax, but no PyPy supports 3.12 yet (the newest, 7.3.23, is Python
   3.11.15), so that floor would make pip refuse PyPy and the syntax
   would not run on it. Instead: `requires-python` stays `>=3.11` with a
   comment naming PyPy as the reason, ruff stays `py311`, no syntax newer
   than 3.11, classifiers 3.12/3.13/3.14 plus PyPy, CI matrix `3.12`,
   `3.13`, `3.14`, `pypy3.11`. Raise the floor when PyPy supports 3.12.

## Constraints

- **Every oracle must pass unchanged after every item** that touches
  `src/`: SST (`pytest tests/test_z80.py`), z80test
  (`tests/test_z80test_suite.py`), FUSE, the interrupt cross-check, the
  conformance fixtures, and the readability test. ZEXDOC/ZEXALL once, at the
  end of item 2 (semantic-core layout change), on PyPy (~6 min each) and
  recorded in `docs/validation.md` with the hash they certify.
- The readability contract stays: `grep DJNZ src/` lands on the handler.
  Tables may *route* to handlers; they must not *replace* them with lambdas
  or generated code.
- No runtime dependencies. PyPy must stay green.
- Public API: the two decided breaks (callable contract, 3.12 floor) are
  the only ones. `Flags`, `cpu.f`, `CPUState`, the debugger values, the
  trace and conformance surfaces keep working; everything else is additive.
- One commit per item, authored as alewman, with the Co-Authored-By line the
  session gives you. **Pushing and merging are authorised (Aubrey,
  2026-09-18); tagging and publishing are not.** Work on a branch
  `polish-0.4.0`, push it, open one PR, wait for CI and the Oracles workflow
  (`gh workflow run oracles.yml` on the branch) to go green, merge, and stop
  there. The `v0.4.0` tag, the GitHub release and the PyPI upload happen
  after Aubrey's reviewer has read the merged result; item 7 prepares them.
  The repository is public.
- Never commit vectors, ZEX binaries, z80test data, ROMs.

## Item 1 — enforce formatting, fix the small things (an hour)

- Run `ruff format .` (18 files), add `ruff format --check .` to
  `.github/workflows/ci.yml` and `CONTRIBUTING.md`.
- `_loads.py`: `LD A,I` and `LD A,R` docstrings each say "the only load that
  sets flags". There are two. Fix both.
- `_alu.py` `_op_alu_n`: the dict literal rebuilt on every call is
  `(opcode >> 3) & 0x07`. Replace it.
- Sign extension of a displacement byte is written out six times
  (`_op_jr`, `_op_djnz`, `_index_displacement_addr`, `_op_index_bit`,
  `_op_index_rot`, `_op_index_res_set`). One `_signed8()` helper in
  `_core.py`.
- `tests/test_smoke.py` asserts `1 + 1 == 2`; delete it. `pyproject.toml`
  declares `unit` and `integration` markers nothing uses; remove them or use
  them.
- `docs/undocumented-behavior.md` is a nine-line redirect to
  `z80-undocumented-behavior.md`; merge into one page, fix the links.
- README "Version status" says the current release is 0.3.0 while the tree is
  0.4.0.dev0 with a written `docs/releases/0.4.0.md`; item 7 ships 0.4.0, so
  leave the table but make it say 0.4.0 is in progress and link the release
  note.

## Item 2 — the speed ablation ladder (two to three days; the big one)

The core is structured for readability and pays for it in four places the
profile and a micro-benchmark identify. Do these as an **ablation ladder**:
one commit per rung, the benchmark run before and after on CPython and PyPy
with the numbers in the commit message, every oracle green at every rung,
and a rung that does not pay is reverted, not kept. Record the ladder in
`docs/validation.md` ("Speed") and `CHANGELOG.md`. Target: `base` workload at
or above 2.5 M instr/s on CPython 3.14 with oracles unchanged; stop early if
a rung does not move the number.

**Rung A — table dispatch.** `_dispatch.py:_execute_main` is a chain of about
fifty `if opcode in (...)` tests; `_execute_index_opcode` is seventy more and
**rebuilds two dicts of 24 bound methods and a 40-element set on every
prefixed instruction**; `_execute_ed` mixes `match` with if-chains. Together
`step`, `decode_and_execute` and `_execute_main` are about 30 % of the
profile's own time on the `base` workload. Replace each decoder with a
256-entry table built once per class (main, CB, ED, DD/FD, DDCB) whose
entries are `(unbound handler, argument)` so the handler methods and their
docstrings are untouched and the readability test still finds every
mnemonic. m6800-python's `_dispatch.py:build_table` is the shape: the table
is data, the handlers are code. Keep the DD/FD stray-prefix loop and the
DD-then-ED rule from `_index_dispatch.py`'s docstring exactly as they are,
with their FUSE `ddfd00` and `tests/test_prefix_sequences.py` gates.

**Rung B — flags as a packed int.** `Flags` is an object with a `_byte` slot
behind eight properties; the ALU sets them one at a time (`_add` makes nine
property calls). Measured 2026-09-18: an ADD's flag update costs **4.4×**
through the properties versus one packed-int expression. Change the core to
keep `self._f` as an int and compute each instruction's flags as one
expression (the m6800 `_add8` is the model; the SST corpus is the judge for
every X/Y/H/PV rule, so this is safe to do mechanically). Keep the public
API: `cpu.f` becomes a property returning a `Flags` **view** bound to the
CPU that reads and writes `_f` through (so `cpu.f.byte`, `cpu.f.c = 1` and
`int(cpu.f)` keep working, and `Flags(value)` standalone keeps working);
`CPUState.f` is already an int. Update `docs/start-here.md`'s register
table, which documents `cpu.f` as the object.

**Rung C — register file.** `_read_reg`/`_write_reg` are if-chains keyed by
the 3-bit field. Options to measure: a tuple of attribute names plus
`getattr`/`setattr`; or, at table-build time, binding the register name into
the table entry so the handler receives it. Keep whichever pays; the
handler bodies stay readable either way.

**Rung D — `_update_q` per instruction.** It is a method call on every
instruction. Measure inlining it as an attribute write in the handlers that
write flags (`self.q = self._f`) and in `step()` for the rest. Keep only if
it pays.

**Rung E — the 32 index ALU handlers.** `_index.py` has sixteen
`_op_<alu>_a_index_{h,l}` and eight `_op_<alu>_a_index_mem` methods that are
the same three lines with a different group number. Collapse them to
`_op_alu_index_byte(prefix, sub_opcode)` and `_op_alu_index_mem(prefix,
sub_opcode)`, decoding the group from the opcode as `_op_alu_r` already does;
the readability test accepts `ADD/ADC/SUB/SBC/AND/XOR/OR/CP A,IXH/IXL` as a
headline. This rung is for readability, not speed; measure anyway.

## Item 3 — consolidate the test suite (a day)

Facts from the survey (2026-09-18): 178 test files, 18,553 lines, 473 test
functions. **139 are per-opcode files; 117 of them are near-exact copies of
one template** (`tests/test_dd_71_ld_ix_plus_2_c.py`: a local `MemoryCPU`
subclass, a local `_run` helper, one test with eight asserts). **151 files
carry a byte-identical `MemoryCPU`; 128 carry an identical `_run`.** Every
opcode those files pin is covered exhaustively by the SST corpus, including
WZ, Q and T-states, which is what they assert. They were red-first witnesses
during the build and have done their job.

- Add one shared `MemoryCPU` (flat RAM, logging bus, deterministic ports)
  and a `run(cpu, bytes) -> t_states` helper to `tests/conftest.py`; delete
  the 151 local copies.
- Fold the 139 per-opcode files into one parametrized file per instruction
  family (`test_index_loads.py`, `test_index_alu.py`, `test_index_prefixed_base.py`,
  `test_ddcb_fdcb.py`, …), each row a tuple `(bytes, initial, expected,
  t_states)` taken from the file it replaces, so **no assertion is lost**,
  only its boilerplate. Prove it: count assertions before and after with a
  script and put the two numbers in the commit message.
- Keep every non-per-opcode file (the survey lists 39: lifecycle, debugger,
  disasm, trace, conformance, oracles, readability, public API, benchmark).
- `tests/test_z80.py` carries an inline fallback copy of `validation/vector_utils.py`
  for when the import fails; delete the fallback, the import cannot fail
  inside this repository.
- Target: under 6,000 test lines, the same 6,119 passing results (fewer
  functions, same or more assertions), fast suite still under 90 s with the
  corpus present.

## Item 4 — cite the source in every handler (a day)

m6800-python's readability test requires each handler docstring to read
`MNEMONIC operands -- description (MANUAL p. N)`. z80-python's requires only
the mnemonic, and many handlers are bare (`"""INC r"""`, `"""RST p"""`,
`"""JP (HL)"""`). For the flagship reference, every handler should say
where its rule comes from. Sources, in tier order, all already cited
somewhere in the docs: Zilog *Z80 CPU User Manual* UM008011 (page per
instruction), Sean Young *The Undocumented Z80 Documented* v0.91 (section
per undocumented rule), and for the X/Y, WZ and Q rules the SST corpus file
that pins them. Extend `tests/test_readability.py` to require a citation in
parentheses on the headline and fail the build without one. Fetch and pin
UM0080's SHA-256 in `docs/validation.md` the way m6800 pins its manuals
(`scripts/fetch_reference_docs.py` there is the shape); do not commit the PDF.

## Item 5 — tier the claims where they are made (half a day)

`docs/validation.md` (line 170) says plainly that SingleStepTests is derived
from a corrected Ares core and ZEXALL checks self-consistency, and that only
z80test is captured from real silicon. README's headline still says
"SingleStep-complete and ZEX-certified", and the 0.4.0 note says memory
transactions are certified "against the pin strobes" of SST cases, which are
emulator-derived pin strobes. Nothing is false; the tier is a page away from
the claim. Add an oracle-tier table to `docs/validation.md` in the m6800
shape (hardware-captured > hardware-corrected > emulator-derived >
documentation), one row per oracle with what it covers, and rewrite the
README "Validation" list so each bullet names its tier in the same
sentence. Say in one line that bus-transaction *order* has no hardware
oracle at all.

## Item 6 — tooling parity with m6800-python (a day)

m6800-python's debugger grew past z80-python's. Back-port:

- `DebugSession(track_accesses=True)`: record every `read_byte`/`write_byte`
  (and here `read_port`/`write_port`) per step as `StepRecord.accesses`,
  optional, `None` when off; `watch(address, "r"|"w"|"rw")` with
  `StopReason.WATCHPOINT` and `RunResult.hits`. The m6800 `debug.py` has
  the implementation; it wraps the bus callables, which is why decision 1
  above matters.
- `next_boundary(state)` as a public function (z80 has it private as
  `_boundary_kind`).
- `python -m z80_python --load FILE@ADDR --pc ADDR -c "break 1234" -c "run
  1000"`, the m6800 `__main__.py` shape, so a ROM can be stepped without
  writing a host.
- `trace-schema.md` gains the optional `accesses` array (schema version
  stays 1 if absent-means-off; say so).
- `console.py`: add `watch`/`unwatch`/`over` if missing, matching the m6800
  command set so the two debuggers read the same.

## Item 7 — prepare the 0.4.0 release, stop before the tag (half a day)

- `CHANGELOG.md`: move `[Unreleased]` to `[0.4.0] — <date>`, listing items
  1-6 with the speed ladder's before/after numbers, and a **Breaking**
  section for the callable contract and the 3.12 floor with their migrations.
- `docs/releases/0.4.0.md` updated to match; README version table; API
  stability page lists the new debugger surface and the callable contract.
- CI matrix 3.12/3.13/3.14/pypy-3.11; `ruff format --check` in CI (item 1).
- `docs/validation.md`: recertify. Record the SST, z80test, FUSE, cross-check
  and ZEX runs against the final hash, with commands and timings, exactly as
  the page does for 0.3.0.
- **Publish workflow, not the publish.** There is no PyPI workflow in the
  tree and no `~/.pypirc`; 0.3.0 was uploaded by hand. Add
  `.github/workflows/publish.yml`: on a pushed `v*` tag (excluding `-rc`
  tags), build sdist and wheel, run the installed-API smoke test, then upload
  with `pypa/gh-action-pypi-publish` using **Trusted Publishing** (OIDC, no
  stored token). Trusted Publishing needs a one-time registration on
  pypi.org (project `z80-python` → Publishing → add publisher: owner
  `alewman`, repository `z80-python`, workflow `publish.yml`, environment
  `pypi`). **Aubrey registered it on 2026-09-18.** Prove the workflow
  without a tag: give it `workflow_dispatch` as a second trigger with a
  `dry_run` input that builds, smoke-tests and runs `twine check` but skips
  the upload step, and run that once on the branch so the PR shows it green.
- **Stop before the tag.** Do not run `git tag`, `gh release create`, or any
  upload. The merged main is the deliverable. Note that `v0.4.0-rc1` already
  names the pre-polish state (dadff4d); leave it alone. In the final report,
  give Aubrey the exact commands to run after review, filled in with the
  merged hash:
  `git tag -a v0.4.0 <hash> -m "..."; git push origin v0.4.0;
  gh release create v0.4.0 --notes-file docs/releases/0.4.0.md`,
  and what to check afterwards: the publish job green, then
  `pip install z80-python==0.4.0` in a fresh venv plus the smoke test,
  whose result goes into the release note as a follow-up commit.

## Stretch 8 — IM 0 beyond RST

`_accept_maskable_interrupt` raises `NotImplementedError` for an IM 0 vector
that is not an RST opcode. Real IM 0 devices also supply `CALL nn` (three
bytes) and, in principle, any instruction. Implement the general form: the
request carries a byte sequence, the accept path executes that instruction
with its fetches redirected to the sequence, T-states are the instruction's
plus the two acknowledge wait states, R increments once for the acknowledge
M1. There is no hardware oracle; the superzazu cross-check is the detector
and already has one xfail for its own IM 0 bug. Keep the RST fast path.

## Stretch 9 — a `flat` conformance run of ZEXALL, checkpointed, as a shipped fixture

`docs/conformance.md` describes checkpointing so a multi-hour ZEXALL run can
be diffed in segments, and z80-rust used it. Ship the checkpoint manifests
(not the traces) under `examples/conformance/zexall/` with the command that
regenerates each segment's reference trace on PyPy, so a port author can
certify against ZEXALL in parallel without rediscovering the recipe.

## Known gotchas

- With the SST corpus present the "fast" suite includes it (77 s); deselect
  `tests/test_z80.py` for a quick loop. `test_z80test_suite.py` takes ~7 min
  on CPython; run it on PyPy.
- ZEX takes ~1.5 h per program on CPython and ~6 min on PyPy; the
  certification policy is in `docs/validation.md`.
- The FUSE suite has six strict xfails and the cross-check one dynamic
  xfail, each naming the hardware-derived source the core follows instead;
  do not "fix" them.
- `tests/test_readability.py` parses the source with `ast`; a table of
  handler names is fine, a handler defined twice across the mixins is caught
  (the MRO would shadow it silently).
- `_index_dispatch.py`'s docstring is the specification for prefix runs;
  keep it with the table that replaces the code.

## What done looks like

- Items 1-7 landed as one commit each; every oracle green after each;
  ZEX recorded once at the end; ruff check and format clean; CPython and
  PyPy green.
- `benchmarks/` numbers before and after in `docs/validation.md`, with the
  rungs that did not pay listed as reverted.
- Test suite under 6,000 lines with assertion counts proven equal or higher.
- Every handler docstring cites its source and the readability test
  enforces it.
- README claims name their oracle tier in the sentence that makes them.
- The debugger, CLI and trace schema match m6800-python's, so the next core
  can copy either.
- The `polish-0.4.0` PR merged to main with CI and Oracles green, the
  publish workflow proven by a dry run, and **no tag pushed**. The final
  report ends with the tag, release and verification commands for Aubrey to
  run once the reviewer has read the merged result.
