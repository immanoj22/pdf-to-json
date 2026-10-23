"""Bounded object views for the read-only development table parity audit.

Cache envelopes/fingerprints/payloads are verified. Every table-consumed object
field and path item is validated by its existing model. Native render glyphs and
paint commands are not table inputs. Paths are re-iterable, without retaining a
Pydantic instance for every map vertex. No production cache reader is changed.
"""
import hashlib
import json
import re
from types import SimpleNamespace

from book_core.cache_store import FORMAT_VERSION, read_json
from book_core.objects.models import CompoundVisual, PageObject, PathItem

DECODER = json.JSONDecoder()
STRUCTURE = re.compile(r'"(?:[^"\\]|\\.)*"|[{}\[\]]')


def space(text, position):
    while position < len(text) and text[position].isspace():
        position += 1
    return position


def end_value(text, start):
    start = space(text, start)
    if text[start] not in "[{":
        return DECODER.raw_decode(text, start)[1]
    stack = []
    for match in STRUCTURE.finditer(text, start):
        token = match[0]
        if token[0] == '"':
            continue
        if token in "[{":
            stack.append(token)
        else:
            assert stack and stack.pop() == {"}": "{", "]": "["}[token]
            if not stack:
                return match.end()
    raise ValueError("Truncated JSON container")


def fields(text, start=0):
    position = space(text, start)
    assert text[position] == "{"
    position = space(text, position + 1)
    while text[position] != "}":
        key, position = DECODER.raw_decode(text, position)
        assert isinstance(key, str)
        position = space(text, position)
        assert text[position] == ":"
        first = space(text, position + 1)
        last = end_value(text, first)
        yield key, first, last
        position = space(text, last)
        if text[position] == "}":
            break
        assert text[position] == ","
        position = space(text, position + 1)


def array_ranges(text, start):
    position = space(text, start)
    assert text[position] == "["
    position = space(text, position + 1)
    while text[position] != "]":
        last = end_value(text, position)
        yield position, last
        position = space(text, last)
        if text[position] == "]":
            break
        assert text[position] == ","
        position = space(text, position + 1)


class Paths:
    def __init__(self, text, start):
        self.text, self.start = text, start

    def __bool__(self):
        assert self.text[self.start] == "["
        return self.text[space(self.text, self.start + 1)] != "]"

    def __iter__(self):
        for first, last in array_ranges(self.text, self.start):
            yield PathItem.model_validate_json(self.text[first:last])

    def __len__(self):
        if not hasattr(self, "length"):
            self.length = sum(1 for _ in array_ranges(self.text, self.start))
        return self.length


def objects(text, start, model):
    for first, _ in array_ranges(text, start):
        metadata, paths = {}, None
        for key, a, b in fields(text, first):
            if key == "path_items":
                paths = Paths(text, a)
            elif key != "render_info":
                metadata[key] = DECODER.raw_decode(text, a)[0]
        validated = model.model_validate(metadata)
        values = dict(validated.__dict__)
        values["path_items"] = paths if paths is not None else ()
        yield SimpleNamespace(**values)


def checked_payload(path, fingerprint):
    entry = read_json(path)
    assert entry.get("format_version", 1) in {1, FORMAT_VERSION}
    assert entry["fingerprint"] == fingerprint
    payload = entry["payload"]
    checksum = hashlib.sha256()
    for offset in range(0, len(payload), 1024 * 1024):
        checksum.update(payload[offset:offset + 1024 * 1024].encode("utf-8"))
    assert checksum.hexdigest() == entry["sha256"]
    return payload


class TableObjects:
    """A fresh iterator for every unchanged table-evidence pass over the objects."""
    def __init__(self, native_path, native_key, analysis_path, analysis_key):
        self.native = checked_payload(native_path, native_key)
        self.analysis = checked_payload(analysis_path, analysis_key)
        self.native_fields = {k: (a, b) for k, a, b in fields(self.native)}
        self.analysis_fields = {k: (a, b) for k, a, b in fields(self.analysis)}
        key_start = self.analysis_fields["native_key"][0]
        assert DECODER.raw_decode(self.analysis, key_start)[0] == native_key

    def __iter__(self):
        yield from objects(self.native, self.native_fields["objects"][0], PageObject)
        if "compounds" in self.analysis_fields:
            yield from objects(self.analysis, self.analysis_fields["compounds"][0], CompoundVisual)
