# z80-python

[![CI](https://github.com/alewman/z80-python/actions/workflows/ci.yml/badge.svg)](https://github.com/alewman/z80-python/actions/workflows/ci.yml)
[![Oracles](https://github.com/alewman/z80-python/actions/workflows/oracles.yml/badge.svg)](https://github.com/alewman/z80-python/actions/workflows/oracles.yml)

A readable, pure-Python Z80 **instruction-core reference implementation**.

`z80-python` is a SingleStep-complete and ZEX-certified processor core built to
be read, learned from, embedded in real machines, and inspected by humans and AI
tools. It implements the Z80 instruction set and deterministic processor
lifecycle at instruction boundaries while leaving memory maps, devices, and
machine scheduling to the host.

The project is deliberately:

- **readable** — instruction families are organized as ordinary Python rather
  than generated tables, native extensions, or opaque optimizations;
- **pure Python** — the core has no runtime dependencies and supports CPython and
  PyPy;
- **independently validated** — correctness claims come from external test
  oracles, not from code-generation confidence;
- **embeddable** — a host supplies four memory and I/O methods and controls when
  the processor advances; and
- **inspectable** — processor state, disassembly, bounded debugging, and
  structured traces make execution explainable without contaminating the hot
  core path.

## Validation

The instruction core has passed:

- all **1,604** opcode/prefix files in the pinned `SingleStepTests/z80`
  corpus—**1,604,000 state transitions** covering registers, flags, memory,
  I/O ordering, T-states, alternate registers, `R`, WZ/MEMPTR, Q, and
  undocumented behavior; and
- **ZEXDOC** and **ZEXALL** long-sequence CRC exercisers under both CPython and
  PyPy; and
- three of raxoft/z80test's hardware-derived suites (`z80full`, `z80memptr`,
  `z80ccf`)—values captured from a real 48K ZX Spectrum's Zilog Z80, covering
  instruction semantics and flags including SCF/CCF's undocumented X/Y-flag
  behavior against the genuine NMOS convention. This is the project's first
  certification against real silicon rather than a software-derived corpus;
  and
- FUSE 1.6.0's Z80 core test set, **1,356** emulator-derived cases, of which
  1,350 agree and the six that do not are each explained by a
  hardware-derived source the core follows instead
  ([validation](docs/validation.md)).

The current processor implementation was recertified after the lifecycle and
inspection work. Exact source revisions, hashes, commands, timings, and scope
limits are recorded in [the validation evidence](docs/validation.md).

This is an instruction-level semantic and lifecycle claim. It is **not** a claim
of cycle-accurate bus-pin behavior or of a complete computer.

### CI coverage

The two badges cover different things, and neither covers everything. A green
**CI** badge alone would not mean the oracle gates above passed, so they are
separated rather than implied:

| Badge | Runs | When |
| --- | --- | --- |
| **CI** | unit and integration suite, Ruff, the example host, a wheel build and installed-API smoke test, on Python 3.11/3.12/3.13; plus the FUSE oracle | every push and pull request |
| **Oracles** | SingleStepTests (1,604 files, 1,604,000 cases), z80test (`z80full`, `z80ccf`, `z80memptr`), FUSE, and the superzazu/z80 interrupt cross-check, each against its pinned corpus | weekly, and on demand |

**ZEXDOC and ZEXALL are certified locally, not in CI.** They need
`zexdoc.com`/`zexall.com`, which no script here fetches, and take roughly 90
minutes each under CPython. Their revisions, file hashes, commands and timings
are in [the validation evidence](docs/validation.md); treat that record, not a
badge, as the citation for those two gates.

## Vibe coded, oracle validated

This project was developed with extensive AI assistance—“vibe coded” in the
colloquial sense. That history is intentional and worth stating plainly: the
implementation demonstrates what AI-assisted engineering can produce when the
feedback loop is stronger than the model's confidence.

Generated emulator code can be plausible and wrong, especially around prefixes,
undocumented flags, WZ/MEMPTR, Q, and refresh behavior. The project therefore
does not treat AI output or code review as proof. Independent SingleStep vectors,
focused regressions, ZEX CRCs, and real emulator integrations are the authority.
See [AI-assisted development and validation](docs/ai-assisted-development.md).

## Version status

The current release is **`0.3.0`**.

| Source | Status | Contents |
| --- | --- | --- |
| PyPI `0.3.0` | Published release | Complete validated core and inspection toolkit |
| GitHub `v0.2.0` | Published milestone | RESET, CPU state, disassembly, and debugger foundations |
| GitHub `v0.3.0` | Current release | API hardening and advanced trace diagnostics |

### Install from PyPI

```text
python -m pip install z80-python
```

### Install the source tree

```text
git clone https://github.com/alewman/z80-python.git
cd z80-python
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -e .
```

Recent Debian, Ubuntu, Fedora, and Homebrew Pythons refuse `pip install` into
the system interpreter (PEP 668); the virtual environment line above is the
supported way around that.

For tests, linting, and development tools:

```text
python -m pip install -e ".[dev]"
```

The distribution is named `z80-python`; its public import is `z80_python` to
avoid ambiguity with the unrelated `z80` distribution on PyPI.

## Minimal host

A machine subclasses `Z80CPU` and supplies its 16-bit memory and I/O spaces:

```python
from z80_python import Z80CPU


class Machine(Z80CPU):
    def __init__(self) -> None:
        super().__init__()
        self.memory = bytearray(0x10000)
        self.ports = bytearray(0x10000)

    def read_byte(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write_byte(self, addr: int, value: int) -> None:
        self.memory[addr & 0xFFFF] = value & 0xFF

    def read_port(self, addr: int) -> int:
        return self.ports[addr & 0xFFFF]

    def write_port(self, addr: int, value: int) -> None:
        self.ports[addr & 0xFFFF] = value & 0xFF


cpu = Machine()
cpu.memory[:3] = bytes((0x3E, 0x2A, 0x3C))  # LD A,2Ah; INC A
assert cpu.step() == 7
assert cpu.step() == 4
assert cpu.a == 0x2B
```

`step()` advances one instruction or accepted lifecycle boundary and returns its
documented T-state total. Registers and modeled processor state are directly
readable and writable. `decode_and_execute()` remains the historical
instruction-only entry point; new hosts should normally use `step()`.

## Processor lifecycle

The core models external processor inputs as deterministic transitions between
instructions:

- **RESET** is host-controlled and level-sensitive. While asserted, each
  `step()` applies the documented processor-state effects in 3 T-states without
  fetching an instruction or accessing the stack.
- **NMI** is accepted at the next available boundary, wakes HALT, preserves the
  prior `IFF1` in `IFF2`, pushes `PC`, and enters `0x0066` in 11 T-states.
- **Maskable interrupts** honor `IFF1`, the one-instruction `EI` delay, HALT, and
  interrupt modes 0, 1, and 2. IM 0 is intentionally bounded to device-supplied
  `RST` opcodes.

RESET has priority over NMI; NMI has priority over an acceptable maskable
interrupt. Hosts schedule devices from returned T-state totals and request
interrupts through the public lifecycle API rather than mutating `PC`, `SP`, or
interrupt flip-flops to synthesize entry.

See [the interrupt lifecycle contract](docs/interrupt-lifecycle.md) for exact
state transitions and exclusions.

## Reference-core boundary

`z80-python` owns:

- Z80 instruction semantics and documented instruction T-state totals;
- registers, flags, alternate registers, and modeled internal processor state;
- RESET, NMI, maskable interrupts, EI delay, RETN, and HALT behavior; and
- processor-level observation and debugging values.

A host machine owns:

- ROM, RAM, memory maps, ports, mappers, and open-bus behavior;
- video, audio, input, and other devices;
- frame, scanline, clock, and interrupt scheduling;
- device events and side-effect-free memory peeking; and
- complete machine save states, deterministic replay, and rewind.

Accordingly, the project does not claim:

- cycle-accurate bus cycles, contention, `WAIT`, `BUSREQ`, or pin timing;
- interrupt-acknowledge bus callbacks, daisy chains, or arbitrary IM 0 injected
  instructions;
- a complete CP/M system, arcade board, console, or computer; or
- a universal machine scheduler or save-state format.

These are scope boundaries, not unfinished promises. They keep the core readable,
portable, and useful across different machines.

## Learning and inspection

New to the Z80? Read [Start here](docs/start-here.md) first: the register file,
the flag byte, the opcode bit fields every handler decodes, the prefix model,
and the three internal registers (WZ, Q, R) that only emulator authors meet.

The implementation is organized by instruction family behind a small public
`Z80CPU` facade. Every opcode handler's docstring starts with its Zilog
mnemonic, so `grep DJNZ src/` lands on the implementation, and the hardware
reason behind each undocumented flag or MEMPTR effect is a comment on the line
that encodes it. A test (`tests/test_readability.py`) enforces the first
property the same way the vector gate enforces correctness.

The development tree also provides immutable `CPUState` capture and restoration
for processor-owned state and a complete structured disassembler for every opcode
form supported by the core. Disassembly requires an explicit side-effect-free byte
reader: debugging must not accidentally acknowledge or mutate a mapped device.

These APIs make the project useful as:

- a reference while learning Z80 instructions and flags;
- a tested foundation for emulators and machine experiments;
- a source of deterministic examples and regression witnesses; and
- an executable environment where an AI agent can inspect real state instead of
  guessing from source code alone.

See [CPU state](docs/cpu-state.md), [disassembly](docs/disassembly.md), and
[undocumented behavior](docs/undocumented-behavior.md).

## Conformance for ports in other languages

A manifest pins a machine (memory, initial state, host profile, interrupt
events, stop rule); the reference core produces a trace for it, and a core in
any language can be diffed against that trace after every instruction, with
T-states and all 28 processor-state fields compared:

```text
python -m z80_python.conformance trace examples/conformance/interrupts.json --out ref.jsonl
python -m z80_python.conformance diff  examples/conformance/interrupts.json yours.jsonl
```

See [conformance](docs/conformance.md) for the host contract and the
certification ladder, and [the trace schema](docs/trace-schema.md) for the
record format.

## Advanced diagnostics and tooling

The following development-tree features support emulator diagnosis but are
secondary to the instruction core itself:

- `DebugSession` wraps an existing host with bounded execution, execute
  breakpoints, lifecycle-aware records, T-state totals, and bounded history. It
  adds no callback or history overhead when unused.
- `CommandDebugger` is a dependency-free text-stream frontend for registers,
  stepping, bounded runs, breakpoints, disassembly, memory display, and history.
- Trace comparison finds the first differing instruction, lifecycle boundary,
  timing result, or individual CPU-state field across two executions.
- Versioned JSON Lines persistence allows large traces to be written, reloaded,
  and compared incrementally without buffering complete runs.
- Live lockstep comparison can advance two machines under a finite budget and
  stop at the causal processor-visible difference while preserving bounded
  pre-divergence context.

A Galaxian integration proved the intended diagnostic behavior: two otherwise
identical boards differed only in their vblank NMI-enable latch. Comparison
stopped at the exact boundary where one scheduler first asserted pending NMI—one
step before the later control-flow divergence into `0x0066`.

These are deterministic tools, not an embedded LLM or AI provider. Any human UI,
agent, MCP adapter, or model can consume the same structured contracts. See
[debug sessions](docs/debug-session.md), [trace comparison](docs/trace-comparison.md),
and [the tooling roadmap](docs/debugging-roadmap.md).

## Development

Run the ordinary quality gate:

```text
python -m pytest -q
python -m ruff check .
python examples/minimal_z80_host.py
```

The vector corpus and ZEX binaries are external artifacts and are intentionally
not bundled. Fetch the pinned vector corpus with:

```text
python scripts/fetch_test_vectors.py
python -m pytest -q
```

ZEX recertification is reserved for release candidates and semantic-core changes;
reproduction instructions and finite execution budgets are documented in
[the validation evidence](docs/validation.md).

## Project records

- [0.4.0 release notes (in development)](docs/releases/0.4.0.md)
- [0.3.0 release notes](docs/releases/0.3.0.md)
- [Validation evidence and scope](docs/validation.md)
- [Public API stability](docs/api-stability.md)
- [AI-assisted development and validation](docs/ai-assisted-development.md)
- [Extraction provenance](docs/provenance.md)
- [Interrupt lifecycle](docs/interrupt-lifecycle.md)
- [CPU state](docs/cpu-state.md)
- [Disassembly](docs/disassembly.md)
- [Debug sessions](docs/debug-session.md)
- [Trace comparison](docs/trace-comparison.md)
- [Conformance for other cores](docs/conformance.md)
- [Trace schema](docs/trace-schema.md)
- [Start here: Z80 primer](docs/start-here.md)
- [Undocumented behavior](docs/undocumented-behavior.md)
- [Debugging and agent-tooling roadmap](docs/debugging-roadmap.md)
- [Contribution guidance](CONTRIBUTING.md)

## License

MIT. External validation artifacts retain their own licenses and are not bundled
in this distribution.
