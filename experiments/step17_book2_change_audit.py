"""Compare every non-OCR page with Step 16; do not mask book-wide cover side effects."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.cache_store import read_json
from step11c_identity import semantic

BOOK = "immigrant_children"
FINAL = ROOT / "experiments/out/step17/final"
LANGUAGE_FIELDS = {"language", "language_confidence", "language_runs"}


def without_unit_languages(payload):
    result = dict(payload)
    for key, field in (("units", "units"), ("table_view", "added")):
        result[key] = {**payload[key], field: [
            {k: v for k, v in unit.items() if k not in LANGUAGE_FIELDS}
            for unit in payload[key][field]]}
    return result


def main():
    old = json.loads((ROOT / f"experiments/out/step16/final/performance/{BOOK}.json")
                     .read_text("utf-8"))["run"]
    record = json.loads((FINAL / f"performance/{BOOK}.json").read_text("utf-8"))
    new = record["run"]
    ocr_pages = {int(n) for n in record["ocr"]["page_keys"]}
    old_book = semantic(read_json(Path(old["output"]) / "book.json.gz"))
    new_book = semantic(read_json(Path(new["output"]) / "book.json.gz"))
    book_changes = {}
    non_ocr_structure = {}
    for section in ("structure", "lists"):
        a, b = old_book[section], new_book[section]
        book_changes[section] = [k for k in sorted(a.keys() | b.keys()) if a.get(k) != b.get(k)]
    for key in ("headings", "styled", "rejected", "page_zones", "navigation_pages"):
        a = [r for r in old_book["structure"].get(key, []) if r["page"] not in ocr_pages]
        b = [r for r in new_book["structure"].get(key, []) if r["page"] not in ocr_pages]
        if a != b:
            non_ocr_structure[key] = {"before_records": len(a), "after_records": len(b)}
    old_headings = {r["id"]: r for r in old_book["structure"]["headings"]
                    if r["page"] not in ocr_pages}
    new_headings = {r["id"]: r for r in new_book["structure"]["headings"]
                    if r["page"] not in ocr_pages}
    heading_changes = [{"id": key, "page": old_headings[key]["page"],
                        "fields": {field: [old_headings[key].get(field),
                                            new_headings[key].get(field)]
                                   for field in sorted(old_headings[key].keys()
                                                       | new_headings[key].keys())
                                   if old_headings[key].get(field) != new_headings[key].get(field)}}
                       for key in sorted(old_headings.keys() & new_headings.keys())
                       if old_headings[key] != new_headings[key]]
    cover_titles = [r for r in new_book["structure"]["headings"]
                    if r["page"] in ocr_pages and r.get("role") == "book_title"]
    heading_changes_explained = (
        old_headings.keys() == new_headings.keys()
        and all(set(row["fields"]) <= {"role", "reasons"}
                and row["fields"].get("role") == ["book_title", "front_section_title"]
                and any(title["page"] < row["page"] for title in cover_titles)
                for row in heading_changes)
        and set(non_ocr_structure) <= {"headings"})
    differences = []
    fields = Counter()
    unexpected, language_pairs = [], Counter()
    for number in range(1, new["pages"] + 1):
        name = f"page_{number:06d}.json.gz"
        before = semantic(read_json(Path(old["output"]) / name))
        after = semantic(read_json(Path(new["output"]) / name))
        changed = [k for k in sorted(before.keys() | after.keys())
                   if before.get(k) != after.get(k)]
        if changed:
            differences.append({"page": number, "ocr_page": number in ocr_pages,
                                "fields": changed})
            fields.update(changed)
            if number not in ocr_pages:
                if without_unit_languages(before) != without_unit_languages(after):
                    unexpected.append({"page": number, "fields": changed})
                old_units = {u["id"]: u for u in before["units"]["units"]}
                for unit in after["units"]["units"]:
                    prior = old_units.get(unit["id"], {})
                    a, b = prior.get("language"), unit.get("language")
                    if a != b:
                        language_pairs[f"{a} -> {b}"] += 1
        if number % 50 == 0:
            print("book2 audit", number, flush=True)
    result = {"pages": new["pages"], "ocr_pages": sorted(ocr_pages),
              "method": "Exact semantic payload comparison; only cache_key_inputs/page_keys omitted",
              "changed_fields": dict(fields), "changed_pages": differences,
              "non_ocr_page_changes": [r for r in differences if not r["ocr_page"]],
              "unexpected_non_ocr_page_changes": unexpected,
              "book_level_changed_fields": book_changes,
              "non_ocr_structure_record_changes": non_ocr_structure,
              "non_ocr_heading_changes": heading_changes,
              "non_ocr_heading_changes_explained": heading_changes_explained,
              "cover_structure_explanation": (
                  "The new OCR cover title takes book_title; the prior title-page heading becomes "
                  "front_section_title. The cover section gains that OCR heading ID. Body-style "
                  "letter totals, style-group and profile counts include the added OCR candidate. "
                  "Body style, zones, existing heading IDs/levels and all other native heading "
                  "fields remain unchanged."),
              "non_ocr_language_label_changes": dict(language_pairs),
              "language_change_cause": {
                  "before_candidates": ["spa", "eng"], "after_candidates": ["eng"],
                  "evidence": "step17_ocr_cover.ocr_settings passes eng; paragraphs/cache.py constructs Lingua with Settings.ocr_languages",
                  "scope": "Only language/language_confidence/language_runs on original or table-added units may differ"}}
    (FINAL / "book2_change_audit.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in {"changed_pages", "non_ocr_page_changes"}}), flush=True)
    if unexpected or not heading_changes_explained:
        raise SystemExit("Unexpected non-OCR changes; do not accept the identity gate")


if __name__ == "__main__":
    main()
