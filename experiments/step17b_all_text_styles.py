"""Complete the styling population with furniture; preserve the original cohort.

Only audit evidence is written. The same seed/order is retained, so the five cells
without furniture keep their original samples. Three cells receive fresh samples.
"""
import copy
import json
import random
import sys
from collections import Counter
from pathlib import Path

from step17b_investigate import CELLS, OUT, ROOT, SEED, populations, sheets, walk, write


def signature(row):
    return (row["unit"], row["page"], row["kind"], row["start"], row["end"], row["text"])


def source_box(row, book):
    """Locate repeated/absent frozen boxes through the actual source references."""
    from book_core.assembly.build import sid
    from book_core.assembly.text import build_text, ordered_spans
    from book_core.cache_store import read_json
    from book_core.model.spans import ExtractedPage

    payload = read_json(Path(book["archive"]) / f"page_{row['page']:06d}.json.gz")
    page = ExtractedPage.model_validate(payload["source"])
    spans = ordered_spans(page.store)
    line_of = {sid(k): k for k in payload["line_spans"]}
    span_of = {sid(k): k for k in spans}
    pieces = [(line_of[k], [(s, None, None) for s in payload["line_spans"][line_of[k]]])
              for k in row["refs"]["lines"]]
    pieces += [(spans[span_of[r["span"]]].line_id,
                [(span_of[r["span"]], r["start"], r["end"])]) for r in row["refs"]["spans"]]
    built = build_text(pieces, spans)
    if built.content.text == row["unit_text"]:
        boxes = [s.span.bbox for s in built.segments
                 if s.start < row["end"] and s.end > row["start"]]
        row["box"] = [min(b.x0 for b in boxes), min(b.y0 for b in boxes),
                      max(b.x1 for b in boxes), max(b.y1 for b in boxes)]
        row["box_method"] = "exact source-reference character range"
    else:
        # Keep the actual source owner's crop, never a repeated word elsewhere.
        boxes = row["owner_boxes"]
        assert boxes
        row["box"] = [min(b["x0"] for b in boxes), min(b["y0"] for b in boxes),
                      max(b["x1"] for b in boxes), max(b["y1"] for b in boxes)]
        row["box_method"] = "owner box; manual target disambiguation required"
        row["source_text_differs"] = True


def all_pools(book, data):
    wrapped = {"content": [*data["content"], *[
        {**node, "type": "furniture", "pages": [node["page"]]} for node in data["furniture"]]]}
    pools, _ = populations(book, wrapped)
    for values in pools.values():
        for row in values:
            if row["node_type"] == "furniture" and "furniture" not in row["context"]:
                row["context"].append("furniture")
    return pools


def sample():
    import pymupdf
    from reference_paths import reference_path

    inputs = json.loads((OUT / "inputs.json").read_text("utf-8"))
    old_samples = json.loads((OUT / "style_verdicts.json").read_text("utf-8"))
    indexes = json.loads((OUT / "index_sample.json").read_text("utf-8"))
    corrections = {r["sample_id"]: r for r in json.loads(
        (OUT / "target_disambiguation.json").read_text("utf-8"))}
    results, cells, before_after = [], {}, {}
    for book, source in inputs.items():
        before = json.loads(Path(source["json"]).read_text("utf-8"))
        run = json.loads((OUT / f"final/performance/{book}.json").read_text("utf-8"))["run"]
        after = json.loads((Path(run["book_json"]) / "book.json").read_text("utf-8"))
        assert before["furniture"] == after["furniture"], book
        pools, new_pools = all_pools(book, before), all_pools(book, after)
        before_after[book] = {"before": {k: len(v) for k, v in pools.items()},
                              "after": {k: len(v) for k, v in new_pools.items()},
                              "all_furniture_fields_identical": True}
        with pymupdf.open(reference_path(source["pdf_key"])) as pdf:
            for kind in CELLS.get(book, ()):
                key = book + "-" + kind
                pool = pools[kind]
                furniture = sum("furniture" in r["context"] for r in pool)
                picked = copy.deepcopy(random.Random(f"{SEED}:{key}").sample(pool, 20))
                contexts = Counter(t for r in pool for t in r["context"])
                old = [r for r in old_samples if r["sample_id"].startswith(key + "-")]
                assert len(old) == 20
                if furniture == 0:
                    assert list(map(signature, picked)) == list(map(signature, old)), key
                    picked = copy.deepcopy(old)
                    for row in picked:
                        if row["sample_id"] in corrections:
                            correction = corrections[row["sample_id"]]
                            row["box"] = correction["chosen_box"]
                            row["crop"] = (OUT / correction["crop"]).relative_to(ROOT).as_posix()
                        row["review_source"] = "unchanged original visual cohort"
                else:
                    for row in picked:
                        source_box(row, source)
                        row["review_source"] = "new full-population visual review required"
                    sheets(picked, pdf, "all_text-" + key)
                for row in picked:
                    row["cell"] = key
                results.extend(picked)
                cells[key] = {"detected_spans": len(pool), "content_spans": len(pool) - furniture,
                              "furniture_spans": furniture, "contexts_overlap": dict(contexts),
                              "on_index_pages": sum(r["page"] in indexes[book]["index_pages"] for r in pool),
                              "new_cohort": furniture > 0,
                              "sampled_furniture": sum("furniture" in r["context"] for r in picked)}
                print(key, cells[key], flush=True)
    assert len(results) == 160
    write(OUT / "all_text_style_sample.json", {"seed": SEED, "rows": results,
          "population_order": "published content traversal followed by furniture array",
          "original_content_cohort_preserved": "style_sample.json / style_verdicts.json"})
    write(OUT / "all_text_style_census.json", {"seed": SEED, "cells": cells,
          "all_kind_before_after": before_after,
          "furniture_tag_is_analytical": True})


