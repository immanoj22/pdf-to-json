"""Where the profiles folder and the user profile store are."""

from __future__ import annotations

import os
from pathlib import Path

PROFILES_ENV = "BOOK_ADAPTERS_PROFILES"
STORE_ENV = "BOOK_ADAPTERS_PROFILE_STORE"


def profiles_root() -> Path:
    """The built-in profiles folder: $BOOK_ADAPTERS_PROFILES, else the nearest ``profiles``
    folder (holding ``schema/profile.schema.json``) above this package."""
    override = os.environ.get(PROFILES_ENV)
    if override:
        return Path(override).expanduser()
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "profiles"
        if (candidate / "schema" / "profile.schema.json").is_file():
            return candidate
    raise FileNotFoundError(f"No profiles folder found; set {PROFILES_ENV}")


def store_root() -> Path:
    """The user profile store (uploaded profiles): $BOOK_ADAPTERS_PROFILE_STORE, else
    ``_store`` inside the profiles folder (git-ignored)."""
    override = os.environ.get(STORE_ENV)
    return Path(override).expanduser() if override else profiles_root() / "_store"
