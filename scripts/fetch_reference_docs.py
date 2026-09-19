"""Fetch the two manuals every handler docstring cites, and check their pins.

    python scripts/fetch_reference_docs.py [--dest DIR] [--only UM0080|YOUNG]

``UM0080`` is Zilog's *Z80 CPU User Manual*, UM008011-0816 (August 2016, 332
pages); a handler citing ``UM0080 p. 278`` means its printed page 278. ``YOUNG``
is Sean Young's *The Undocumented Z80 Documented*, version 0.91 (18 September
2005, GNU FDL); ``Young 3.4`` means its section 3.4. docs/validation.md places
both in the oracle tiers: documentation, below every executable oracle.

Neither is redistributed: the download directory is gitignored. Each file is
checked against the SHA-256 recorded below and in docs/validation.md. A
mismatch means the publisher replaced the file; do not silently update the
hash -- check whether the cited page numbers still hold, and record the change.
"""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path

DOCUMENTS = {
    "UM0080": (
        "https://www.zilog.com/docs/z80/um0080.pdf",
        "um0080.pdf",
        "Zilog Z80 CPU User Manual, UM008011-0816",
    ),
    "YOUNG": (
        "http://www.z80.info/zip/z80-documented.pdf",
        "z80-documented.pdf",
        "Sean Young, The Undocumented Z80 Documented, v0.91",
    ),
}

# SHA-256 of each file as fetched on 2026-09-18; recorded in docs/validation.md.
PINNED_SHA256 = {
    "UM0080": "e3c83da5a5d8e372364c20fa53665e6fbb165ec6ac38c8c1eebc359603447b5e",
    "YOUNG": "6413048f39c2e735373b1fb23102599133bc64ccd0ed63b16fbc1173643d7a9d",
}

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) z80-python/docs-fetch"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(name: str, dest: Path) -> Path:
    url, filename, title = DOCUMENTS[name]
    target = dest / filename
    if not target.exists():
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request) as response, target.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
    digest = _sha256(target)
    status = "ok" if digest == PINNED_SHA256[name] else "MISMATCH"
    print(f"{name:<7} {target.stat().st_size:>10,} bytes  {digest}  {status}  {title}")
    if status == "MISMATCH":
        raise SystemExit(f"{name}: expected SHA-256 {PINNED_SHA256[name]}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dest", type=Path, default=Path(__file__).resolve().parents[1] / "reference"
    )
    parser.add_argument("--only", choices=sorted(DOCUMENTS))
    arguments = parser.parse_args()
    arguments.dest.mkdir(parents=True, exist_ok=True)
    for name in [arguments.only] if arguments.only else sorted(DOCUMENTS):
        fetch(name, arguments.dest)


if __name__ == "__main__":
    main()
