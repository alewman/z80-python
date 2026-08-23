# Contributing

Issues are the right place for bug reports, API discussion, and proposed changes.

For a pull request:

1. Keep the instruction core independent of machine/device policy.
2. Add or update a focused regression test for behavior changes.
3. Run `python -m pytest -q` and `python -m ruff check .`.
4. If the change affects instruction semantics, fetch the pinned vector corpus
   and run the complete vector gate. Release candidates and semantic-core changes
   must also rerun ZEXDOC and ZEXALL as documented in [docs/validation.md](docs/validation.md).
5. Public API and lifecycle changes require built-wheel consumer tests. Keep CPU
   state, disassembly, debugging, and host/device boundaries explicit in those tests.

Do not commit vector payloads, ZEX binaries, ROMs, caches, generated package
artifacts, or credentials.
