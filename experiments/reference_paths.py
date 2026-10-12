"""Configured external, read-only references shared by tests and experiments."""

import os
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def reference_path(key: str) -> Path:
    """Resolve a configured reference key.

    Order: the BOOK_CONVERTER_<KEY> environment variable, then the git-ignored sibling
    ``<config stem>.local.toml`` (real paths live there), then the committed config, which
    holds keys only (an empty value means "set locally"). The config is
    experiments/references.toml unless BOOK_CONVERTER_REFERENCE_CONFIG names another file.
    Relative values resolve against the file that holds them.
    """
    override = os.environ.get(f"BOOK_CONVERTER_{key.upper()}")
    if override:
        return Path(override).expanduser()
    config = Path(
        os.environ.get(
            "BOOK_CONVERTER_REFERENCE_CONFIG",
            str(PROJECT_ROOT / "experiments/references.toml"),
        )
    )
    keys = tomllib.loads(config.read_text("utf-8"))["paths"]
    if key not in keys:
        raise KeyError(f"Unknown reference key {key!r} in {config.name}")
    local = config.with_name(f"{config.stem}.local.toml")
    for source in (local, config):
        if not source.exists():
            continue
        value = tomllib.loads(source.read_text("utf-8")).get("paths", {}).get(key, "")
        if value:
            path = Path(value).expanduser()
            return path if path.is_absolute() else source.resolve().parent / path
    raise KeyError(
        f"Reference key {key!r} has no path: set it in {local.name} or BOOK_CONVERTER_{key.upper()}"
    )


def private_file_names() -> frozenset[str]:
    """File names discovery skips entirely, from a git-ignored local list (never committed)."""
    path = Path(
        os.environ.get(
            "BOOK_CONVERTER_PRIVATE_FILES",
            str(PROJECT_ROOT / "experiments/private_files.local.txt"),
        )
    )
    if not path.exists():
        return frozenset()
    lines = (line.strip() for line in path.read_text("utf-8").splitlines())
    return frozenset(line for line in lines if line and not line.startswith("#"))
