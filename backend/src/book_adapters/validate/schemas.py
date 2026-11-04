"""Offline schema validation with the pinned official DTDs (``validate/dtds``): no network, no
installed validator. A document names its DOCTYPE as the standard does (public and system
identifiers of the official DTD); a resolver maps those to the pinned local files."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from lxml import etree

DTD_ROOT = Path(__file__).parent / "dtds"


@lru_cache(maxsize=1)
def verify_pinned() -> None:
    pinned = json.loads((DTD_ROOT / "PINNED.json").read_text("utf-8"))
    for rel, sha in pinned["files"].items():
        if hashlib.sha256((DTD_ROOT / rel).read_bytes()).hexdigest() != sha:
            raise RuntimeError(f"Pinned schema file changed: {rel}")


class PinnedResolver(etree.Resolver):
    """Maps a DTD named by its official URL (or file name) to the pinned copy."""

    def __init__(self, folders: list[str]):
        super().__init__()
        self.files: dict[str, Path] = {}
        for folder in folders:
            for path in (DTD_ROOT / folder).rglob("*"):
                if path.is_file():
                    self.files.setdefault(path.name, path)

    def resolve(self, system_url, public_id, context):
        if system_url and not system_url.startswith("/"):
            name = system_url.rsplit("/", 1)[-1]
            if name in self.files and (
                system_url.startswith(("http", "file:")) or "/" not in system_url
            ):
                return self.resolve_filename(str(self.files[name]), context)
        return None


def validate(data: bytes, folders: list[str]) -> list[str]:
    """DTD errors of one document (empty: valid)."""
    verify_pinned()
    parser = etree.XMLParser(
        load_dtd=True, dtd_validation=True, no_network=True, resolve_entities=False
    )
    parser.resolvers.add(PinnedResolver(folders))
    try:
        etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        log = [f"line {e.line}: {e.message}" for e in exc.error_log]
        return log or [str(exc)]
    return []
