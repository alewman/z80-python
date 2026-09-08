# Conformance: proving another core is the same CPU

This page is for someone writing a Z80 core in another language who wants to
use `z80-python` as the reference. It says what "the same CPU" means here, how
to check it after every instruction, which oracles to run in what order, and
what you may claim after each. The tooling is `z80_python.conformance`; the
trace format is [trace-schema.md](trace-schema.md).

## What must match

At every processor boundary, all of:

- the boundary **kind** (instruction, halt idle, reset, NMI, maskable);
- the **T-state** total the boundary consumed;
- the instruction's **address and bytes**, when it is an instruction;
- all **28 fields of `CPUState`** before and after, including `wz`, `q`, `r`,
  `ei_delay`, both flip-flops, the halt flag, and the pending-request fields.

Nothing less. A core that matches registers but not `wz`, or matches state but
not T-states, is not equivalent for the purposes of this project, and the
tools here will say so at the first boundary where it fails.

## The manifest: one machine for both cores

Traces are only comparable when both cores ran the same machine. A manifest
pins that down:

```json
{
  "version": 1,
  "name": "flags-and-branches",
  "host": "flat",
  "port_read_value": 255,
  "memory": [{"address": 0, "data": "3e7f3c..."}],
  "initial": {"pc": 0, "sp": 65535},
  "events": [{"at_step": 2, "kind": "int", "vector": 255}],
  "stop": {"max_steps": 100, "on_halt": true, "at_pc": []}
}
```

| Key | Meaning |
| --- | --- |
| `memory` | Segments placed before the run. `data` is hex with no whitespace; or `file` (relative to the manifest) with optional `offset` and `length`. Everything else is zero. |
| `initial` | Any subset of the `CPUState` fields; the rest are zero or false. |
| `host` | `flat` or `cpm-minimal`, defined below. |
| `port_read_value` | What every `IN` returns under either profile. Port writes are discarded. |
| `events` | Lifecycle requests applied immediately *before* the boundary numbered `at_step` (records count from 0, every kind included). Kinds: `nmi`, `int` (with `vector`), `int_clear`, `reset`, `reset_clear`. Must be ordered by step. |
| `stop` | `max_steps` is mandatory. `on_halt` stops before a halt-idle boundary when nothing is pending and no event remains. `at_pc` stops before executing at any listed address. |

The **host** a port must implement to be comparable:

- **`flat`**: 64 KiB of RAM, reads return the byte, writes store it, `IN`
  returns `port_read_value`, `OUT` does nothing.
- **`cpm-minimal`**: `flat` plus two traps checked before every boundary, in
  this order, outside the CPU and producing no record. PC == 0x0000 ends the
  run. PC == 0x0005 performs BDOS function C: 0 ends the run; 2 appends E to
  the output; 9 appends bytes from DE until, not including, `$`; any other
  function is an error. It then reads the return address from SP (low byte
  first), adds 2 to SP, sets PC, and continues. This is exactly what
  `validation/zex.py` does, so ZEXDOC and ZEXALL run meaningfully on both
  sides.

The stop check order each boundary is: pending events, cpm traps, `at_pc`,
`on_halt`, then the step budget.

## Producing a trace from your core

Write one JSON Lines record per boundary as specified in
[trace-schema.md](trace-schema.md). Omit `mnemonic` and `operands`; give the
instruction's address and every byte it occupied, and the reader fills in the
text with this project's disassembler. Stream to a file or a pipe.

## Comparing

```text
python -m z80_python.conformance trace manifest.json --out reference.jsonl
python -m z80_python.conformance diff  manifest.json yours.jsonl
python -m z80_python.conformance checkpoints manifest.json --every N --dir segments/
```

`diff` runs the reference core in lockstep with your trace and stops at the
first differing field, printing the position, the instruction there, and every
differing path with both values. It reads lazily, so `yours.jsonl` can be a
pipe from a still-running core (`-` for stdin) and a multi-hour ZEX run stops
at the first bad instruction rather than the end. Exit status is 0 for
identical, 1 for a divergence, 2 for a malformed manifest or trace.

### Long runs: checkpoints and parallel segments

The reference side of `diff` builds, validates, and compares two complete
`CPUState` values per record on top of running the core, so it manages a
few thousand records per second on CPython and a few tens of thousands on
PyPy. ZEXALL is 5,764,169,474 records: a single pipe would take days.

```text
python -m z80_python.conformance checkpoints zexall.json --every 50000000 --dir segments/
```

runs the manifest with bare `step()` calls (minutes on PyPy for all of
ZEXALL) and writes a manifest at boundary 0, N, 2N, ... that resumes the
run from there: the full 64 KiB as a `file` segment beside it, every
`CPUState` field as `initial`, and `max_steps` of N. Diff every checkpoint
against your core's trace of it, as many in parallel as you have cores.
Each segment starts from the state the previous one ended in, so a
divergence anywhere is reported by the segment that holds it, and a clean
result on every segment is a clean result for the whole run. Manifests with
`events` are refused, since their `at_step` values would have to be shifted.
z80-rust's `scripts/rung3.sh` is a worked example.

`examples/conformance/` holds three manifests with their committed reference
traces: a straight-line flag and branch program, an interrupt scenario with a
maskable accept, RETI, an NMI, and RETN, and a program of DD/FD prefix runs.
`examples/conformance/interrupts/` holds the ten scenarios of
`validation/interrupt_crosscheck.py` as manifests with `events`, each with its
reference trace; they are rung 5 of the ladder below.

## Certification ladder

Run these in order. Each is cheaper than the next and each earns a specific
claim.

| Step | What | What you may then say |
| --- | --- | --- |
| 1 | All example manifests diff clean. | Your trace producer and host model are right. |
| 2 | SingleStepTests, all 1,604 files, comparing registers, RAM, port order, and T-states (`len(cycles)`). Native runner in your language; `validation/vector_utils.py` is the reference runner and the shape is documented in [start-here.md](start-here.md). | Instruction semantics, undocumented flags, WZ, Q, R, and timing match the corpus. |
| 3 | ZEXDOC and ZEXALL diffed against the reference with a `cpm-minimal` manifest. | Equivalent to `z80-python` over hundreds of millions of instructions. |
| 4 | raxoft/z80test natively (see `validation/z80test_runner.py` for the two ROM stubs). | Flags verified against real Zilog NMOS silicon. |
| 5 | The interrupt scenarios in `validation/interrupt_crosscheck.py` as manifests with events, shipped in `examples/conformance/interrupts/`. | Lifecycle sequencing equivalent to the reference. |

State the exact `z80-python` version, trace schema version, SingleStepTests
revision, and z80test release you certified against. A claim without those
four numbers is not reproducible.

## What this does not cover

Bus-level timing, memory contention, WAIT states, interrupt-acknowledge
callbacks, and daisy chains are outside the reference core's own claim and
therefore outside conformance. A port may model them; this kit will neither
check nor object.
