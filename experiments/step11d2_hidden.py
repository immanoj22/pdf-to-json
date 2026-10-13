"""Occurrence-attributed opaque-cover diagnosis; no converter or reference mutation."""

# ruff: noqa: E402
import argparse
import hashlib
import json
import sys
import unicodedata
from collections import Counter, defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import numpy as np
import pymupdf
from reference_paths import reference_path
from step7_layouts import BOOKS
from step11d2_device import contains, inspect_page, intersect, render

from book_core.atomic import replace_with_retry
from book_core.caching import code_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ledger.tokenization import token_counter
from book_core.model.common import Provenance
from book_core.run_context import open_source, source_session

OUT = ROOT / "experiments/out/step11d2/hidden"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", "utf8", newline="\n"
    )
    replace_with_retry(temporary, path)


def unsupported(state):
    reasons = set()
    for clip in state["clips"]:
        if clip["core"] is None:
            reasons.add(clip["kind"])
    if any(g["alpha"] != 1 or g["blendmode"] != 0 or g["knockout"] for g in state["groups"]):
        reasons.add("unsupported_group_or_blend")
    if state["layers"]:
        reasons.add("optional_content")
    if state["tiles"]:
        reasons.add("pattern_tile")
    return sorted(reasons)


def glyph_key(character, origin, font):
    return character, *origin, font


def attribute(source, raw, events):
    empty_spaces = {
        glyph_key(32, g["origin"], g["font"])
        for e in events
        for g in e.get("glyphs", [])
        if g["unicode"] == 32
        and g["bbox"] is not None
        and (g["bbox"][0] == g["bbox"][2] or g["bbox"][1] == g["bbox"][3])
    }
    controls = 0
    raw_spans = [
        s for b in raw["blocks"] if b["type"] == 0 for line in b["lines"] for s in line["spans"]
    ]
    assert len(raw_spans) == len(source.store.spans)
    raw_keys, span_keys = [], {}
    for span, record in zip(source.store.spans.values(), raw_spans, strict=True):
        assert span.raw_text == "".join(c["c"] for c in record["chars"])
        keys = []
        for c in record["chars"]:
            if len(c["c"]) != 1 or c.get("synthetic", False):
                continue
            key = glyph_key(ord(c["c"]), c["origin"], span.font)
            space = glyph_key(32, c["origin"], span.font)
            if unicodedata.category(c["c"]) == "Cc" and space in empty_spaces:
                key = space
                controls += 1
            keys.append(key)
        span_keys[span.id] = keys
        raw_keys.extend(keys)
    paints = []
    for event in events:
        for glyph in event.get("glyphs", []):
            u = glyph["unicode"]
            if u < 0:
                continue
            key = glyph_key(u, glyph["origin"], glyph["font"])
            paints.append((key, event, glyph))
    rc, pc = Counter(raw_keys), Counter(k for k, _, _ in paints)
    compatible = {k for k in rc if rc[k] == pc[k]}
    raw_sequence = [k for k in raw_keys if k in compatible]
    paint_sequence = [k for k, _, _ in paints if k in compatible]
    same_order = raw_sequence == paint_sequence
    queues = defaultdict(deque)
    for key, event, glyph in paints:
        if key in compatible and (same_order or rc[key] == 1):
            queues[key].append((event, glyph))
    matches = {}
    for sid, keys in span_keys.items():
        matched = [queues[k].popleft() if queues[k] else None for k in keys]
        if keys and all(v is not None for v in matched):
            matches[sid] = matched
    return matches, {
        "nonblank_spans": sum(bool(v) for v in span_keys.values()),
        "matched_spans": len(matches),
        "compatible_native_order_identical": same_order,
        "nonprinting_control_to_empty_space_attributions": controls,
        "attribution": (
            "exact Unicode/font/glyph-origin equality; equal multiplicities and "
            "native occurrence order, or unique occurrences"
        ),
    }


