"""Step 17 source, ledger and final-archive gates: the Step 15 gates on the Step 17 runs.

Unchanged checks (``step15_source_gates``): 30 sample pages 0 missing / 0 extra against a
fresh native extraction, book 1 ledger 495,751, manifests and images, every line owned once,
continuity links consistent.

Book 2 has an OCR cover and an English-only job language configuration. The separate
exact archive audit must prove every non-OCR field is unchanged except the three unit
language-annotation fields. The source gate records those narrowly permitted list-digest
changes and the OCR-page exception, and still requires unchanged native source text.

Usage: python step17_source_gates.py
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.cache_store import read_json
from book_core.lists.models import PageLists

import step15_source_gates as s15
from step11c_identity import digest

FINAL = ROOT / "experiments/out/step17/final"
BEFORE = ROOT / "experiments/out/step17/before"
BASELINE = FINAL / "source_baseline"
BOOK2 = "immigrant_children"


def prepare_book2():
    record = json.loads((FINAL / "performance" / f"{BOOK2}.json").read_text("utf-8"))
    ocr_pages = sorted(int(p) for p in record["ocr"]["page_keys"])
    root = Path(record["run"]["output"])
    identity = json.loads((BEFORE / f"{BOOK2}.json").read_text("utf-8"))
    archive = read_json(root / "book.json.gz")
    audit = json.loads((FINAL / "book2_change_audit.json").read_text("utf-8"))
    assert not audit["unexpected_non_ocr_page_changes"], "unexplained non-OCR page changes"
    assert audit["non_ocr_heading_changes_explained"], "unexplained native heading changes"
    language_pages = [r["page"] for r in audit["non_ocr_page_changes"]]
    exemptions = {"ocr_pages": ocr_pages, "pages": {}, "books": {},
                  "language_annotation_pages": language_pages,
                  "language_change_cause": audit["language_change_cause"],
                  "identity_scope": ["native_text", "lists", "books.structure", "books.lists"],
                  "other_identity_fields": "Retained Step 16 references, not a fresh Step 17 capture"}
    for number in sorted(set(ocr_pages) | set(language_pages)):
        payload = read_json(root / f"page_{number:06d}.json.gz")
        units = s15.ListsView.model_validate(payload["units"])
        new = {
            "native_text": digest(payload["source"]),
            "lists": digest(PageLists.model_validate(units).model_dump(mode="json")),
        }
        old = identity["pages"][str(number)]
        exemptions["pages"][str(number)] = {k: old.get(k) != v for k, v in new.items()}
        if number not in ocr_pages:
            assert old["native_text"] == new["native_text"], "native text changed"
        identity["pages"][str(number)] = {**old, **new}
    for name in ("structure", "lists"):
        new = digest(archive[name])
        exemptions["books"][name] = identity["books"][name] != new
        identity["books"][name] = new
    (FINAL / "after").mkdir(parents=True, exist_ok=True)
    (FINAL / "after" / f"{BOOK2}.json").write_text(json.dumps(identity, indent=1) + "\n",
                                                    "utf-8", newline="\n")  # fmt: skip
    BASELINE.mkdir(parents=True, exist_ok=True)
    for path in BEFORE.glob("*.json"):
        shutil.copyfile(path, BASELINE / path.name)
    (BASELINE / f"{BOOK2}.json").write_text(json.dumps(identity, indent=1) + "\n", "utf-8",
                                            newline="\n")  # fmt: skip
    (FINAL / "book2_identity_exemptions.json").write_text(
        json.dumps(exemptions, indent=1) + "\n", "utf-8", newline="\n"
    )
    print("book 2 exemptions", {"ocr_pages": ocr_pages,
                               "language_annotation_pages": len(language_pages),
                               "books": exemptions["books"]})


if __name__ == "__main__":
    s15.gates.RUN = FINAL
    s15.gates.BASELINE = BASELINE
    s15._load(BOOK2)
    prepare_book2()
    for name in ("spanish_us_history", BOOK2, "art_therapy_index", "medical_anatomy",
                 "statistics"):  # fmt: skip
        s15._load(name)
    import step17_archive_gates

    step17_archive_gates.main()
