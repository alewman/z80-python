"""Fetch the exact external SingleStepTests/z80 revision used for certification."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPOSITORY = "https://github.com/SingleStepTests/z80.git"
REVISION = "ebe1875d48f374bcfd4b505d8eb8ee751568b5f7"
ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "tests" / "z80_test_vectors"


def main() -> None:
    """Clone and verify the pinned MIT-licensed vector corpus."""
    if DESTINATION.exists():
        raise SystemExit(
            f"{DESTINATION} already exists; remove it before fetching the pinned corpus"
        )
    if shutil.which("git") is None:
        raise SystemExit("git is required to fetch the vector corpus")

    subprocess.run(["git", "clone", REPOSITORY, str(DESTINATION)], check=True)
    subprocess.run(["git", "-C", str(DESTINATION), "checkout", "--detach", REVISION], check=True)
    actual = subprocess.check_output(
        ["git", "-C", str(DESTINATION), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != REVISION:
        raise RuntimeError(f"vector revision mismatch: expected {REVISION}, got {actual}")
    print(f"Fetched SingleStepTests/z80 at {actual}")


if __name__ == "__main__":
    main()
