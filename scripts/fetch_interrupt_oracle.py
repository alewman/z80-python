"""Fetch and build the independent interrupt-lifecycle cross-check oracle.

This pulls the pinned, MIT-licensed ``superzazu/z80`` core -- a separately
written, zexdoc/zexall-certified Z80 implementation -- and compiles it
together with ``validation/interrupt_oracle_wrapper.c`` (ours) into a shared
library that :mod:`validation.interrupt_crosscheck` drives via ctypes.

This is a cross-implementation consistency check, not a hardware oracle: no
publicly known hardware-captured test corpus exists for interrupt
*sequencing* the way SingleStepTests/z80test exist for instruction semantics.
Two independently written cores agreeing raises confidence; it does not carry
the same evidentiary weight as z80test's real-Spectrum vectors.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPOSITORY = "https://github.com/superzazu/z80.git"
REVISION = "d64fe10a2274e5e40019b1086bf7d8990cbc5f23"
ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "validation" / "interrupt_oracle_src"
LIBRARY = ROOT / "validation" / "interrupt_oracle_src" / "libz80sz.so"
WRAPPER = ROOT / "validation" / "interrupt_oracle_wrapper.c"


def main() -> None:
    """Clone the pinned oracle core and build it into a shared library."""
    if SRC_DIR.exists():
        raise SystemExit(f"{SRC_DIR} already exists; remove it before fetching")
    if shutil.which("git") is None:
        raise SystemExit("git is required to fetch the interrupt oracle")
    cc = shutil.which("cc") or shutil.which("gcc")
    if cc is None:
        raise SystemExit("a C compiler (cc or gcc) is required to build the interrupt oracle")

    subprocess.run(["git", "clone", REPOSITORY, str(SRC_DIR)], check=True)
    subprocess.run(["git", "-C", str(SRC_DIR), "checkout", "--detach", REVISION], check=True)
    actual = subprocess.check_output(
        ["git", "-C", str(SRC_DIR), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != REVISION:
        raise RuntimeError(f"interrupt oracle revision mismatch: expected {REVISION}, got {actual}")

    subprocess.run(
        [
            cc, "-O2", "-fPIC", "-shared", "-I", str(SRC_DIR),
            "-o", str(LIBRARY), str(SRC_DIR / "z80.c"), str(WRAPPER),
        ],
        check=True,
    )
    print(f"Fetched superzazu/z80 at {actual} and built {LIBRARY}")


if __name__ == "__main__":
    main()
