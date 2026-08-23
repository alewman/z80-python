# z80-python

A readable, pure-Python Z80 **instruction-core reference implementation**.

`z80-python` is deliberately a CPU core rather than a complete computer or arcade
emulator. A host subclass supplies 16-bit memory and I/O access; the core executes
one instruction at a time and returns its documented T-state total.

## Validation status

The extracted core has passed:

- all 1,604 local `SingleStepTests/z80` opcode/prefix vector files, comprising
  1,604,000 state transitions; and
- ZEXDOC and ZEXALL long-sequence CRC exercisers under both CPython 3.12 and
  PyPy 3.11.

See [validation evidence](docs/validation.md) for exact hashes, commands,
results, and scope limits. This does **not** claim cycle-accurate bus behavior,
a complete Z80 machine, CP/M, or a Galaxian board.

## Install

```text
python -m pip install z80-python
```

The public import is `z80_python`, intentionally distinct from the unrelated
existing `z80` distribution on PyPI.

## Minimal host

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

`step()` is the public one-instruction entry point. `decode_and_execute()` is
retained as a supported historical name. CPU registers and modeled state are
directly readable and writable; the host owns memory, devices, and reset policy.

## Maskable interrupts

The core provides a deterministic instruction-boundary model for external maskable
interrupts. A host asserts a request with `request_maskable_interrupt()` and calls
`step()` normally. Once `IFF1` permits it (including the real one-instruction `EI`
delay), `step()` returns the interrupt lifecycle timing and transfers control:

- IM 1 enters `0x0038` in 13 T-states, which is the standard arcade-board case;
- IM 2 reads a two-byte target through `I` plus the supplied device vector byte in
    19 T-states; and
- IM 0 intentionally supports device-supplied `RST` opcodes only.

Acceptance pushes the instruction-boundary PC, clears both interrupt flip-flops, and
wakes a halted CPU. A masked request remains pending until accepted or explicitly
removed with `clear_maskable_interrupt()`. This is a lifecycle abstraction, not a
cycle-accurate interrupt-acknowledge bus model.

See [the interrupt lifecycle contract](docs/interrupt-lifecycle.md) for exact mode,
timing, and scope details.

## Non-maskable interrupts

Hosts request an NMI with `request_non_maskable_interrupt()`. It is accepted at the
next instruction boundary regardless of `IFF1` or EI delay, takes priority over a
maskable request, wakes HALT, pushes the boundary PC, copies `IFF1` to `IFF2`,
clears `IFF1`, and enters `0x0066` in 11 T-states. A pending NMI can be inspected
through `non_maskable_interrupt_pending` or cancelled with
`clear_non_maskable_interrupt()`.

## Development and validation

```text
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python examples/minimal_z80_host.py
```

The vector corpus and ZEX binaries are external artifacts, intentionally not
bundled in releases. Fetch the pinned vector corpus with
`python scripts/fetch_test_vectors.py`, then rerun the test suite. See
[validation evidence](docs/validation.md) for ZEX instructions.

## Project records

- [Validation evidence and scope](docs/validation.md)
- [Debugging and agent-tooling roadmap](docs/debugging-roadmap.md)
- [Undocumented behavior notes](docs/undocumented-behavior.md)
- [AI-assisted development and validation](docs/ai-assisted-development.md)
- [Extraction provenance](docs/provenance.md)
- [Contribution guidance](CONTRIBUTING.md)

## License

MIT. External validation artifacts have their own licenses and are not bundled.
