"""Offline DTD validation with the pinned OASIS DocBook XML 4.2 DTD (no network)."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from lxml import etree

DTD_DIR = Path(__file__).parent / "docbook42"


def verify_pinned() -> None:
    pinned = json.loads((DTD_DIR / "PINNED.json").read_text("utf-8"))
    for rel, sha in pinned["files"].items():
        if hashlib.sha256((DTD_DIR / rel).read_bytes()).hexdigest() != sha:
            raise RuntimeError(f"Pinned DocBook DTD file changed: {rel}")


@lru_cache(maxsize=1)
def docbook_dtd() -> etree.DTD:
    verify_pinned()
    return etree.DTD(str(DTD_DIR / "docbookx.dtd"))


def validate_file(path: Path) -> list[str]:
    """DTD errors of one file (its root may be book, part, chapter or index)."""
    parser = etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)
    try:
        tree = etree.parse(str(path), parser)
    except etree.XMLSyntaxError as exc:
        return [f"not well-formed: {exc}"]
    dtd = docbook_dtd()
    if dtd.validate(tree):
        return []
    return [f"line {e.line}: {e.message}" for e in dtd.error_log.filter_from_errors()]


def validate_delivery(root: Path, files: list[str]) -> dict:
    results = {}
    for rel in files:
        if not rel.endswith(".xml") or rel.endswith("page_info.xml"):
            continue
        errors = validate_file(root / rel)
        results[rel] = {"errors": len(errors), "first": errors[:5]}
    total = sum(r["errors"] for r in results.values())
    return {
        "dtd": "OASIS DocBook XML 4.2 (pinned)",
        "files": len(results),
        "errors": total,
        "by_file": {k: v for k, v in results.items() if v["errors"]},
    }
