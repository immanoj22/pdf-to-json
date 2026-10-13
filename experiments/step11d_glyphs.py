# ruff: noqa: E402
"""Diagnostic font objects and outlines for explicit, source-digested witnesses."""

import hashlib
import io
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from fontTools.cffLib import CFFFontSet
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.ttLib import TTFont
from reference_paths import reference_path
from step7_layouts import BOOKS

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.run_context import open_source, source_session


class Probe(PyMuPDFExtractor):
    def font(self, source, xref, gid):
        with source_session(source) as snapshot, open_source(source) as doc:
            name, ext, kind, data = doc.extract_font(xref)
            if ext == "cff":
                cff = CFFFontSet()
                cff.decompile(io.BytesIO(data), None)
                top = cff[cff.fontNames[0]]
                top.rawDict.setdefault("charset", 0)
                order = top.charset
                glyph_name = order[gid]
                pen = RecordingPen()
                top.CharStrings[glyph_name].draw(pen)
                cmap = None
                units = 1 / top.FontMatrix[0]
            else:
                font = TTFont(io.BytesIO(data))
                glyph_name = font.getGlyphOrder()[gid]
                glyphs = font.getGlyphSet()
                pen = DecomposingRecordingPen(glyphs)
                glyphs[glyph_name].draw(pen)
                cmap = font.getBestCmap() if "cmap" in font else None
                units = font["head"].unitsPerEm
            evidence = {}
            for key in ("Encoding", "ToUnicode", "DescendantFonts"):
                key_kind, value = doc.xref_get_key(xref, key)
                entry = {"kind": key_kind, "value": value}
                if key_kind == "xref":
                    ref = int(value.split()[0])
                    entry["object"] = doc.xref_object(ref)
                    if doc.xref_is_stream(ref):
                        entry["stream"] = doc.xref_stream(ref).decode("latin1")
                evidence[key] = entry
            return {
                "source_sha256": snapshot.digest,
                "font_xref": xref,
                "font_name": name,
                "extension": ext,
                "font_sha256": hashlib.sha256(data).hexdigest(),
                "glyph_id": gid,
                "glyph_name": glyph_name,
                "outline": pen.value,
                "units_per_em": units,
                "embedded_best_cmap": cmap,
                "pdf_font_object": doc.xref_object(xref),
                "mapping_objects": evidence,
            }


probe = Probe("cpu")
rows = {}
for label, book, xref, gid in (
    ("beta_shaped_b", "immigrant_children", 1033, 66),
    ("correct_beta", "immigrant_children", 1031, 67),
    ("cube_as_U01CA", "medical_anatomy", 3034, 95),
    ("arrow_as_U00BE", "medical_anatomy", 3014, 190),
):
    rows[label] = probe.font(reference_path(BOOKS[book][0]), xref, gid)
a = rows["beta_shaped_b"]["outline"]
b = rows["correct_beta"]["outline"]
assert [op for op, pts in a] == [op for op, pts in b]
points = [
    (p, q) for (_, aps), (_, bps) in zip(a, b, strict=True) for p, q in zip(aps, bps, strict=True)
]
assert all(p[1] == q[1] for p, q in points)
fit = statistics.linear_regression([q[1] for p, q in points], [p[0] - q[0] for p, q in points])
rows["beta_outline_comparison"] = {
    "operators_identical": True,
    "points": len(points),
    "y_coordinates_identical": True,
    "fit": "source_x = target_x + shear * target_y + offset",
    "shear": fit.slope,
    "offset": fit.intercept,
    "max_residual_font_units": max(
        abs(p[0] - q[0] - fit.slope * q[1] - fit.intercept) for p, q in points
    ),
    "interpretation": "Strong diagnostic shape evidence; not a validated general repair algorithm.",
}
out = ROOT / "experiments/out/step11d/diagnosis/glyph_examples.json"
out.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", "utf8")
print(json.dumps(rows["beta_outline_comparison"]))
