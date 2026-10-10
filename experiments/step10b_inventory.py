"""Step 10b Part A: inventory of hold-out book 4 (counts only; no page, heading or layout
inspection for tuning).

PDF: page count, page sizes, digital vs scanned vs blank pages (native text characters and
image coverage per page), PDF page labels and outline entries. XML: root element, detected
dialect, in-memory repairs, page markers and their label series, neutral unit kinds. The
files are only read.

Usage: python step10b_inventory.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from reference_paths import reference_path  # noqa: E402
from step5_run import BOOKS, DIALECTS  # noqa: E402

BOOK = "medical_anatomy"
OUT = ROOT / "experiments/out/step10b"


def pdf_inventory(path):
    import pymupdf

    rows = Counter()
    blank, scanned = [], []
    sizes = Counter()
    with pymupdf.open(path) as document:
        for page in document:
            chars = len(page.get_text("text").strip())
            area = page.rect.width * page.rect.height
            covered = 0.0
            for info in page.get_image_info():
                box = pymupdf.Rect(info["bbox"]) & page.rect
                covered += box.width * box.height
            sizes[(round(page.rect.width), round(page.rect.height))] += 1
            if chars >= 20:
                rows["digital"] += 1
            elif covered >= 0.5 * area:
                rows["scanned_candidate"] += 1
                scanned.append(page.number + 1)
            else:
                rows["blank_or_artwork"] += 1
                blank.append(page.number + 1)
        labels = document.get_page_labels()
        outline = document.get_toc()
        metadata = {k: document.metadata.get(k) for k in ("format", "creator", "producer")}
        count = document.page_count
    return {
        "pages": count,
        "page_sizes_pt": {f"{w}x{h}": n for (w, h), n in sizes.items()},
        "page_kinds": dict(rows),
        "blank_or_artwork_pages": blank,
        "scanned_candidate_pages": scanned,
        "pdf_page_label_rules": len(labels),
        "outline_entries": len(outline),
        "metadata": metadata,
    }


def xml_inventory(path):
    from book_core.reference.dialects import load_dialects
    from book_core.reference.xml_reader import read_reference

    data = Path(path).read_bytes()
    doc = read_reference(data, load_dialects(DIALECTS))
    kinds = Counter(doc.dialect.element_kind(u, doc.elements) for u in dict.fromkeys(doc.units))
    profiles = json.loads(Path(DIALECTS).read_text("utf-8"))
    entry = next(d for d in profiles["dialects"] if d["name"] == doc.dialect.name)
    from book_core.evaluation.derived_gold import marker_label_of

    labels = [marker_label_of(doc, m, entry.get("page_marker_label")) for m in doc.markers]
    series = Counter("front (FM)" if lab.startswith("FM") else
                     "arabic" if lab.isdigit() else "other" for lab in labels)  # fmt: skip
    return {
        "bytes": len(data),
        "root": doc.elements[0].name,
        "dialect": doc.dialect.name,
        "repairs": [r.__dict__ for r in doc.repairs],
        "tokens": len(doc.tokens),
        "page_markers": len(doc.markers),
        "marker_label_series": dict(series),
        "first_labels": labels[:3],
        "last_labels": labels[-3:],
        "units_by_kind": dict(kinds.most_common()),
        "doctype": data[:400].split(b"<!DOCTYPE", 1)[1].split(b">", 1)[0].decode().strip()
        if b"<!DOCTYPE" in data[:400]
        else None,
    }


def main():
    spec = BOOKS[BOOK]
    report = {
        "book": BOOK,
        "split": spec["split"],
        "folder": "Downloads/book4 (named by the owner)",
        "xml_package_note": "the zip holds 18 XML files: the complete book file plus its 16 "
        "chapter/front/index parts and page_info.xml; the complete book file is the reference",
        "pdf_sha256": spec["pdf_sha256"],
        "xml_sha256": spec["xml_sha256"],
        "pdf": pdf_inventory(reference_path(spec["pdf"])),
        "xml": xml_inventory(reference_path(spec["xml"])),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "book4_inventory.json").write_text(json.dumps(report, indent=1) + "\n", "utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
