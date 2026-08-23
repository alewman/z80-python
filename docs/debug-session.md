# Debug Sessions

`DebugSession` is a dependency-free controller around an existing `Z80CPU` host.
It does not subclass the host, install callbacks, or alter the instruction core.

```python
session = DebugSession(
    machine,
    peek_byte=machine.memory.__getitem__,
    history_limit=256,
)
session.add_breakpoint(0x1234)
result = session.run(max_steps=100_000, max_t_states=1_000_000)
```

## Bounded control

Every `run()` call requires a positive `max_steps`. It can also impose a positive
T-state limit. Because one processor boundary is atomic, the returned T-state total
may exceed that limit by the final boundary's cost.

Runs return a `RunResult` with an explicit `StopReason`:

- `BREAKPOINT` stops before an instruction at a selected address executes;
- `HALTED` stops before another idle HALT cycle when no lifecycle request can wake
  the processor;
- `STEP_LIMIT` indicates exhaustion of the mandatory boundary budget; and
- `T_STATE_LIMIT` indicates that the optional timing budget was reached.

Calling `session.step()` always advances exactly one boundary and deliberately
ignores execute breakpoints. This permits a debugger to step over a breakpoint
without temporarily mutating breakpoint state.

## Records and history

Each `StepRecord` contains immutable before/after `CPUState` values, T-states, a
`BoundaryKind`, and optional structured `Instruction` disassembly. Boundary kinds
distinguish normal instructions, HALT idle cycles, RESET, NMI acceptance, and
maskable-interrupt acceptance.

History is an optional bounded ring owned by the session. A limit of zero disables
retention while still returning records directly and maintaining totals. History
does not contain memory or device state and is not rewind.

## Target and peek boundaries

The minimal `DebugTarget` protocol requires only `step()` and `capture_state()`.
Existing hosts therefore work without a debugger-specific subclass. The optional
peek function is separate because ordinary machine reads may have device side
effects. Without a peek function, execution control and breakpoints still work but
instruction records omit disassembly.

Memory and port watchpoints require accurate access events from the host. They are
intentionally deferred until a real machine adapter proves that capability rather
than being simulated through unsafe reads.

## Portable command frontend

`CommandDebugger` is a thin human interface over the session. `execute()` accepts
one command and returns immutable printable lines, making it easy to embed in an
application or test. `interact(input_stream, output_stream)` supplies a portable
line-oriented loop without terminal-framework dependencies.

The frontend includes register display, stepping, bounded runs, execute-breakpoint
management, disassembly, memory display, and retained history. Display commands
have explicit output bounds. Execution and breakpoint semantics remain owned by
`DebugSession`; the frontend does not maintain a competing debugger model and has
no terminal-framework runtime dependency.