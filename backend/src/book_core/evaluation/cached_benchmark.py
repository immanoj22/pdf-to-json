"""Read-only expected text counters from cached extraction evidence, never generated output."""

import json
from collections import Counter
from pathlib import Path

from book_core.ledger.tokenization import token_counter


class CachedBenchmark:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        validation = json.loads((self.directory / "validation.json").read_text("utf-8"))
        self.exclusions = {item["source_id"] for item in validation["exclusions"]}
        manifest = json.loads((self.directory / "manifest.json").read_text("utf-8"))
        self.source_sha256 = manifest["source_hash"]

    def expected_page(self, number: int) -> Counter[str]:
        path = self.directory / "normalized" / "pages" / f"{number:06d}.json"
        page = json.loads(path.read_text("utf-8"))
        counter: Counter[str] = Counter()
        for block in page["blocks"]:
            for line in block["lines"]:
                if line["provenance"]["source_id"] not in self.exclusions:
                    counter.update(token_counter("".join(span["text"] for span in line["spans"])))
        return counter
