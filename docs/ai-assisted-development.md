# AI-assisted development and validation

This project was developed with extensive AI assistance—"vibe coded" in the
colloquial sense—but that is not the basis for its correctness claim.

An agentic runner decomposed early implementation work and exposed real
harness/test failures under a long-running workload. Human-supervised work then
used independent state-vector and ZEX exerciser feedback to correct semantics.
The implementation is trusted only to the stated boundary because reproducible
external validation passed:

- 1,604,000 SingleStepTests state transitions;
- ZEXDOC long-sequence CRC checks; and
- ZEXALL long-sequence CRC checks, including undocumented X/Y behavior.

AI can generate plausible but wrong emulator logic, especially around
prefixes, WZ/MEMPTR, Q, refresh-state effects, and undocumented flags. The
project's central engineering decision was therefore to use independent
oracles, direct regression tests, and bounded certification runs rather than
treating generated code as self-validating.

Future contributions should preserve that discipline: semantic changes require
focused tests and the full vector gate; release candidates require ZEX
recertification as described in [validation.md](validation.md).
