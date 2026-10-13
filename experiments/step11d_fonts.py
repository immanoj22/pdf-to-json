"""Survey glyph-name/cmap disagreements, including expected small-cap false positives.

Counts are diagnostic candidates, never repair decisions. Resource/trace family
matching is incomplete; agreeing or missing font metadata cannot prove clean text.
"""

# ruff: noqa: E402
import hashlib
import io
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from fontTools import agl
from fontTools.cffLib import CFFFontSet
from fontTools.ttLib import TTFont
from reference_paths import reference_path
from step7_layouts import BOOKS

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.run_context import open_source, source_session


class DiagnosticExtractor(PyMuPDFExtractor):
    def scan(self, source):
        fonts = {}
        total = Counter()
        examples = defaultdict(list)
        perpage = {}
        with open_source(source) as doc:
            for page in doc:
                resources = defaultdict(list)
                for xref, ext, _kind, name, *_ in page.get_fonts(full=True):
                    key = name.split("+")[-1]
                    if xref not in fonts:
                        try:
                            _, ext, _, data = doc.extract_font(xref)
                            if ext == "cff":
                                cff = CFFFontSet()
                                cff.decompile(io.BytesIO(data), None)
                                top = cff[cff.fontNames[0]]
                                top.rawDict.setdefault("charset", 0)
                                order = top.charset
                                cmap = {}
                            elif ext in ("ttf", "otf"):
                                font = TTFont(io.BytesIO(data))
                                order = font.getGlyphOrder()
                                cmap = (font.getBestCmap() or {}) if "cmap" in font else {}
                            else:
                                raise ValueError("unsupported " + ext)
                            inverse = defaultdict(list)
                            for cp, gn in cmap.items():
                                inverse[gn].append(cp)
                            mapping = {}
                            for gid, gn in enumerate(order):
                                value = agl.toUnicode(gn)
                                if len(value) == 1:
                                    mapping[gid] = (gn, ord(value), tuple(inverse.get(gn, [])))
                                elif len(tuple(inverse.get(gn, []))) == 1:
                                    mapping[gid] = (gn, inverse[gn][0], tuple(inverse[gn]))
                            fonts[xref] = {
                                "mapping": mapping,
                                "sha256": hashlib.sha256(data).hexdigest(),
                                "extension": ext,
                            }
                        except Exception as e:
                            fonts[xref] = {"error": str(e)}
                    resources[key].append(xref)
                counts = Counter()
                for trace in page.get_texttrace():
                    names = resources.get(trace["font"].split("+")[-1], [])
                    for index, (cp, gid, _origin, bbox) in enumerate(trace["chars"]):
                        total["trace_characters"] += 1
                        if not names:
                            total["unmatched_font_characters"] += 1
                        candidates = {(fonts[x].get("mapping", {}).get(gid)) for x in names}
                        candidates.discard(None)
                        if len(candidates) != 1:
                            continue
                        gn, want, cmap = next(iter(candidates))
                        if chr(cp).isspace():
                            continue
                        if cp == want or unicodedata.normalize(
                            "NFKC", chr(cp)
                        ) == unicodedata.normalize("NFKC", chr(want)):
                            continue
                        if unicodedata.category(chr(want)).startswith("C"):
                            continue
                        group = f"U+{cp:04X}->U+{want:04X}/{gn}"
                        total[group] += 1
                        counts[group] += 1
                        if len(examples[group]) < 5:
                            examples[group].append(
                                {
                                    "page": page.number + 1,
                                    "seqno": trace["seqno"],
                                    "char_index": index,
                                    "extracted": chr(cp),
                                    "glyph_id": gid,
                                    "glyph_name": gn,
                                    "font_xrefs": names,
                                    "intended": chr(want),
                                    "cmap": cmap,
                                    "context": "".join(chr(c[0]) for c in trace["chars"]),
                                    "bbox": bbox,
                                }
                            )
                perpage[page.number + 1] = dict(counts)
                if (page.number + 1) % 100 == 0:
                    print("scan", page.number + 1, flush=True)
        return {
            "counts": dict(total),
            "examples": dict(examples),
            "pages": perpage,
            "fonts": {
                str(k): {a: b for a, b in v.items() if a != "mapping"} for k, v in fonts.items()
            },
        }


for book in BOOKS:
    with source_session(reference_path(BOOKS[book][0])):
        row = DiagnosticExtractor("cpu").scan(reference_path(BOOKS[book][0]))
    Path(f".cache/step11d/font_scan_{book}.json").write_text(
        json.dumps(row, indent=2, ensure_ascii=False) + "\n", "utf8"
    )
    print(book, json.dumps(row["counts"], ensure_ascii=False), flush=True)
