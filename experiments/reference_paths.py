"""Configured external, read-only references shared by tests and experiments."""

import os
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def reference_path(key: str) -> Path:
    override = os.environ.get(f"BOOK_CONVERTER_{key.upper()}")
    if override:
        return Path(override).expanduser()
    config = Path(
        os.environ.get(
            "BOOK_CONVERTER_REFERENCE_CONFIG",
            str(PROJECT_ROOT / "experiments/references.toml"),
        )
    )
    values = tomllib.loads(config.read_text("utf-8"))["paths"]
    value = Path(values[key]).expanduser()
    return value if value.is_absolute() else config.resolve().parent / value


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
