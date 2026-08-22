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
a complete Z80 machine, CP/M, interrupt lifecycle handling, or a Galaxian board.

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
- [Undocumented behavior notes](docs/undocumented-behavior.md)
- [AI-assisted development and validation](docs/ai-assisted-development.md)
- [Extraction provenance](docs/provenance.md)
- [Contribution guidance](CONTRIBUTING.md)

## License

MIT. External validation artifacts have their own licenses and are not bundled.