def candidates(source, matches, events):
    fills = []
    for event in events:
        if event["kind"] != "fill_path" or event.get("core") is None:
            continue
        core = event["core"]
        reasons = unsupported(event["state"])
        if event["alpha"] != 1:
            reasons.append("nonopaque_fill")
        if event["overprint"]:
            reasons.append("overprint")
        for clip in event["state"]["clips"]:
            if clip["core"] is not None:
                core = intersect(core, clip["core"])
        fills.append((event, core, sorted(set(reasons))))
    rows = []
    for sid, pairs in matches.items():
        span = source.store.spans[sid]
        if not span.raw_text.strip():
            continue
        painted = [
            (e, g)
            for e, g in pairs
            if g["bbox"] is not None and g["bbox"][0] < g["bbox"][2] and g["bbox"][1] < g["bbox"][3]
        ]
        if not painted:
            continue
        unsupported_text = sorted({reason for e, _ in pairs for reason in unsupported(e["state"])})
        if any(e["kind"] != "fill_text" or e["alpha"] is None or e["alpha"] <= 0 for e, _ in pairs):
            unsupported_text.append("not_plain_filled_text")
        covers = []
        uncertain = []
        for event, core, reasons in fills:
            if all(
                event["seqno"] > e["seqno"] and contains(core, glyph["bbox"])
                for e, glyph in painted
            ):
                witness = {
                    "seqno": event["seqno"],
                    "core": core,
                    "alpha": event["alpha"],
                    "state": event["state"],
                    "rejected_reasons": sorted(set(reasons + unsupported_text)),
                }
                (uncertain if witness["rejected_reasons"] else covers).append(witness)
        if not covers and not uncertain:
            continue
        line = next(line for line in source.store.lines if line.id == span.line_id)
        content = source.geometry.content_bbox
        excluded = not (
            content.x0 <= (line.bbox.x0 + line.bbox.x1) / 2 <= content.x1
            and content.y0 <= (line.bbox.y0 + line.bbox.y1) / 2 <= content.y1
        )
        rows.append(
            {
                "span_id": sid,
                "line_id": span.line_id,
                "text": span.raw_text,
                "tokens": token_counter(span.raw_text).total(),
                "trimbox_excluded": excluded,
                "glyphs": [{"seqno": e["seqno"], **g} for e, g in pairs],
                "covers": covers,
                "unsupported_covers": uncertain,
                "screen_candidate": bool(covers),
            }
        )
    return rows


def compare_render(page, pairs, scales=(2, 4), save=None, baselines=None):
    glyphs = [g for _, g in pairs if g["bbox"] and g["glyph_id"] >= 0]
    if not glyphs:
        return {"valid": False, "reason": "no_painted_glyphs"}
    clip = pymupdf.Rect(glyphs[0]["bbox"])
    for glyph in glyphs[1:]:
        clip |= pymupdf.Rect(glyph["bbox"])
    # A relative one-em border covers anti-alias fringes and keeps the control
    # region nonempty; the whole rendered crop is compared, not selected pixels.
    margin = max(g["font_size"] for g in glyphs)
    clip = (clip + (-margin, -margin, margin, margin)) & page.rect
    if clip.is_empty:
        return {"valid": False, "reason": "outside_rendered_page"}
    suppressed = defaultdict(set)
    for event, glyph in pairs:
        suppressed[event["seqno"]].add(tuple(glyph["index"]))
    rows = []
    baselines = {} if baselines is None else baselines
    for scale in scales:
        baseline_key = (scale, tuple(clip))
        if baseline_key not in baselines:
            before, _ = render(page, clip, scale)
            normal = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False)
            assert before.irect == normal.irect and before.samples == normal.samples, (
                "Pass-through renderer differs from PyMuPDF"
            )
            baselines[baseline_key] = before
        before = baselines[baseline_key]
        after, count = render(page, clip, scale, suppressed)
        assert count == sum(len(v) for v in suppressed.values()), (count, suppressed)
        a = np.frombuffer(before.samples, dtype=np.uint8).reshape(
            before.height, before.width, before.n
        )
        b = np.frombuffer(after.samples, dtype=np.uint8).reshape(after.height, after.width, after.n)
        bounds = (clip * pymupdf.Matrix(scale, scale)).irect & before.irect
        x0, y0, x1, y1 = bounds
        a = a[y0 - before.y : y1 - before.y, x0 - before.x : x1 - before.x]
        b = b[y0 - after.y : y1 - after.y, x0 - after.x : x1 - after.x]
        changed = np.any(a != b, axis=2)
        rows.append(
            {
                "dpi": scale * 72,
                "changed_pixels": int(np.count_nonzero(changed)),
                "pixels": int(changed.size),
                "before_sha256": hashlib.sha256(a.tobytes()).hexdigest(),
                "after_sha256": hashlib.sha256(b.tobytes()).hexdigest(),
                "suppressed_glyph_items": count,
                "passthrough_matches_standard_renderer": True,
            }
        )
        if save is not None:
            save.parent.mkdir(parents=True, exist_ok=True)
            before.save(str(save) + f"_{scale}_present.png")
            after.save(str(save) + f"_{scale}_suppressed.png")
    return {
        "valid": True,
        "clip": list(clip),
        "renders": rows,
        "no_pixel_change": all(r["changed_pixels"] == 0 for r in rows),
    }


