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