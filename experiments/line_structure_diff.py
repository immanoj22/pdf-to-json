"""Layout lines of a PDF with and without the script-baseline limit (read-only).

Usage: python line_structure_diff.py NAME PDF OUT_JSON
Builds the page lines of every page twice from the same native evidence: with the current
layout.lines.SCRIPT_REACH and with it unlimited (the behaviour before the fix), and lists the
pages whose lines differ."""
import json
import sys
from pathlib import Path

import pymupdf

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.layout import lines as L

name, pdf, out = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
ex = PyMuPDFExtractor()
n_pages = len(pymupdf.open(pdf))
NEW = L.SCRIPT_REACH


def signature(native):
    store = native.page.store
    lines = L.build_lines(native)
    return sorted(tuple(line.span_ids) for line in lines), store


changed, total_old, total_diff = [], 0, 0
for n in range(1, n_pages + 1):
    native = ex.extract_object_page(pdf, n)
    L.SCRIPT_REACH = NEW
    new, store = signature(native)
    L.SCRIPT_REACH = float("inf")
    old, _ = signature(native)
    total_old += len(old)
    if old != new:
        gone = [s for s in old if s not in set(new)]
        total_diff += len(gone)
        text = lambda ids: "".join(store.spans[i].raw_text for i in ids)[:110]  # noqa: E731
        changed.append({"page": n, "old_lines_changed": len(gone), "new_lines": len([s for s in new if s not in set(old)]),
                        "examples": [text(s) for s in gone[:2]]})
    if n % 50 == 0:
        print(name, n, n_pages, flush=True)
json.dump({"book": name, "pages": n_pages, "lines": total_old, "pages_changed": len(changed),
           "lines_changed": total_diff, "changes": changed}, open(out, "w"), ensure_ascii=False, indent=1)
print(name, "done", len(changed), total_diff)
