"""Fetch the pinned raxoft/z80test release used for hardware-oracle validation."""

from __future__ import annotations

import hashlib
import urllib.request
import zipfile
from pathlib import Path

RELEASE_URL = (
    "https://github.com/raxoft/z80test/releases/download/v1.2a/z80test-1.2a.zip"
)
SHA256 = "7df0443d703e6b3114ea04b4cdef3e13b91421c62e37185c1036d06864cacbaf"
ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "validation" / "z80test_data"


def main() -> None:
    """Download, verify, and unpack the pinned MIT-licensed z80test release."""
    if DESTINATION.exists():
        raise SystemExit(
            f"{DESTINATION} already exists; remove it before fetching the pinned release"
        )

    archive = ROOT / "validation" / "z80test-1.2a.zip"
    print(f"Downloading {RELEASE_URL}")
    urllib.request.urlretrieve(RELEASE_URL, archive)

    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != SHA256:
        archive.unlink()
        raise RuntimeError(f"z80test archive hash mismatch: expected {SHA256}, got {actual}")

    DESTINATION.mkdir(parents=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(DESTINATION)
    archive.unlink()
    print(f"Fetched z80test v1.2a into {DESTINATION}")


if __name__ == "__main__":
    main()
