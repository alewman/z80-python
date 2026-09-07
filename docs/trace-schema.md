# Trace schema (version 1)

A trace is the observable behavior of a Z80 core written down one processor
boundary at a time. Two cores that produce equal traces for the same program
and host are, as far as software can tell, the same CPU. This document is the
contract for producing such a trace in any language so that
`z80_python.conformance` (or `first_trace_divergence` directly) can compare it
against the reference core. Everything here is implemented by
`src/z80_python/trace.py`; if the two disagree, the code is the specification
and this page has a bug.

## File format

JSON Lines: UTF-8 text, one JSON object per line, `\n` terminated, blank lines
ignored. Objects are written with sorted keys and no whitespace by this
package; readers must not depend on either. Each line is one **record**, and
records are aligned by line position when two traces are compared. The
`sequence` field is carried for humans and is never used for alignment.

## Record

| Key | Type | Meaning |
| --- | --- | --- |
| `version` | integer | Always `1` for this schema. A reader rejects any other value. |
| `sequence` | integer >= 0 | Producer-local counter. Informational only. |
| `kind` | string | What the boundary was; one of the five values below. |
| `t_states` | integer > 0 | T-states the boundary consumed, exactly as `step()` returns them. |
| `instruction` | object or `null` | The instruction fetched at this boundary; `null` for every non-instruction kind, and permitted to be `null` for instruction boundaries when the producer cannot disassemble. |
| `before` | state object | Complete processor state at the boundary's start. |
| `after` | state object | Complete processor state at its end. |

No other keys are allowed.

### `kind`

| Value | When |
| --- | --- |
| `instruction` | An opcode was fetched and executed. |
| `halt_idle` | The CPU was halted and no request could wake it: a 4-T-state idle step. |
| `reset` | RESET was asserted: the 3-T-state reset step. |
| `non_maskable_interrupt` | A latched NMI was accepted: 11 T-states, entry at 0x0066. |
| `maskable_interrupt` | A pending maskable request was accepted with IFF1 set and no EI delay: 13 T-states in IM 0/1, 19 in IM 2. |

The kind is decided from `before` in this order: `reset_pending`, then
`non_maskable_interrupt_pending`, then a non-null `maskable_interrupt_vector`
with `iff1` true and `ei_delay` 0, then `halted`, else `instruction`. A
producer whose `kind` disagrees with its own `before` state is malformed.

### `instruction`

| Key | Type | Required | Meaning |
| --- | --- | --- | --- |
| `address` | integer 0..0xFFFF | yes | PC at fetch. |
| `data` | lowercase hex string | yes | Every byte the instruction occupies, prefixes and operands included, e.g. `"ddcb0546"`. |
| `mnemonic` | string | optional | Uppercase mnemonic as this package's disassembler prints it. |
| `operands` | array of strings | optional | Operand texts as the disassembler prints them. |

`mnemonic` and `operands` are present together or absent together. **A
producer in another language should omit both.** The reader then decodes
`data` at `address` with this package's disassembler and fills them in, so a
port never has to reproduce the reference formatting; it only has to get the
bytes right. If `data` is not exactly one decodable instruction the record is
rejected.

### State object

Every key below is required, none may be omitted, and no others are allowed.
Integers are unsigned; booleans are JSON `true`/`false`.

| Key | Type | Meaning |
| --- | --- | --- |
| `a` `f` `b` `c` `d` `e` `h` `l` | 0..255 | Main register set; `f` is the whole flag byte including X and Y. |
| `ix` `iy` `sp` `pc` | 0..65535 | Index registers, stack pointer, program counter. |
| `wz` | 0..65535 | MEMPTR, the internal address latch. |
| `i` `r` | 0..255 | Interrupt page and refresh register, all 8 bits of each. |
| `iff1` `iff2` | boolean | Interrupt flip-flops. |
| `im` | 0, 1, or 2 | Interrupt mode. |
| `af_alt` `bc_alt` `de_alt` `hl_alt` | 0..65535 | Alternate register pairs, high byte first (`af_alt` = A' << 8 \| F'). |
| `q` | 0..255 | The flag latch: F after an instruction that wrote flags, else 0. |
| `halted` | boolean | HALT state. |
| `ei_delay` | 0 or 1 | 1 for exactly the one instruction after EI. |
| `reset_pending` | boolean | Host has RESET asserted. |
| `maskable_interrupt_vector` | 0..255 or `null` | Pending maskable request and its bus byte; `null` when none. |
| `non_maskable_interrupt_pending` | boolean | Latched NMI request. |

These are the 29 fields of `CPUState` and are the definition of "processor
state" for equivalence purposes. Memory, ports, and devices are host state and
are not in the trace; equality of traces implies equality of every memory and
port access the CPU made only when both cores ran the same host, which is what
a conformance manifest guarantees.

## Example

An external producer's record for `INC A` at 0x0100 with A = 0x2A:

```json
{"after":{"a":43,"af_alt":0,"b":0,"bc_alt":0,"c":0,"d":0,"de_alt":0,"e":0,"ei_delay":0,"f":40,"h":0,"halted":false,"hl_alt":0,"i":0,"iff1":false,"iff2":false,"im":0,"ix":0,"iy":0,"l":0,"maskable_interrupt_vector":null,"non_maskable_interrupt_pending":false,"pc":257,"q":40,"r":1,"reset_pending":false,"sp":0,"wz":0},"before":{"a":42,"af_alt":0,"b":0,"bc_alt":0,"c":0,"d":0,"de_alt":0,"e":0,"ei_delay":0,"f":0,"h":0,"halted":false,"hl_alt":0,"i":0,"iff1":false,"iff2":false,"im":0,"ix":0,"iy":0,"l":0,"maskable_interrupt_vector":null,"non_maskable_interrupt_pending":false,"pc":256,"q":0,"r":0,"reset_pending":false,"sp":0,"wz":0},"instruction":{"address":256,"data":"3c"},"kind":"instruction","sequence":0,"t_states":4,"version":1}
```

## Comparison rules

`compare_step_records` reports every differing field by path: `kind`,
`t_states`, `instruction.address`, `instruction.data`, `instruction.mnemonic`,
`instruction.operands`, and `before.<field>` / `after.<field>` for each state
key. When one trace ends before the other, the divergence path is `record`
with values `"present"` and `null`. Comparison is lazy: the first divergence
is found without reading either file to the end.

## Versioning

Any change to the set of keys, their types, or their meaning is a new
`version`, and readers reject versions they do not know. Making `mnemonic` and
`operands` optional for producers did not change the version: every version 1
trace written before that change is still valid, and every field a version 1
reader could rely on is still present in traces this package writes.
