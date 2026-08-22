# Extraction provenance

This repository was extracted from the `src/z80/` instruction core in the
private/local Galemu development project at source commit:

```text
535970e Record PyPy Z80 certification and benchmarks
```

The extraction intentionally carries only the CPU core, its focused tests,
minimal host example, benchmark harness, ZEX validation adapter, and the
validation evidence needed to reproduce public claims. It does not carry
Galaxian ROMs, arcade hardware code, machine assets, or the parent project's
history.

The extraction renamed the import package from `z80` to `z80_python`. This
avoids import ambiguity with the pre-existing unrelated `z80` distribution on
PyPI. The distribution name is `z80-python`.

This note is historical context, not a dependency: the standalone repository
must remain buildable and testable on its own.
