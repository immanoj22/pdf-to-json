"""Verify the entry-level publication correction against independently checked output.

Capture the four completed development/parity proofs before the correction. After
publication, require every other JSON field to be unchanged (except producer/content
hash), and check every new item level against its original archive unit. This reuses
the expensive independent rendering proof only for inputs and output fields that have
not changed. The OCR-cover book takes the ordinary full parity path instead.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
from book_core.cache_store import read_json

FINAL = ROOT / "experiments/out/step17/final"
BOOKS = ("art_therapy_index", "medical_anatomy", "spanish_us_history", "statistics")
ITEMS = {"list_item", "index_entry", "glossary_entry", "definition_entry",
         "bibliography_entry", "contents_entry"}


def read(path):
    return json.loads(path.read_text("utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(book):
    record = read(FINAL / "performance" / f"{book}.json")["run"]
    proof = read(FINAL / "parity" / f"{book}.json")
    assert proof["assembly"]["identical"] and proof["continuity"]["identical"]
    assert not proof["tables"]["differ"]
    archive = Path(record["output"])
    publication = Path(record["book_json"]) / "book.json"
    target = FINAL / "parity_before_entry_levels" / f"{book}.json"
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        raise FileExistsError(f"Frozen proof already exists: {target}")
    target.write_text(json.dumps({
        "proof": proof, "archive": str(archive), "pages": record["pages"],
        "cache_keys": record["cache_keys"], "publication": str(publication),
        "publication_sha256": sha(publication),
        "archive_sha256": {name: sha(archive / name) for name in
                           ("book.json.gz", "manifest.json.gz")},
    }, indent=1) + "\n", "utf-8")
    print("captured", book, flush=True)


def walk(node):
    yield node
    for value in node.values():
        if isinstance(value, dict):
            yield from walk(value)
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, dict):
                    yield from walk(child)


def project(data):
    for node in walk(data):
        if node.get("type") in ITEMS:
            node.pop("level", None)
    data["metadata"]["converter"].pop("producer")
    data["metadata"].pop("content_sha256")
    return data


def verify(book):
    frozen_path = FINAL / "parity_before_entry_levels" / f"{book}.json"
    frozen = read(frozen_path)
    run = read(FINAL / "performance" / f"{book}.json")["run"]
    archive = Path(run["output"])
    assert str(archive) == frozen["archive"] and run["pages"] == frozen["pages"]
    assert all(value == run["cache_keys"].get(key) for key, value in
               frozen["cache_keys"].items() if key != "assembly_evidence")
    assert all(sha(archive / name) == value for name, value in frozen["archive_sha256"].items())
    old_path = Path(frozen["publication"])
    assert sha(old_path) == frozen["publication_sha256"]
    published = read(Path(run["book_json"]) / "book.json")
    items = [node for node in walk(published) if node.get("type") in ITEMS]
    levels = {}
    for number in range(1, run["pages"] + 1):
        payload = read_json(archive / f"page_{number:06d}.json.gz")
        for unit in payload["units"]["units"] + payload["table_view"]["added"]:
            levels[unit["id"][:16]] = unit.get("level")
    mismatches = [{"id": item["id"], "json": item.get("level"),
                   "source": levels.get(item["id"]), "source_found": item["id"] in levels}
                  for item in items if "level" not in item or item["id"] not in levels
                  or item["level"] != levels[item["id"]]]
    unchanged = project(published) == project(read(old_path))
    passed = unchanged and not mismatches
    proof = frozen["proof"]
    proof["assembly"] = {
        "identical": passed,
        "differing_sections": [] if unchanged else ["unexpected publication changes"],
        "method": "Frozen independent development parity plus exact unchanged-field and source-level checks",
        "frozen_proof_sha256": sha(frozen_path), "unchanged_fields_identical": unchanged,
        "items_checked": len(items), "level_mismatches": mismatches,
    }
    (FINAL / "parity" / f"{book}.json").write_text(json.dumps(proof, indent=1) + "\n", "utf-8")
    print(book, proof["assembly"], flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("capture", "verify"))
    parser.add_argument("--book", choices=BOOKS)
    args = parser.parse_args()
    for book in (args.book,) if args.book else BOOKS:
        (capture if args.action == "capture" else verify)(book)
