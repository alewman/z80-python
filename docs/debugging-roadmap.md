# Debugging and Tooling Roadmap

## Direction

Interactive and agent-assisted debugging are a good fit for `z80-python`. The
core is already useful in a real Galaxian host, where deterministic stepping,
interrupt requests, T-state totals, and memory/device events have proved their
value. A Sega Master System host will put more pressure on interrupts, ports,
device scheduling, mappers, and whole-machine state.

The project should grow a debugging ecosystem without turning the instruction
core into a debugger framework. The desired architecture is:

```text
Z80CPU + host machine
        |
        v
structured debug target and session
        |-------------------|
        v                   v
human terminal UI    agent/tool adapter
```

The shared asset is the structured debug session, not the screen and not an AI
provider. A TUI and an agent should issue the same bounded commands and consume
the same deterministic records.

"Vibe debugging" is a useful informal description, but not a stable technical
term. Public documentation should normally use **agent-assisted debugging** or
**tool-driven debugging**: an agent forms a hypothesis, inspects real state,
runs a bounded experiment, and receives forced feedback from the emulator.

## Invariants

All phases must preserve these properties:

1. `Z80CPU.step()` remains the small, authoritative one-boundary operation.
2. The instruction core retains no debugger, trace-history, UI, network, or AI
   state.
3. Normal execution pays no per-instruction callback cost when debugging is not
   in use. Control belongs around `step()`, not throughout opcode handlers.
4. The base installation remains pure Python with no runtime dependencies.
   Optional presentation dependencies may be isolated in an install extra.
5. CPU state and machine state remain distinct. The core cannot snapshot or
   restore host RAM, mapper, VDP, PSG, input, or scheduler state.
6. Debug reads must not accidentally perform device reads. Generic tooling uses
   an explicit side-effect-free `peek_byte()` contract rather than assuming a
   host's `read_byte()` is safe for disassembly or memory views.
7. Structured output is deterministic, compact, versioned, and independent of
   terminal formatting. No timestamps, colors, or prose are part of its data
   contract.
8. Existing hosts remain source-compatible. New debugging capabilities are
   adapters or optional protocols, not new abstract methods on `Z80CPU`.

These constraints strengthen the reference-core philosophy: the CPU stays easy
to read and embed, while its behavior becomes easier to observe and explain.

## Corrections to the initial design sketch

Several tempting implementations should be avoided:

- Do not add `before_instruction` and `after_instruction` callbacks to the hot
  core path. A controller can inspect state immediately before and after calling
  `step()` with no change to opcode execution.
- Do not make memory and port watchpoints appear universal. The CPU calls methods
  implemented by its host, so only the host can reliably report semantic or
  side-effecting accesses. The debug protocol can accept access events, and
  instrumented hosts can produce them.
- Do not make a TUI-specific CPU subclass. Real machines already subclass
  `Z80CPU`; the debugger must wrap a machine instance rather than compete for its
  inheritance slot.
- Do not add an AI orchestrator, prompt engine, or "repair suggestions" module to
  the library. The reusable feature is a deterministic command and observation
  surface. AI products can consume that surface externally.
- Do not describe CPU-state restoration as rewind. Whole-machine rewind requires
  host-owned device state and deterministic replay.
- Do not introduce Rich, Textual, Pydantic, an MCP SDK, or any model-provider SDK
  as a required dependency. A full-screen UI can be an optional extra after the
  underlying controller works.

## Phase 0 - Stabilize the lifecycle baseline

Complete and release the lifecycle work already in progress before expanding the
public surface.

### Deliverables

- Finalize the level-sensitive RESET contract alongside maskable interrupt and
  NMI lifecycle behavior.
- State explicitly which CPU fields RESET changes, which it preserves, how it
  interacts with pending requests, and what one asserted `step()` returns.
- Add wheel-level lifecycle contracts to the separate compatibility suite.
- Update the README and versioned validation evidence when the contract is
  released.

### Exit criteria

- Unit tests, lint, vector tests, ZEXDOC, and ZEXALL remain green on supported
  CPython and PyPy versions.
- The built wheel passes public-API lifecycle tests without importing private
  modules.
- The release introduces no debugger API yet.

## Phase 1 - Define CPU introspection and disassembly

Build the two read-only primitives every debugger frontend needs.

