# Trace comparison

`first_trace_divergence()` compares two deterministic streams of `StepRecord`
values and returns the first unequal processor boundary. `iter_trace_divergences()`
yields every unequal aligned position without loading either complete trace.

```python
divergence = first_trace_divergence(first_session.history, second_session.history)
if divergence is not None:
    for difference in divergence.differences:
        print(difference.path, difference.left, difference.right)
```

    For live targets, `first_session_divergence()` advances two `DebugSession` values
    in lockstep under a mandatory finite budget and stops immediately when their
    processor observations differ:

    ```python
    divergence = first_session_divergence(first, second, max_steps=1_000_000)
    ```

    Each session retains its own bounded history, which supplies the instructions
    immediately preceding the divergence without requiring the comparator to buffer
    the full run.

    ### Galemu integration proof

    The first live-machine witness used two otherwise identical synthetic Galaxian
    boards executing `JR -2`. Both boards enabled the deterministic vblank scheduler;
    only the left board's NMI-enable latch was set. Lockstep comparison stopped at
    position 3,583, after 3,584 boundaries on each side. The exact first difference
    was `after.non_maskable_interrupt_pending`: the left scheduler had requested its
    vblank NMI and emitted `vblank_nmi_request`, while the right scheduler had not.

    This is the intended diagnostic shape. It identified the scheduling boundary that
    caused the future control-flow divergence, one step earlier than merely observing
    one CPU enter `0x0066`. The retained eight-record context consisted of the shared
    loop instructions immediately preceding that request.

Comparison covers:

- boundary kind;
- instruction address, encoded bytes, mnemonic, and operands;
- returned T-state count; and
- every field of the before and after `CPUState` values.

The session-local `StepRecord.sequence` field is deliberately excluded from
equality. Traces are aligned by their iterable positions, so independently captured
windows can be compared even when their original session counters differ.

If one trace ends first, the divergence uses the `record` path with `present` on
the remaining side. `TraceDivergence.as_dict()` emits compact, deterministic,
JSON-compatible evidence containing the aligned position, original sequence IDs,
and field-level differences. It does not duplicate complete CPU states.

## Machine events

This API compares processor observations only. Memory writes, port accesses,
device events, frames, and scheduler boundaries remain host-owned. A machine can
compare its event stream separately and combine that first divergence with the
processor result in its own evidence bundle. This avoids making arcade or console
device policy part of the Z80 core.

## Memory behavior

Inputs are consumed incrementally. `first_trace_divergence()` stops reading as soon
as it finds an unequal position. `iter_trace_divergences()` retains no prior records
beyond the current aligned pair, so it can operate on generators and large stored
traces.

## Persisted traces

`write_trace(records, stream)` writes deterministic, versioned JSON Lines without
buffering the iterable. `read_trace(stream)` validates and yields one record at a
time, so two large files can be compared directly:

```python
with open("first.jsonl") as first, open("second.jsonl") as second:
    divergence = first_trace_divergence(read_trace(first), read_trace(second))
```

The schema stores `TRACE_SCHEMA_VERSION`, exact instruction bytes, enum string
values, and every CPU state field. It contains no timestamps or terminal output.
Readers reject unknown, missing, or invalid fields rather than silently changing
the meaning of evidence. A schema change requires a new version.