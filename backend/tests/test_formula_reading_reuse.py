"""Step 21: a formula reading is keyed by its crop, the model and settings, not by the code of
the rest of the package: a schema change elsewhere must not make a book's readings run again."""

from types import SimpleNamespace

from book_core.cache_store import read_json, write_json
from book_core.mathml.recognition import RecognitionCache


def reader(identity, calls):
    def recognize(png):
        calls.append(png)
        return f"latex-{len(calls)}", False

    return SimpleNamespace(identity=identity, recognize=recognize)


def test_a_reading_made_under_another_key_is_reused_for_the_same_crop_and_model(tmp_path):
    identity = {"recognizer": "fake", "revision": "r1", "device": "cpu"}
    calls = []
    first = RecognitionCache(reader(identity, calls), tmp_path)
    assert first.read(b"crop")["cached"] is False and len(calls) == 1
    # the same crop under a key made by other code (an earlier producer digest)
    other = next(tmp_path.glob("formula_readings/*"))
    moved = other.parent / ("0" * 20)
    other.rename(moved)
    for path in moved.iterdir():
        record = read_json(path)
        record["key"] = "an-earlier-key"
        write_json(path, record)
    second = RecognitionCache(reader(identity, calls), tmp_path)
    again = second.read(b"crop")
    assert again["cached"] is True and again["latex"] == "latex-1" and len(calls) == 1
    assert again["key"] == second.key()  # now kept under the current key
    assert second.read(b"crop")["cached"] is True and len(calls) == 1


def test_another_model_or_another_crop_is_read_again(tmp_path):
    calls = []
    RecognitionCache(reader({"recognizer": "fake", "revision": "r1"}, calls), tmp_path).read(b"a")
    changed = {"recognizer": "fake", "revision": "r2"}
    other_model = RecognitionCache(reader(changed, calls), tmp_path)
    assert other_model.read(b"a")["cached"] is False
    assert other_model.read(b"b")["cached"] is False
    assert len(calls) == 3


def test_a_table_reading_made_under_another_key_is_reused(tmp_path):
    from book_core.tables.recognizers import ReadingCache

    def table_reader(identity, calls):
        def read(png):
            calls.append(png)
            return {"cells": [len(calls)]}

        return SimpleNamespace(identity=identity, read=read,
                               device=SimpleNamespace(model_dump=lambda: {}))  # fmt: skip

    identity = {"name": "fake-table", "revision": "r1", "device": "cpu"}
    calls = []
    assert ReadingCache(table_reader(identity, calls), tmp_path).read(b"crop") == {"cells": [1]}
    other = next(tmp_path.glob("table_readings/*"))
    moved = other.parent / ("0" * 20)
    other.rename(moved)
    for path in moved.iterdir():
        record = read_json(path)
        record["key"] = "an-earlier-key"
        write_json(path, record)
    again = ReadingCache(table_reader(identity, calls), tmp_path)
    assert again.read(b"crop") == {"cells": [1]} and len(calls) == 1  # reused
    changed = ReadingCache(table_reader({**identity, "revision": "r2"}, calls), tmp_path)
    assert changed.read(b"crop") == {"cells": [2]} and len(calls) == 2  # another model