### CPU state

Add an immutable public `CPUState` value and explicit
`capture_state()`/`restore_state()` methods. The value must include every field
needed to resume CPU execution exactly, including alternate registers,
undocumented state, HALT, EI delay, and pending lifecycle requests. It contains
no host memory or devices.

Restoration must validate widths and legal values rather than assigning an
arbitrary dictionary into the object. The state value should be naturally
comparable and serializable with standard-library tools, but the first release
does not need to promise a permanent save-file encoding.

### Disassembly

Add a complete public disassembler utility returning a structured instruction
record, for example address, raw bytes, size, mnemonic, and formatted operands.
It should cover base, CB, ED, DD, FD, DDCB, and FDCB forms, including documented
alias and ignored-prefix behavior.

The disassembler accepts a byte sequence or an injected side-effect-free byte
reader. It must not silently call a machine's normal `read_byte()` method.

### Exit criteria

- Capturing and restoring around every tested instruction reproduces the same
  subsequent CPU result when the host state is unchanged.
- The state contract includes private execution-relevant fields without exposing
  private implementation names as the serialization format.
- Disassembly has exhaustive opcode-family coverage and boundary tests at
  `0xffff`.
- Disassembly never mutates CPU or host state.
- The normal execution benchmark is unchanged within an agreed noise threshold.

## Phase 2 - Add a dependency-free debug session

Create a controller around an existing CPU host. This is the architectural center
of both human and agent debugging.

### Target protocol

Define a small, runtime-checkable protocol or adapter with capabilities such as:

- access to the CPU instance;
- `step()`;
- side-effect-free `peek_byte()` for disassembly and memory views;
- optional symbol lookup; and
- optional draining of host-produced access or semantic events.

Capabilities should be discoverable. A target without access events can still use
stepping and execute breakpoints; the API should report that memory or I/O
watchpoints are unsupported rather than pretend they work.

### Session model

The session owns:

- instruction and T-state totals;
- execute breakpoints;
- bounded step and run operations;
- stop reasons such as breakpoint, HALT, instruction budget, T-state budget,
  lifecycle boundary, or host stop;
- a bounded ring of immutable step records; and
- register/flag diffs derived from `CPUState`.

Every run command must require a finite instruction or T-state budget. This keeps
the API safe for tests, terminal clients, and autonomous agents.

### Exit criteria

- The controller can debug the minimal example without modifying its CPU class.
- Breakpoints stop before the instruction at the selected address executes.
- HALT and interrupt/reset boundary steps have unambiguous records.
- History is bounded and can be disabled.
- Running the same target twice produces byte-for-byte equivalent structured
  records.

## Phase 3 - Prove host events and machine boundaries in Galaxian

Use the existing emulator as the first real consumer rather than designing
generic watchpoint semantics in isolation.

### Deliverables

- Adapt the Galaxian board to the debug-target protocol without moving board
  behavior into `z80-python`.
- Normalize its existing device, input, memory-write, vblank, and NMI-acceptance
  evidence into optional debug-session events.
- Add read, write, and execute watchpoint experiments where the board can report
  accesses accurately.
- Demonstrate bounded investigations such as stopping at the first vblank NMI,
  first write to the interrupt-enable latch, or first mutation of video RAM.
- Feed any genuinely general contract problems back into the library; keep
  Galaxian addresses and device semantics in Galemu.

### Exit criteria

- Existing deterministic Galaxian boot evidence is unchanged when debugging is
  disabled.
- Debug mode can locate a known board event and emit a compact evidence bundle
  containing CPU state, disassembly, recent steps, and relevant host events.
- Unsupported watchpoint capabilities fail explicitly.

This phase is important: host I/O is where an apparently clean generic debugger
design is most likely to be wrong.

## Phase 4 - Ship human terminal frontends

Build presentation only after the structured session has proved itself.

### 4A: portable command debugger

First provide a dependency-free command interface that works on Windows, Linux,
and macOS. Initial commands should include:

- registers and decoded flags;
- disassembly and side-effect-free memory display;
- step, bounded run, pause, and run-to-address;
- breakpoint and supported-watchpoint management;
- recent history and host events; and
- deterministic JSON export of the current evidence bundle.

