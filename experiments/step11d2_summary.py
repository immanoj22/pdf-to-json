"""Independent ledger/reference context for the four-book opaque-cover diagnosis."""

# ruff: noqa: E402
import hashlib
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step11d2_hidden import OUT, write

from book_core.cache_store import read_json
from book_core.ledger.tokenization import line_tokens
from book_core.model.spans import ExtractedPage
from book_core.reference.xml_reader import load_tree

REFERENCES = {
    "spanish_us_history": "spanish_xml",
    "immigrant_children": "immigrant_xml",
    "art_therapy_index": "art_index_xml",
    "medical_anatomy": "medical_xml",
}


def read(path):
    return json.loads(path.read_text("utf8"))


def search_text(raw):
    text = unicodedata.normalize("NFKC", raw)
    return " ".join("".join(" " if unicodedata.category(c) == "Cc" else c for c in text).split())


def main():
    books = {}
    for book, refkey in REFERENCES.items():
        validation = read(OUT / f"{book}_validated.json")
        screen = read(OUT / f"{book}_all.json")
        data = reference_path(refkey).read_bytes()
        tree, repairs = load_tree(data)
        reference = search_text(" ".join(tree.itertext()))
        archive = Path(
            read(OUT.parent.parent / f"step11e/performance/{book}.json")["run"]["output"]
        )
        earlier = read(OUT.parent.parent / f"step11d/diagnosis/hidden_{book}.json")
        old_excluded = {
            r["line_id"]
            for p in earlier["pages"]
            for r in p["lines"]
            if r["status"] == "hidden" and not r["inside_trimbox"]
        }
        counts, rows = Counter(), []
        for row in validation["pages"]:
            number = row["page"]
            if not row["candidates"]:
                continue
            page = ExtractedPage.model_validate(
                read_json(archive / f"page_{number:06d}.json.gz")["source"]
            )
            assert page.source_sha256 == validation["source_sha256"]
            ids = {r["span_id"] for r in row["candidates"]}
            confirmed = {
                r["span_id"] for r in row["candidates"] if r["render_test"].get("no_pixel_change")
            }
            reference_rows, ledger_rows = [], []
            for line in page.store.lines:
                members = set(line.span_ids)
                if not members & ids:
                    continue
                retained = page.geometry.content_bbox.contains_center(line.bbox)
                tokens = list(line_tokens(page.store, line))
                fully = [t for t in tokens if set(t.span_ids) <= confirmed]
                affected = [t for t in tokens if set(t.span_ids) & confirmed]
                counts["confirmed_retained_tokens" if retained else "confirmed_trimbox_tokens"] += (
                    len(fully)
                )
                counts["partially_affected_tokens"] += len(affected) - len(fully)
                counts["candidate_retained_lines" if retained else "candidate_trimbox_lines"] += 1
                if line.id in old_excluded:
                    counts["old_170_line_group_overlap"] += 1
                    counts["old_476_token_group_overlap"] += len(tokens)
                ledger_rows.append(
                    {
                        "line_id": line.id,
                        "retained": retained,
                        "fully_hidden_token_ids": [t.id for t in fully],
                        "partially_hidden_token_ids": [t.id for t in affected if t not in fully],
                        "previous_hidden_trimbox_group": line.id in old_excluded,
                    }
                )
            for candidate in row["candidates"]:
                span = page.store.spans[candidate["span_id"]]
                assert span.raw_text == candidate["text"]
                phrase = search_text(span.raw_text)
                present = bool(phrase) and phrase in reference
                counts[
                    "candidate_span_phrase_present" if present else "candidate_span_phrase_absent"
                ] += 1
                reference_rows.append(
                    {
                        "span_id": span.id,
                        "search": phrase,
                        "substring_present": present,
                        "confirmed": span.id in confirmed,
                    }
                )
            rows.append({"page": number, "ledger": ledger_rows, "reference": reference_rows})
        books[book] = {
            "summary": validation["summary"],
            "ledger_counts": dict(counts),
            "unsupported_cover_observations": sum(
                not r["screen_candidate"] for p in screen["pages"] for r in p["candidate_spans"]
            ),
            "reference_sha256": hashlib.sha256(data).hexdigest(),
            "reference_in_memory_repairs": [{"kind": r.kind, "detail": r.detail} for r in repairs],
            "pages": rows,
        }
    failed = any(
        b["summary"]["render_rejected_candidates"]
        or b["summary"]["visible_control_false_positives"]
        for b in books.values()
    )
    write(
        OUT.parent / "diagnosis.json",
        {
            "books": books,
            "false_positive_gate": "FAIL" if failed else "PASS",
            "reference_limit": "Substring presence in the complete read-only reference, not a "
            "source-occurrence alignment or a correctness label. Short phrases "
            "can appear in unrelated reference locations.",
            "token_method": "Distinct ledger token IDs; full hiding requires all owner spans to be "
            "confirmed. Existing TrimBox exclusions are counted separately.",
        },
    )
    print("false-positive gate", "FAIL" if failed else "PASS", flush=True)


if __name__ == "__main__":
    main()
