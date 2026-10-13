# ruff: noqa: E402
"""Read-only diagnostic totals from frozen Step 11c final source stores."""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step11c_identity import BOOKS

from book_core.cache_store import read_json
from book_core.model.spans import ExtractedPage

OUT = ROOT / "experiments/out/step11d/diagnosis"
OUT.mkdir(exist_ok=True)
summary = {}
for book in BOOKS:
    archive = json.loads((ROOT / f"experiments/out/step11c/archive/{book}.json").read_text("utf8"))
    hidden = json.loads((ROOT / f".cache/step11d/hidden_{book}.json").read_text("utf8"))
    raw_scan_totals = hidden["totals"]
    suspect = {r["page"]: r for r in hidden["pages"]}
    characters = Counter()
    candidate = Counter()
    retained = Counter()
    excluded = Counter()
    invisible = Counter()
    beta_witnesses = []
    for path in sorted(Path(archive["output"]).glob("page_*.json.gz")):
        payload = read_json(path)
        page = ExtractedPage.model_validate(payload["source"])
        keep = {
            line.id: page.geometry.content_bbox.contains_center(line.bbox)
            for line in page.store.lines
        }
        characters.update("".join(s.raw_text for s in page.store.spans.values()))
        # A witnessed font program is selected for diagnosis, never for a repair rule.
        for s in page.store.spans.values():
            if s.font == "SymbolItalic" and s.raw_text == "b":
                beta_witnesses.append(
                    {
                        "page": page.geometry.page,
                        "span_id": s.id,
                        "source_line_id": s.line_id,
                        "raw_text": s.raw_text,
                        "inside_trimbox": keep[s.line_id],
                    }
                )
        row = suspect[page.geometry.page]
        for line in row["lines"]:
            # The exploratory scanner's all(blank-or-hidden) condition is vacuous
            # for whitespace-only lines. Such a line has no glyphs to certify.
            if line["status"] == "hidden" and not line["text"].strip():
                line["raw_scan_status"] = "hidden"
                line["status"] = "whitespace_only_candidate"
            line["inside_trimbox"] = keep[line["line_id"]]
            dest = retained if line["inside_trimbox"] else excluded
            for counts in (candidate, dest):
                counts[line["status"] + "_lines"] += 1
                counts[line["status"] + "_tokens"] += line["tokens"]
        for unit in payload["units"]["units"]:
            if unit["kind"] == "invisible":
                invisible["units"] += 1
                invisible["visual_lines"] += len(unit["line_ids"])
    assert sum(v for k, v in candidate.items() if k.endswith("_lines")) == sum(
        v for k, v in raw_scan_totals.items() if k.endswith("_lines")
    )
    hidden["raw_scan_totals"] = raw_scan_totals
    hidden["totals"] = dict(candidate)
    hidden["interpretation"] = (
        "Diagnostic candidates only; no visibility decisions applied. "
        "Not an exhaustive census or a production proof."
    )
    hidden["retained_candidate_totals"] = dict(retained)
    hidden["trimbox_excluded_candidate_totals"] = dict(excluded)
    (OUT / f"hidden_{book}.json").write_text(
        json.dumps(hidden, indent=2, ensure_ascii=False) + "\n", "utf8"
    )
    summary[book] = {
        "pages": len(suspect),
        "source_character_counts": {
            f"U+{cp:04X}": characters[chr(cp)] for cp in (0x03B2, 0x01CA, 0x00BE, 0x25C6, 0x2022)
        },
        "beta_shaped_b_witnesses": beta_witnesses,
        "hidden_candidate_totals": dict(candidate),
        "retained_candidate_totals": dict(retained),
        "trimbox_excluded_candidate_totals": dict(excluded),
        "existing_invisible_units": dict(invisible),
    }
    print(book, summary[book], flush=True)
(OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", "utf8")