The host application remains responsible for constructing its machine and
passing it to the debugger. The package cannot infer how to instantiate an
arbitrary emulator.

### 4B: optional full-screen TUI

Once command semantics are stable, add a full-screen frontend with register,
disassembly, memory, breakpoint, and history panes. If a third-party framework is
used, publish it under a `tui` install extra and keep imports lazy so the base
package remains dependency-free.

The TUI is a view/controller client. It must not become the owner of breakpoint,
trace, or execution semantics.

### Exit criteria

- The command debugger is scriptable and works without optional dependencies.
- The full-screen frontend can be omitted with no loss of programmatic features.
- Terminal snapshot tests are separate from structured-session tests.
- Long values wrap or scroll without corrupting ASCII-safe or redirected output.

## Phase 5 - Expose the agent-assisted debugging seam

Expose the same session commands and records to external tools. This is where
"vibe debugging" becomes a concrete forced-feedback loop.

### Deliverables

- A versioned JSON command/result schema over a simple local transport, initially
  JSON Lines over standard input/output or an in-process API.
- Compact evidence bundles: current state, disassembly around PC, stop reason,
  recent deltas, selected memory, and host events.
- Capability discovery so an agent knows whether it may peek memory, observe
  ports, restore checkpoints, or resolve symbols.
- Read/observe/run commands by default. Mutation of registers, memory, or device
  state must be an explicit capability with clear audit records.
- Hard command budgets and output limits enforced by the session, not merely
  requested in a prompt.

An MCP adapter may be built later as a thin companion integration, but the
project's durable contract should be transport-neutral and must not depend on a
particular editor, model, provider, or agent SDK.

### Exit criteria

- An external process can investigate a deterministic Galaxian checkpoint using
  only structured commands and results.
- The same investigation can be replayed without an LLM.
- Invalid, unsupported, or unbounded commands fail safely and descriptively.
- No model-generated prose is required for library tests.

## Phase 6 - Whole-machine checkpoints and deterministic replay

Delay time travel until the Sega Master System host or another machine gives the
contract concrete requirements.

Define a separate optional machine-state protocol that composes `CPUState` with
host-owned RAM, mapper, VDP, PSG, input, scheduler, pending events, and any other
state required for deterministic continuation. `z80-python` may define or consume
the protocol, but it cannot implement machine snapshots on behalf of a host.

Reverse debugging should initially mean:

1. restore a known whole-machine checkpoint; then
2. deterministically replay to an earlier instruction or event boundary.

It should not claim to undo arbitrary external I/O. Delta compression and frequent
checkpoint rings are optimizations to consider only after correctness is proved.

### Exit criteria

- Restoring a machine checkpoint and replaying produces identical structured
  traces and externally visible machine state.
- CPU-only restore is clearly distinguished from machine restore in names and
  documentation.
- Save-state schema compatibility is either explicitly versioned or explicitly
  not promised.

## Later possibilities

After the first six phases have real consumers, consider:

- labels and symbol files;
- safe conditional-breakpoint expressions;
- trace comparison and first-divergence search;
- instruction/opcode and memory-region profiling;
- source annotations;
- remote debugging transports; and
- machine-specific visualization plugins.

These are not prerequisites for a useful debugger and should not delay the first
small end-to-end path.

## Release and validation policy

Each phase should be independently releasable and should add public API only when
its behavior is demonstrated by a real consumer.

For every phase:

- keep public names out of underscore-prefixed modules;
- add public API and built-wheel contract tests;
- run lint, unit tests, the full external vectors, and ZEX certification whenever
  execution or restorable CPU state changes;
- benchmark both CPython and PyPy before accepting hot-path changes;
- document capability and scope limits beside the feature; and
- update Galemu first as the integration witness, then use the Sega Master System
  host to drive broader machine-state contracts.

## Recommended first vertical slice

After the RESET release, implement only this narrow path:

1. immutable `CPUState` capture;
2. one-instruction structured disassembly;
3. a `DebugSession` with execute breakpoints and bounded history;
4. a dependency-free command debugger; and
5. a Galaxian demonstration that stops at the first accepted vblank NMI and
   exports deterministic evidence.

That slice proves the architecture from CPU to real machine to human/agent-readable
evidence. Memory watchpoints, a full-screen TUI, transports, and rewind can then be
added from observed need rather than speculation.