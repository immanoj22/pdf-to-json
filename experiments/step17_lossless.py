"""Step 17 Part 7: lossless check of a book JSON against the ledger of its final archive.

The ledger side is read from the archive's span stores: retained tokens (lines whose centre
lies in the content frame, as ``step4b_run.retained_counter``) and the TrimBox discards. The
JSON side is rebuilt from the JSON alone (``assembly.lossless``).

Usage: python step17_lossless.py --json PATH --archive DIR [--out PATH]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

from book_core.assembly.lossless import compare
from book_core.cache_store import read_json
from book_core.ledger.tokenization import token_counter
from book_core.model.spans import ExtractedPage


def ledger(archive):
    manifest = read_json(Path(archive) / "manifest.json.gz")
    retained, discarded = Counter(), Counter()
    for number in range(1, manifest["pages"] + 1):
        page = ExtractedPage.model_validate(
            read_json(Path(archive) / f"page_{number:06d}.json.gz")["source"]
        )
        for line in page.store.lines:
            tokens = token_counter(page.store.raw_line_text(line))
            if page.geometry.content_bbox.contains_center(line.bbox):
                retained.update(tokens)
            else:
                discarded.update(tokens)
    return retained, discarded


def check(json_path, archive):
    book = json.loads(Path(json_path).read_text("utf-8"))
    retained, discarded = ledger(archive)
    return compare(book, retained, discarded)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    result = check(args.json, args.archive)
    text = json.dumps(result, indent=1, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n", "utf-8", newline="\n")
    print(text)
    sys.exit(1 if any(result.get(k, 0) for k in (
        "missing", "extra", "discard_missing", "discard_extra")) else 0)
