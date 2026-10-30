"""Fixtures for adapter tests (helpers live in adapter_fixtures.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from adapter_fixtures import PROFILES, build_sample


@pytest.fixture
def sample_book(tmp_path) -> Path:
    return build_sample(tmp_path / "book")


@pytest.fixture
def store(tmp_path):
    from book_adapters.engine.profile_store import ProfileStore

    return ProfileStore(PROFILES, tmp_path / "store")


@pytest.fixture
def settings_file(tmp_path) -> Path:
    path = tmp_path / "9780306406157.yaml"
    path.write_text(
        "isbn: '9780306406157'\ntitle: A Test Book\nedition: First Edition\n"
        "profile: jaypee_v3\nauthorgroups:\n  - - firstname: Ann\n      surname: Author\n",
        "utf-8",
    )
    return path
