"""The format sections of a profile (``html``, ``dtbook``, ``daisy3``, ``jats``, ``bits``, ``tail``).

A profile may leave a section out: the schema defaults apply to every field it does not set,
so any profile can be given to any format writer (the report then says the section was
missing)."""

from __future__ import annotations

import copy
from typing import Any

from .profile import Profile, apply_defaults, load_schema

FORMAT_SECTIONS = ("html", "dtbook", "daisy3", "jats", "bits", "tail")
WRITER_SECTION = {
    "html": "html",
    "dtbook": "dtbook",
    "daisy3": "daisy3",
    "jats": "jats",
    "bits": "bits",
    "tail": "tail",
}


def format_section(profile: Profile, name: str) -> dict[str, Any]:
    schema = load_schema()
    data = copy.deepcopy(profile.data.get(name) or {})
    return apply_defaults(data, schema["properties"][name], schema)


def has_section(profile: Profile, name: str) -> bool:
    return name in profile.data
