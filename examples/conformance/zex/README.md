# ZEXDOC and ZEXALL, diffed in parallel segments

Rung 3 of the [certification ladder](../../../docs/conformance.md#certification-ladder):
your core's trace of ZEXDOC or ZEXALL, diffed against this one's, record by
record. Each program is 5,764,169,474 records, far too many for one pipe (the
reference side of `diff` manages tens of thousands of records per second on
PyPy), so the run is cut into segments of 50,000,000 records that are diffed
side by side. z80-rust certified this way (its `scripts/rung3.sh`).

This directory ships the two manifests and the SHA-256 of every checkpoint they
produce, not the checkpoints themselves: each checkpoint holds a full 64 KiB
memory image, which contains the GPL-2.0 ZEX program, and this repository does
not redistribute it.

## 1. Fetch and check the programs

Download `zexdoc.com` and `zexall.com` from <https://github.com/agn453/ZEXALL>
into this directory and check them against the SHA-256 in
[docs/validation.md](../../../docs/validation.md#zex-long-sequence-certification):

```text
34923A7ED82285D3038B2D54BD64899E12173EEBB61F9D07B4FC72E78AF2AE8F  zexdoc.com
6E2DA55147A04F28D303D5DA6A1E6B771557AC244653590A0F24A2D39C8537E8  zexall.com
```

## 2. Write the checkpoints and check them

```text
cd examples/conformance/zex
pypy3 -m z80_python.conformance checkpoints zexall.json --every 50000000 --dir zexall-segments
(cd zexall-segments && sha256sum -c ../SHA256SUMS.zexall)
```

and the same for `zexdoc`. On PyPy 7.3.20 each program takes about ten minutes;
CPython writes identical files in about 100 minutes per program. Every file
must check out: a checkpoint is the complete machine at that boundary (every
`CPUState` field, the whole of memory), so a mismatch means your program file
or your reference install differs from the one these sums were made with, and
nothing downstream would mean anything.

## 3. Diff every segment against your core

Each checkpoint is a manifest that resumes the run at its boundary for
50,000,000 records (the last ends where the program exits). Trace each with your core and
diff it, as many at once as you have cores:

```text
ls zexall-segments/*.json | xargs -P "$(nproc)" -I{} sh -c \
    'your-trace "{}" | pypy3 -m z80_python.conformance diff "{}" - > "{}.result"; echo $? > "{}.status"'
grep -L '^0$' zexall-segments/*.status    # lists any segment that diverged
```

Each segment starts from the state the previous one ended in, so a clean
result on every segment is a clean result for the whole run, and a divergence
anywhere is reported, with the instruction and every differing field, by the
segment that holds it. Exit status per segment: 0 identical, 1 divergence,
2 malformed manifest or trace.

The sums were written by z80-python 0.4.0 on 2026-09-18. They change only if
the core's behaviour on ZEX changes, which the ZEX certification in
docs/validation.md would also show.
