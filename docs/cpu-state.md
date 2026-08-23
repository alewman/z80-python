# CPU State

`Z80CPU.capture_state()` returns an immutable `CPUState` value containing the
complete processor-owned state at an instruction boundary. `restore_state()`
applies that value without calling the host's memory or port methods.

The value includes:

- the main and alternate register sets;
- `PC`, `SP`, `IX`, `IY`, `I`, and `R`;
- the complete flags byte;
- undocumented `WZ`/MEMPTR and `Q` state;
- interrupt mode and both interrupt flip-flops;
- HALT and EI-delay state; and
- asserted RESET, pending NMI, and the pending maskable-interrupt vector.

Fields use public, serialization-friendly values: integers, booleans, and an
optional integer interrupt vector. Construction validates register widths,
interrupt mode, EI delay, and boolean fields. The value is comparable and can be
converted with `dataclasses.asdict()`. This release does not promise that the
resulting dictionary is a permanent cross-version save-file format.

## Machine boundary

`CPUState` excludes everything owned by the host:

- memory and cartridge or mapper state;
- ports and devices;
- display, sound, and input state;
- clocks, frame scheduling, and host counters; and
- queued host events.

Restoring only `CPUState` is correct when the host state has not changed, or when
the host restores its own matching state separately. It is not whole-machine
rewind and must not be presented as a complete emulator save state.

## Example

```python
before = cpu.capture_state()
memory_before = bytes(cpu.memory)  # Host-specific state.

cpu.step()

cpu.memory[:] = memory_before
cpu.restore_state(before)
assert cpu.capture_state() == before
```