def finalize():
    sample_data = json.loads((OUT / "all_text_style_sample.json").read_text("utf-8"))
    decisions = json.loads((OUT / "all_text_added_verdicts.json").read_text("utf-8"))
    rows = sample_data["rows"]
    added = {r["sample_id"] for r in rows if r["review_source"].startswith("new")}
    assert set(decisions) == added and len(added) == 60
    for row in rows:
        if row["sample_id"] in added:
            decision = decisions[row["sample_id"]]
            row.update(decision)
        assert row["verdict"] in {"correct", "wrong", "unclear"}
        assert row["verdict"] != "wrong" or row.get("cause") or row.get("note")
    counts, coverage = {}, []
    for book in CELLS:
        run = json.loads((OUT / f"final/performance/{book}.json").read_text("utf-8"))["run"]
        data = json.loads((Path(run["book_json"]) / "book.json").read_text("utf-8"))
        nodes = [n for top in data["content"] for n, *_ in walk(top)]
        nodes += [{**n, "type": "furniture"} for n in data["furniture"]]
        for row in [r for r in rows if r["book"] == book]:
            candidates = [n for n in nodes if n.get("id") == row["unit"]] if row["unit"] else [
                n for n in nodes if n.get("refs") == row["refs"]
                and n.get("type") == row["node_type"]
                and n.get("content", {}).get("text") == row["unit_text"]]
            assert len(candidates) == 1, row["sample_id"]
            content = candidates[0]["content"]
            assert content["text"] == row["unit_text"]
            covered = set()
            for span in content["spans"]:
                kinds = ("bold", "italic") if span["kind"] == "bold_italic" else (span["kind"],)
                if span["kind"] == row["kind"] or row["kind"] in kinds:
                    covered.update(range(max(span["start"], row["start"]), min(span["end"], row["end"])))
            if row["verdict"] == "correct":
                assert len(covered) == row["end"] - row["start"]
            coverage.append({"sample_id": row["sample_id"], "verdict": row["verdict"],
                             "covered_characters": len(covered),
                             "sample_characters": row["end"] - row["start"]})
    for cell in {r["cell"] for r in rows}:
        selected = [r for r in rows if r["cell"] == cell]
        assert len(selected) == 20
        counts[cell] = dict(Counter(r["verdict"] for r in selected))
    summary = {"targets": len(rows), "new_visually_reviewed_targets": len(added),
               "overall": dict(Counter(r["verdict"] for r in rows)), "cells": counts,
               "single_reviewer": True, "all_correct_samples_retained_in_full": True}
    write(OUT / "all_text_style_verdicts.json", rows)
    write(OUT / "all_text_hand_check_summary.json", summary)
    write(OUT / "final/all_text_sample_after.json", coverage)
    print(summary, flush=True)


if __name__ == "__main__":
    {"sample": sample, "finalize": finalize}[sys.argv[1]]()