class AuditExtractor(PyMuPDFExtractor):
    def page_evidence(self, page, digest):
        prov = Provenance(
            source_sha256=digest,
            engine=self.identity.name,
            engine_version=self.identity.version,
            method="native",
            resolved_device="cpu",
        )
        source = self._page_evidence(
            page, digest, self._namespace(digest), prov, pymupdf.TEXTFLAGS_RAWDICT
        )
        raw = page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT, sort=False)
        events = inspect_page(page)
        matches, attribution = attribute(source, raw, events)
        return source, events, matches, attribution

    def scan(self, source_path, numbers=None, confirm=True):
        results = []
        with source_session(source_path) as snapshot, open_source(source_path) as document:
            inputs = {
                "source": snapshot.digest,
                "extraction": code_digest("extraction"),
                "pymupdf": pymupdf.VersionBind,
                "confirm": confirm,
                "producer": {
                    name: hashlib.sha256((ROOT / "experiments" / name).read_bytes()).hexdigest()
                    for name in (
                        "step11d2_hidden.py",
                        "step11d2_device.py",
                        "step11d_visibility.py",
                    )
                },
            }
            key = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
            for page in document:
                number = page.number + 1
                if numbers and number not in numbers:
                    continue
                checkpoint = ROOT / ".cache/step11d2/hidden" / key / f"{number}.json"
                if checkpoint.exists():
                    result = json.loads(checkpoint.read_text("utf8"))
                    assert result["cache_inputs"] == inputs
                    results.append(result)
                    continue
                source, events, matches, attribution = self.page_evidence(page, snapshot.digest)
                rows = candidates(source, matches, events)
                baselines = {}
                for row in rows:
                    if confirm and row["screen_candidate"]:
                        row["render_test"] = compare_render(
                            page, matches[row["span_id"]], baselines=baselines
                        )
                result = {
                    "cache_inputs": inputs,
                    "page": number,
                    "attribution": attribution,
                    "candidate_spans": rows,
                    "form_xobjects": [
                        {"xref": x[0], "name": x[1], "invoker": x[2], "bbox": list(x[3])}
                        for x in page.get_xobjects()
                    ],
                    "effective_state_method": (
                        "MuPDF executes page and nested forms; device records each resolved "
                        "paint operation, CTM, clip stack, mask lifetime, group alpha/blend "
                        "and optional layer stack"
                    ),
                }
                write(checkpoint, result)
                results.append(result)
                print(
                    "scan",
                    number,
                    attribution["matched_spans"],
                    "attributed;",
                    len(rows),
                    "cover observations",
                    flush=True,
                )
        return {"source_sha256": snapshot.digest, "pages": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=BOOKS, required=True)
    parser.add_argument("--pages", type=int, nargs="+")
    parser.add_argument("--screen-only", action="store_true")
    args = parser.parse_args()
    result = AuditExtractor("cpu").scan(
        reference_path(BOOKS[args.book][0]), args.pages, not args.screen_only
    )
    label = "all" if args.pages is None else "_".join(map(str, args.pages))
    write(OUT / f"{args.book}_{label}.json", result)


if __name__ == "__main__":
    main()
