"""The JSON Schema of the book model and validation of outputs with ``jsonschema``.

The schema is generated from ``assembly.schema`` (Pydantic, serialization mode: every field
an output always carries is required) and committed as ``assembly/book.schema.json``; a test
fails when the committed file differs from the generated one. Outputs are validated against
the committed file with the Draft 2020-12 validator, so a broken file fails clearly with the
path of every error.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from book_core.assembly.schema import SCHEMA_NAME, SCHEMA_VERSION, Book

SCHEMA_FILE = Path(__file__).with_name("book.schema.json")
SCHEMA_ID = f"https://schemas.internal/{SCHEMA_NAME}/{SCHEMA_VERSION}/book.schema.json"


def generate_schema():
    schema = Book.model_json_schema(by_alias=True, mode="serialization")
    return {
        **schema,
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": f"{SCHEMA_NAME} {SCHEMA_VERSION}",
    }


def schema_text():
    return json.dumps(generate_schema(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


@lru_cache(maxsize=1)
def _validator():
    from jsonschema import Draft202012Validator

    schema = json.loads(SCHEMA_FILE.read_text("utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _causes(error):
    """The leaf errors behind a union error, from the branch of the node's own ``type``
    (a unit's kind), deepest first; the error itself when it has no branches."""
    if not error.context:
        return [error]
    leaves = [leaf for sub in error.context for leaf in _causes(sub)]
    # Branches of other unit kinds fail on their "type" constant: not the cause.
    own = [e for e in leaves if not (e.validator == "const" and list(e.absolute_path)[-1:] ==
                                     ["type"])]  # fmt: skip
    leaves = own or leaves
    deepest = max(len(e.absolute_path) for e in leaves)
    return [e for e in leaves if len(e.absolute_path) == deepest]


def errors(data):
    """[(path, message)] of every schema violation of a book dict (empty: valid); a union
    error is reported at its real cause (the field of the unit that is wrong)."""
    found = []
    for error in sorted(_validator().iter_errors(data), key=lambda e: list(e.absolute_path)):
        for cause in _causes(error):
            path = "/".join(str(p) for p in cause.absolute_path) or "(root)"
            if (path, cause.message) not in found:
                found.append((path, cause.message))
    if not found:
        try:
            Book.model_validate(data)
        except ValidationError as error:
            for cause in error.errors(include_url=False, include_context=False):
                path = "/".join(str(p) for p in cause["loc"]) or "(root)"
                found.append((path, cause["msg"]))
    return found


class InvalidBook(ValueError):
    pass


def check(data):
    """Raise ``InvalidBook`` listing the first errors when ``data`` breaks the schema."""
    found = errors(data)
    if found:
        lines = [f"{path}: {message}" for path, message in found[:20]]
        more = f" (+{len(found) - 20} more)" if len(found) > 20 else ""
        raise InvalidBook(f"{len(found)} schema error(s){more}:\n" + "\n".join(lines))
    return data


def dumps(data):
    """The canonical serialization: sorted keys, compact, UTF-8 text."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
