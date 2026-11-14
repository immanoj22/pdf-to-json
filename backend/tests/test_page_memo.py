"""Per-page memo of the book stages: values come back exactly, keys bind the producer and the
inputs, and a damaged entry is refused, never used."""

import json

import pytest

from book_core.page_memo import PageMemo, digest, jsonable
from book_core.model.common import BBox


def test_values_come_back_exactly(tmp_path):
    memo = PageMemo(tmp_path, "figures", "producer-1", "settings")
    key = memo.key("measure", 7, digest([BBox(x0=1, y0=2, x1=3, y1=4), ["a", "b"]]))
    assert memo.get(key) is None
    value = {"kind": "photo", "confidence": 0.8125, "edges": {"shape": [2, 2, 3], "data": [0] * 12}}
    memo.put(key, value)
    assert memo.get(key) == value and memo.stats() == {"hits": 1, "misses": 1}
    memo.write_bytes(key, b"\x89PNG")
    assert memo.read_bytes(key) == b"\x89PNG"


def test_keys_bind_the_producer_and_the_inputs(tmp_path):
    a = PageMemo(tmp_path, "tables", "producer-1", "layout-key")
    b = PageMemo(tmp_path, "tables", "producer-2", "layout-key")  # other code: other entries
    c = PageMemo(tmp_path, "tables", "producer-1", "other-layout")
    assert len({a.key(3, "units"), b.key(3, "units"), c.key(3, "units")}) == 3
    assert a.key(3, "units") != a.key(4, "units") != a.key(3, "other units")
    # model and dict give the same digest; key order does not matter
    box = BBox(x0=1, y0=2, x1=3, y1=4)
    assert digest(box) == digest(jsonable(box)) == digest(dict(reversed(list(jsonable(box).items()))))


def test_a_damaged_entry_is_refused(tmp_path):
    memo = PageMemo(tmp_path, "equations", "producer-1")
    key = memo.key("page", 1)
    memo.put(key, {"vector_glyphs": 3})
    path = next((tmp_path / "page_memo" / "equations").rglob("*.json"))
    import gzip

    raw = gzip.decompress(path.read_bytes())
    path.write_bytes(gzip.compress(raw.replace(b'"vector_glyphs":3', b'"vector_glyphs":4')))
    with pytest.raises(ValueError, match="checksum"):
        memo.get(key)
    entry = json.loads(raw)
    entry["key"] = "0" * 64
    path.write_bytes(gzip.compress(json.dumps(entry).encode()))
    with pytest.raises(ValueError, match="Corrupt"):
        memo.get(key)
