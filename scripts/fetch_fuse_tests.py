"""Fetch the Z80 core test set from the pinned FUSE release."""

from __future__ import annotations

import hashlib
import tarfile
import urllib.request
from pathlib import Path

RELEASE_URL = "https://sourceforge.net/projects/fuse-emulator/files/fuse/1.6.0/fuse-1.6.0.tar.gz/download"
SHA256 = "3a8fedf2ffe947c571561bac55a59adad4c59338f74e449b7e7a67d9ca047096"
ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "validation" / "fuse_data"
MEMBERS = {
    "fuse-1.6.0/z80/tests/tests.in": "tests.in",
    "fuse-1.6.0/z80/tests/tests.expected": "tests.expected",
    "fuse-1.6.0/COPYING": "COPYING",
}


def main() -> None:
    """Download, verify, and unpack the two test files and their license."""
    if DESTINATION.exists():
        raise SystemExit(
            f"{DESTINATION} already exists; remove it before fetching the pinned release"
        )

    archive = ROOT / "validation" / "fuse-1.6.0.tar.gz"
    print(f"Downloading {RELEASE_URL}")
    urllib.request.urlretrieve(RELEASE_URL, archive)

    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != SHA256:
        archive.unlink()
        raise RuntimeError(f"FUSE archive hash mismatch: expected {SHA256}, got {actual}")

    DESTINATION.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        for member, name in MEMBERS.items():
            handle = tar.extractfile(member)
            if handle is None:
                raise RuntimeError(f"FUSE archive did not contain {member}")
            (DESTINATION / name).write_bytes(handle.read())
    archive.unlink()
    print(f"Fetched FUSE 1.6.0 z80/tests into {DESTINATION}")


if __name__ == "__main__":
    main()
