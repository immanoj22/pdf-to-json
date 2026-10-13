"""Render every opaque-cover candidate and deterministic visible controls; read-only PDFs."""

# ruff: noqa: E402
import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step7_layouts import BOOKS
from step11d2_hidden import OUT, AuditExtractor, compare_render, unsupported, write
from step11d2_hidden import candidates as screen_candidates

from book_core.run_context import open_source, source_session


def read(path):
    return json.loads(path.read_text("utf8"))


def validate(book):
    screen_path = OUT / f"{book}_all.json"
    screen = read(screen_path)
    inputs = {
        "screen_sha256": hashlib.sha256(screen_path.read_bytes()).hexdigest(),
        "producer": {
            name: hashlib.sha256((ROOT / "experiments" / name).read_bytes()).hexdigest()
            for name in ("step11d2_validate.py", "step11d2_hidden.py", "step11d2_device.py")
        },
        "control_target": 320,
        "control_pages": 16,
        "scales": [2, 4],
    }
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    chosen = sorted(
        screen["pages"],
        key=lambda r: hashlib.sha256(f"{screen['source_sha256']}:{r['page']}".encode()).hexdigest(),
    )[:16]
    sample_pages = {r["page"] for r in chosen}
    per_page = math.ceil(320 / len(chosen))
    rows = []
    source_path = reference_path(BOOKS[book][0])
    with source_session(source_path) as snapshot, open_source(source_path) as document:
        assert snapshot.digest == screen["source_sha256"]
        extractor = AuditExtractor("cpu")
        for observation in screen["pages"]:
            number = observation["page"]
            candidates = [r for r in observation["candidate_spans"] if r["screen_candidate"]]
            if not candidates and number not in sample_pages:
                continue
            checkpoint = ROOT / ".cache/step11d2/validation" / key / f"{number}.json"
            if checkpoint.exists():
                row = read(checkpoint)
                assert row["cache_inputs"] == inputs
                rows.append(row)
                continue
            page = document[number - 1]
            native, events, matches, attribution = extractor.page_evidence(page, snapshot.digest)
            assert attribution == observation["attribution"]
            actual = json.loads(json.dumps(screen_candidates(native, matches, events)))
            assert actual == observation["candidate_spans"]
            controls = []
            if number in sample_pages:
                eligible = [
                    sid
                    for sid, pairs in matches.items()
                    if native.store.spans[sid].raw_text.strip()
                    and all(
                        e["kind"] == "fill_text"
                        and not unsupported(e["state"])
                        and e["alpha"] is not None
                        and e["alpha"] > 0
                        for e, _ in pairs
                    )
                    and any(
                        g["bbox"] is not None
                        and g["bbox"][0] < g["bbox"][2]
                        and g["bbox"][1] < g["bbox"][3]
                        for _, g in pairs
                    )
                ]
                controls = sorted(
                    eligible, key=lambda sid: hashlib.sha256(sid.encode()).hexdigest()
                )[:per_page]
            baselines, tested = {}, {}
            for sid in dict.fromkeys([r["span_id"] for r in candidates] + controls):
                tested[sid] = compare_render(page, matches[sid], baselines=baselines)
            row = {
                "cache_inputs": inputs,
                "page": number,
                "candidates": [{**r, "render_test": tested[r["span_id"]]} for r in candidates],
                "controls": [
                    {
                        "span_id": sid,
                        "text": native.store.spans[sid].raw_text,
                        "screen_candidate": sid in {r["span_id"] for r in candidates},
                        "render_test": tested[sid],
                    }
                    for sid in controls
                ],
            }
            write(checkpoint, row)
            rows.append(row)
            counts = Counter(
                "zero_pixels" if r["no_pixel_change"] else "visible"
                for r in tested.values()
                if r["valid"]
            )
            print(
                book,
                number,
                "candidates",
                len(candidates),
                "controls",
                len(controls),
                dict(counts),
                flush=True,
            )
    candidates = [c for r in rows for c in r["candidates"]]
    controls = [c for r in rows for c in r["controls"]]
    visible = [
        c for c in controls if c["render_test"]["valid"] and not c["render_test"]["no_pixel_change"]
    ]
    confirmed = [
        c for c in candidates if c["render_test"]["valid"] and c["render_test"]["no_pixel_change"]
    ]
    rejected = [
        c
        for c in candidates
        if c["render_test"]["valid"] and not c["render_test"]["no_pixel_change"]
    ]
    result = {
        "book": book,
        "source_sha256": screen["source_sha256"],
        "cache_inputs": inputs,
        "control_sample_pages": sorted(sample_pages),
        "pages": rows,
        "summary": {
            "candidate_spans": len(candidates),
            "candidate_tokens": sum(c["tokens"] for c in candidates),
            "render_confirmed_spans": len(confirmed),
            "render_confirmed_tokens": sum(c["tokens"] for c in confirmed),
            "trimbox_already_excluded_spans": sum(c["trimbox_excluded"] for c in confirmed),
            "trimbox_already_excluded_tokens": sum(
                c["tokens"] for c in confirmed if c["trimbox_excluded"]
            ),
            "render_rejected_candidates": len(rejected),
            "invalid_render_candidates": sum(not c["render_test"]["valid"] for c in candidates),
            "sampled_controls": len(controls),
            "independently_visible_controls": len(visible),
            "visible_control_false_positives": sum(c["screen_candidate"] for c in visible),
        },
    }
    write(OUT / f"{book}_validated.json", result)
    print(json.dumps(result["summary"]), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", required=True, choices=BOOKS)
    validate(parser.parse_args().book)
