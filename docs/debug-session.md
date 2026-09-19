# Debug Sessions

`DebugSession` is a dependency-free controller around an existing `Z80CPU` host.
It does not subclass the host or alter the instruction core. It has the same
shape as m6800-python's, so a debugger written for one family core reads like
one for another.

```python
session = DebugSession(
    cpu,
    peek_byte=memory.__getitem__,
    history_limit=256,
    track_accesses=True,
)
session.add_breakpoint(0x1234)
session.add_watchpoint(0x4000, "w")
result = session.run(max_steps=100_000, max_t_states=1_000_000)
```

To step through a binary without writing a host:

```text
python -m z80_python --load program.bin@0x100 --pc 0x100 -c "break 0x1234" -c "run 1000"
python -m z80_python --zip ROMPATH/set.zip:rom.bin@0 -c "watch 0x4000 w" -c "continue"
```

The command line puts the images in flat 64 KiB RAM with nothing on the I/O
bus, tracks accesses, runs the `-c` commands, then reads more from stdin
unless `--batch` is given.

## Bounded control

Every `run()` call requires a positive `max_steps`. It can also impose a positive
T-state limit. Because one processor boundary is atomic, the returned T-state total
may exceed that limit by the final boundary's cost.

Runs return a `RunResult` with an explicit `StopReason`:

- `BREAKPOINT` stops before an instruction at a selected address executes;
- `WATCHPOINT` stops after the step that read or wrote a watched memory byte,
  with the accesses that matched in `RunResult.hits`;
- `HALTED` stops before another idle HALT cycle when no lifecycle request can wake
  the processor;
- `STEP_LIMIT` indicates exhaustion of the mandatory boundary budget; and
- `T_STATE_LIMIT` indicates that the optional timing budget was reached.

Calling `session.step()` always advances exactly one boundary and deliberately
ignores execute breakpoints. This permits a debugger to step over a breakpoint
without temporarily mutating breakpoint state.

## Records and history

Each `StepRecord` contains immutable before/after `CPUState` values, T-states, a
`BoundaryKind`, optional structured `Instruction` disassembly and, when the
session tracks accesses, `accesses`: every bus access the step made, in order,
as `("r" | "w", address, value)` for memory and `("in" | "out", port, value)`
for I/O. Boundary kinds distinguish normal instructions, HALT idle cycles,
RESET, NMI acceptance, and maskable-interrupt acceptance. `next_boundary(state)`
says which kind the next `step()` will be, decided exactly as `Z80CPU.step()`
decides it.

History is an optional bounded ring owned by the session. A limit of zero disables
retention while still returning records directly and maintaining totals. History
does not contain memory or device state and is not rewind.

## Target and peek boundaries

The minimal `DebugTarget` protocol requires only `step()` and `capture_state()`.
Existing hosts therefore work without a debugger-specific subclass. The optional
peek function is separate because ordinary machine reads may have device side
effects. Without a peek function, execution control and breakpoints still work but
instruction records omit disassembly.

## Access tracking and watchpoints

Because the CPU takes its bus as callables (the embedding contract),
`track_accesses=True` can see every access without the host's help: it
replaces the CPU's `read_byte`, `write_byte`, `read_port` and `write_port`
with wrappers that log and then call the originals, and `close()` puts the
originals back. Nothing reads memory the program did not read. A target may
be a whole board: an object whose `step()` runs its devices around one CPU
step and whose `cpu` attribute is the processor, whose bus is then the one
tracked.

`add_watchpoint(address, "r" | "w" | "rw")` needs a tracking session and
watches one memory byte; `run()` stops after any step whose accesses touch
it. Ports are recorded in `accesses` but not watched.

## Portable command frontend

`CommandDebugger` is a thin human interface over the session. `execute()` accepts
one command and returns immutable printable lines, making it easy to embed in an
application or test. `interact(input_stream, output_stream)` supplies a portable
line-oriented loop without terminal-framework dependencies.

The frontend includes register display, stepping (`step`, and `over`, which runs
a `CALL` or `RST` through to its return), bounded runs (`run`, and `continue`,
which steps off a breakpoint first), breakpoints and watchpoints, disassembly,
memory display, retained history, `set` for registers, and the interrupt
inputs (`int VECTOR`, `int off`, `nmi`, and `reset`, which pulses RESET for one
step). `help` lists them. The command set and its one-letter aliases match
m6800-python's; numbers here stay decimal unless written `0x1234` or `$1234`,
as they were before 0.4.0. Display commands have explicit output bounds.
Execution and breakpoint semantics remain owned by `DebugSession`; the frontend
does not maintain a competing debugger model and has no terminal-framework
runtime dependency.