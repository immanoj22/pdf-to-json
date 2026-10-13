"""Exploratory visibility candidates only; never changes the converter or its caches.

Exact text/bounding-box matches and limited drawing cores are insufficient for a
production exclusion proof. In particular, graphics-state resources are guarded
page-wide rather than tracked per operation. See the report's reliability table.
"""

# ruff: noqa: E402
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
sys.stdout.reconfigure(encoding="utf8")
import pymupdf
from reference_paths import reference_path
from step7_layouts import BOOKS

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ledger.tokenization import token_counter
from book_core.model.common import Provenance
from book_core.run_context import open_source, source_session


def contains(a, b):
    return a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]


def core(items):
    if len(items) == 1 and items[0][0] == "re":
        return tuple(items[0][1])
    if len(items) != 8 or Counter(i[0] for i in items) != {"c": 4, "l": 4}:
        return None
    endpoints = []
    lines = []
    curves = []
    for item in items:
        points = [tuple(p) for p in item[1:]]
        if item[0] == "l":
            lines.append(points)
        else:
            curves.append(points)
        endpoints.extend([points[0], points[-1]])
    xs = [p[0] for p in endpoints]
    ys = [p[1] for p in endpoints]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    sides = {}
    for a, b in lines:
        if a[0] == b[0] and a[0] in (xmin, xmax):
            sides["left" if a[0] == xmin else "right"] = sorted([a[1], b[1]])
        elif a[1] == b[1] and a[1] in (ymin, ymax):
            sides["top" if a[1] == ymin else "bottom"] = sorted([a[0], b[0]])
        else:
            return None
    if len(sides) != 4:
        return None
    box = (
        max(sides["top"][0], sides["bottom"][0]),
        max(sides["left"][0], sides["right"][0]),
        min(sides["top"][1], sides["bottom"][1]),
        min(sides["left"][1], sides["right"][1]),
    )
    if box[0] >= box[2] or box[1] >= box[3]:
        return None
    # Four cubic corner paths stay in disjoint corner rectangles. No sampled
    # approximation or path bounding-box-as-fill assumption is used.
    corners = set()
    for pts in curves:
        matching = []
        for ix, (lo, hi) in enumerate(((xmin, box[0]), (box[2], xmax))):
            for iy, (bot, top) in enumerate(((ymin, box[1]), (box[3], ymax))):
                if all(lo <= x <= hi and bot <= y <= top for x, y in pts):
                    matching.append((ix, iy))
        if len(matching) != 1:
            return None
        corners.add(matching[0])
    if len(corners) != 4:
        return None
    # Require one continuous closed contour, allowing arbitrary start/direction.
    if any(tuple(a[-1]) != tuple(b[1]) for a, b in zip(items, items[1:] + items[:1], strict=True)):
        return None
    return box


