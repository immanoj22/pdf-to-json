"""Recreate untracked unseen-page fixtures from the Step 4a-v manifest.

Each manifest row names a configured source key, a physical page and SHA-256 digests of
the source and of the fixture. The source digest is checked before cutting and the fixture
digest after; a mismatch is an error, never a silent substitute.

Usage: python recreate_unseen_fixtures.py [fixture_id ...]   (default: every missing fixture)
"""

import hashlib
import json
import sys
from pathlib import Path

import pymupdf
from step4av_scan import SOURCES

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments/out/step4av/fixtures_manifest.json"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cut(source, physical_page, dest):
    """Byte-reproducible single-page cut: no random trailer /ID, so digests are stable."""
    with pymupdf.open(source) as doc, pymupdf.open() as single:
        single.insert_pdf(doc, from_page=physical_page - 1, to_page=physical_page - 1)
        single.save(dest, garbage=3, deflate=True, no_new_id=True)


def recreate(row, force=False):
    dest = ROOT / row["fixture"]
    if dest.exists() and not force:
        return "present"
    source = SOURCES[row["source_key"]]
    if not source.exists():
        raise FileNotFoundError(f"{row['id']}: source {row['source_key']} not found at {source}")
    if sha256(source) != row["source_sha256"]:
        raise ValueError(f"{row['id']}: source digest differs from the manifest")
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_suffix(".tmp.pdf")
    cut(source, row["physical_page"], temporary)
    if sha256(temporary) != row["fixture_sha256"]:
        temporary.unlink()
        raise ValueError(f"{row['id']}: recreated fixture digest differs from the manifest")
    temporary.replace(dest)
    return "recreated"


def main(ids):
    rows = json.loads(MANIFEST.read_text("utf-8"))
    selected = [row for row in rows if not ids or row["id"] in ids]
    for row in selected:
        print(row["id"], recreate(row))


if __name__ == "__main__":
    main(sys.argv[1:])
