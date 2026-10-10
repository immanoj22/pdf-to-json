"""Per-dialect identity of reference dialect profiles (evaluation data, not converter source).

Derived gold is read with one dialect profile: the profile file's common vocabulary plus the
entry of the dialect detected for that reference. A gold manifest is therefore validated
against the digest of that dialect's profile only, so adding a dialect entry for a new book
does not invalidate the gold of other books (Step 10b infrastructure fix).

- ``profile_digest(data, name)``: SHA-256 of the canonical JSON of the common section and the
  named dialect entry.
- New manifests record ``dialect_profile_sha256`` (per dialect) next to the whole-file
  ``dialect_profiles_sha256``.
- Manifests written before the fix carry only the whole-file digest. The per-dialect digests of
  each earlier profile file are recorded as data (``reference_dialects/profile_digests.json``),
  computed from that file before it changed; such a manifest is valid when its dialect's
  recorded digest equals the current one.

The caller also checks that the reference is still detected as the manifest's dialect and
that the reading (units and paths) is unchanged.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

HISTORY = Path(__file__).resolve().parents[3] / "reference_dialects" / "profile_digests.json"


class DialectProfileChanged(ValueError):
    """The dialect profile a gold manifest was derived with has changed."""


def file_digest(data: Mapping) -> str:
    """Whole-file digest, as ``reference.dialects.dialects_from_data`` computes it."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def profile_digest(data: Mapping, name: str) -> str:
    specs = [spec for spec in data["dialects"] if spec["name"] == name]
    if len(specs) != 1:
        raise DialectProfileChanged(f"Dialect profile {name!r} is missing or not unique")
    canonical = json.dumps(
        {"common": data["common"], "dialect": specs[0]},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def profile_digests(data: Mapping) -> dict[str, str]:
    return {spec["name"]: profile_digest(data, spec["name"]) for spec in data["dialects"]}


def load_history(path: Path = HISTORY) -> dict:
    return json.loads(Path(path).read_text("utf-8")) if Path(path).exists() else {}


def check_manifest(manifest: Mapping, data: Mapping, history: Mapping | None = None) -> str:
    """Validate a gold manifest against the current profile of its own dialect.

    Returns how it was validated ("per_dialect" or "recorded_file_digest"); raises
    DialectProfileChanged otherwise.
    """
    provenance = manifest["provenance"]
    name = provenance["dialect"]
    current = profile_digest(data, name)
    recorded = provenance.get("dialect_profile_sha256")
    if recorded is not None:
        if recorded != current:
            raise DialectProfileChanged(f"Dialect profile {name!r} differs from committed gold")
        return "per_dialect"
    whole = provenance["dialect_profiles_sha256"]
    if whole == file_digest(data):
        return "per_dialect"
    history = load_history() if history is None else history
    earlier = history.get("file_digests", {}).get(whole)
    if earlier is None:
        raise DialectProfileChanged(f"No per-dialect record for profile file {whole[:12]}")
    if earlier.get(name) != current:
        raise DialectProfileChanged(f"Dialect profile {name!r} differs from committed gold")
    return "recorded_file_digest"