class DiagnosticExtractor(PyMuPDFExtractor):
    def inspect(self, source, numbers=None):
        results = []
        totals = Counter()
        namespace = None
        with source_session(source) as snapshot, open_source(source) as doc:
            namespace = self._namespace(snapshot.digest)
            prov = Provenance(
                source_sha256=snapshot.digest,
                engine=self.identity.name,
                engine_version=self.identity.version,
                method="native",
                resolved_device="cpu",
            )
            for page in doc:
                if numbers and page.number + 1 not in numbers:
                    continue
                evidence = self._page_evidence(
                    page, snapshot.digest, namespace, prov, pymupdf.TEXTFLAGS_RAWDICT
                )
                traces = page.get_texttrace()
                drawings = page.get_drawings(extended=True)
                log = page.get_bboxlog(layers=True)
                # Unsupported graphics states conservatively disable cover proofs.
                resources = [page.xref] + [x[0] for x in page.get_xobjects()]
                unsafe = []
                for xref in resources:
                    kind, value = doc.xref_get_key(xref, "Resources/ExtGState")
                    refs = re.findall(r"(\d+)\s+\d+\s+R", value)
                    for number in refs:
                        gs = doc.xref_object(int(number))
                        if re.search(r"/SMask\s+(?!/None\b)", gs) or re.search(
                            r"/BM\s+(?!/Normal\b)", gs
                        ):
                            unsafe.append(int(number))
                groups = any(d["type"] == "group" for d in drawings)
                clips = {}
                fills = []
                cover_candidates = []
                for d in drawings:
                    level = d.get("level", 0)
                    clips = {k: v for k, v in clips.items() if k < level}
                    if d["type"] == "clip":
                        clips[level] = core(d.get("items", []))
                        continue
                    if d["type"] not in ("f", "fs"):
                        continue
                    rect = core(d["items"])
                    seq = d.get("seqno")
                    if seq is None:
                        continue
                    if rect is None:
                        cover_candidates.append((seq, tuple(d["rect"]), "unsupported_filled_path"))
                        continue
                    valid = (
                        not unsafe
                        and not groups
                        and not d.get("layer")
                        and d.get("fill_opacity") == 1
                        and all(c is not None and contains(c, rect) for c in clips.values())
                    )
                    if valid:
                        fills.append((seq, rect, d.get("fill")))
                    else:
                        cover_candidates.append((seq, rect, "unsupported_graphics_state_or_clip"))
                bytext = defaultdict(list)
                for trace in traces:
                    bytext["".join(chr(c[0]) for c in trace["chars"])].append(trace)
                sizes = [
                    s.size
                    for s in evidence.store.spans.values()
                    if s.raw_text.strip() and s.size > 0
                ]
                median = statistics.median(sizes) if sizes else None
                span_rows = []
                line_rows = []
                for span in evidence.store.spans.values():
                    bbox = tuple(span.bbox.model_dump().values())
                    candidates = [t for t in bytext[span.raw_text] if contains(bbox, t["bbox"])]
                    facts = []
                    hidden = []
                    for t in candidates:
                        reasons = []
                        if t["type"] == 3:
                            reasons.append({"kind": "ignored_text_trace", "seqno": t["seqno"]})
                        if t.get("opacity") == 0:
                            reasons.append({"kind": "zero_opacity", "seqno": t["seqno"]})
                        glyphs = [c[3] for c in t["chars"] if not chr(c[0]).isspace()]
                        occluders = [
                            seq
                            for seq, rect, color in fills
                            if seq > t["seqno"]
                            and glyphs
                            and all(contains(rect, g) for g in glyphs)
                        ]
                        if occluders:
                            reasons.append(
                                {
                                    "kind": "later_opaque_fill_core",
                                    "seqno": t["seqno"],
                                    "cover_seqnos": occluders,
                                }
                            )
                        hidden.append(bool(reasons))
                        facts.extend(reasons)
                    review = []
                    if any(
                        seq > t["seqno"] and contains(rect, t["bbox"])
                        for t in candidates
                        for seq, rect, reason in cover_candidates
                    ):
                        review.append("unproved_later_cover")
                    if any(
                        entry[0] == "fill-image"
                        and i > t["seqno"]
                        and contains(entry[1], t["bbox"])
                        for t in candidates
                        for i, entry in enumerate(log)
                    ):
                        review.append("later_image_bounds_only")
                    if any(t.get("layer") for t in candidates):
                        review.append("optional_content_membership")
                    if median and span.size < median / 20:
                        review.append("tiny_relative_to_page")
                    if span.bbox.x1 == span.bbox.x0 or span.bbox.y1 == span.bbox.y0:
                        review.append("zero_area")
                    if (
                        span.bbox.x1 <= 0
                        or span.bbox.y1 <= 0
                        or span.bbox.x0 >= page.rect.width
                        or span.bbox.y0 >= page.rect.height
                    ):
                        review.append("outside_page")
                    if candidates and all(hidden):
                        status = "hidden"
                    elif any(hidden) or review:
                        status = "uncertain"
                    else:
                        status = "visible"
                    if status != "visible":
                        span_rows.append(
                            {
                                "span_id": span.id,
                                "source_line_id": span.line_id,
                                "status": status,
                                "facts": facts,
                                "review": review,
                                "text": span.raw_text,
                                "matches": len(candidates),
                            }
                        )
                byspan = {r["span_id"]: r for r in span_rows}
                for line in evidence.store.lines:
                    relevant = [byspan[s] for s in line.span_ids if s in byspan]
                    if relevant:
                        wholly = all(
                            (not evidence.store.spans[s].raw_text.strip())
                            or (s in byspan and byspan[s]["status"] == "hidden")
                            for s in line.span_ids
                        )
                        text = evidence.store.raw_line_text(line)
                        line_rows.append(
                            {
                                "line_id": line.id,
                                "status": (
                                    "whitespace_only_candidate"
                                    if not text.strip()
                                    else "hidden"
                                    if wholly
                                    else "suspicious_mixed_or_uncertain"
                                ),
                                "tokens": token_counter(text).total(),
                                "text": text,
                            }
                        )
                row = {
                    "page": page.number + 1,
                    "spans": span_rows,
                    "lines": line_rows,
                    "ocgs": doc.get_ocgs(),
                    "unsafe_graphics_states": sorted(set(unsafe)),
                    "fill_cores": len(fills),
                }
                for r in line_rows:
                    totals[r["status"] + "_lines"] += 1
                    totals[r["status"] + "_tokens"] += r["tokens"]
                results.append(row)
                if (page.number + 1) % 100 == 0:
                    print("hidden scan", page.number + 1, dict(totals), flush=True)
        return {"source_sha256": snapshot.digest, "totals": dict(totals), "pages": results}


if __name__ == "__main__":
    for book in BOOKS:
        row = DiagnosticExtractor("cpu").inspect(reference_path(BOOKS[book][0]))
        (ROOT / f".cache/step11d/hidden_{book}.json").write_text(
            json.dumps(row, indent=2, ensure_ascii=False) + "\n", "utf8"
        )
        print(book, dict(row["totals"]), flush=True)
