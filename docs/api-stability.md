# Public API stability

`z80-python` uses semantic versioning for the public names exported from the
package root and listed in each public module's `__all__`.

## Public contracts

The supported surface includes:

- `Z80CPU`, `Flags`, and flag constants;
- `CPUState` capture and restoration;
- `Instruction` and disassembly functions;
- `DebugSession`, its protocols, enums, and immutable result values;
- `z80_python.conformance`: `Manifest` and its parts, `ConformanceHost`,
  `trace_manifest`, `diff_manifest`, the manifest JSON form, and the command line;
- `CommandDebugger` and command result/error values; and
- trace comparison values and functions.

The package ships a `py.typed` marker so these annotations are available to static
type checkers. Public dataclass field names, enum values, function signatures, and
documented behavior follow semantic-versioning compatibility rules.

Public immutable values validate their field types and ranges when constructed.
`DebugTarget` is a runtime-checkable structural protocol, so machine hosts need not
inherit a debugger-specific base class.

## Not public

Underscore-prefixed modules, methods, attributes, and helpers are implementation
details. Directly writable legacy CPU register attributes remain supported, but
new integrations should prefer immutable values at API boundaries. JSON dictionaries
produced by methods explicitly documented as versioned evidence are public; an
arbitrary `dataclasses.asdict()` result is not automatically a permanent save-file
format.

## Compatibility policy

- Patch releases fix defects without intentional public incompatibilities.
- Minor releases may add fields or APIs while preserving existing consumers.
- Breaking public changes require a major release and migration notes.
- Hardware-fidelity claims remain bounded by the validation and lifecycle scope;
  API stability does not expand those claims.

Development snapshots use a `.dev0` version and are not release promises. Version
0.3.0 is the first PyPI release containing the complete lifecycle, state,
disassembly, debugging, and trace-comparison contracts described here.