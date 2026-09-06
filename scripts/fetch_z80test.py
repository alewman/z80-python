"""Fetch the pinned raxoft/z80test release used for hardware-oracle validation."""

from __future__ import annotations

import hashlib
import urllib.request
import zipfile
from pathlib import Path

RELEASE_URL = "https://github.com/raxoft/z80test/releases/download/v1.2a/z80test-1.2a.zip"
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
        # The release archive wraps everything in a z80test-1.2a/ directory;
        # tests/test_z80test_suite.py expects the .tap programs directly under
        # DESTINATION, so strip that single leading path component.
        for member in zf.infolist():
            parts = Path(member.filename).parts
            if member.is_dir() or len(parts) < 2:
                continue
            target = DESTINATION.joinpath(*parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(member))
    archive.unlink()
    missing = [
        name
        for name in ("z80full.tap", "z80memptr.tap", "z80ccf.tap")
        if not (DESTINATION / name).is_file()
    ]
    if missing:
        raise RuntimeError(f"z80test archive did not contain expected programs: {missing}")
    print(f"Fetched z80test v1.2a into {DESTINATION}")


if __name__ == "__main__":
    main()
