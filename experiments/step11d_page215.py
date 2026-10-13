# ruff: noqa: E402
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step7_layouts import BOOKS

from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.layout.lines import visibility
from book_core.layout.models import PageLayout
from book_core.objects.analysis import verified_read
from book_core.run_context import open_source, source_session
from book_core.structure.models import BookStructure


class Probe(PyMuPDFExtractor):
    def paint(self, source, number):
        with source_session(source), open_source(source) as doc:
            page = doc[number - 1]
            traces = []
            for index, t in enumerate(page.get_texttrace()):
                text = "".join(chr(c[0]) for c in t["chars"])
                if any(phrase in text for phrase in ("INQUIRY", "LEARN", "Progressive", "REVIEW")):
                    traces.append(
                        {
                            "trace_index": index,
                            "text": text,
                            "seqno": t["seqno"],
                            "type": t["type"],
                            "opacity": t["opacity"],
                            "color": t["color"],
                            "bbox": t["bbox"],
                            "layer": t["layer"],
                        }
                    )
            return {
                "traces": traces,
                "optional_content_groups": doc.get_ocgs(),
                "soft_mask_state_28319": doc.xref_object(28319),
                "soft_mask_object_28318": doc.xref_object(28318),
            }


source = reference_path(BOOKS["spanish_us_history"][0])
extractor = Probe("cpu")
keys = json.loads(
    (ROOT / "experiments/out/step11d/before/spanish_us_history.json").read_text("utf8")
)["keys"]
with source_session(source):
    native = extractor.extract_object_page(source, 215)
visible = visibility(native)
layout = verified_read(
    ROOT / ".cache/step7/layout" / keys["layout"] / "215.json", PageLayout, keys["layout"]
)
decision_key = keys["lists"]["structure_decision_key"]
structure = verified_read(
    ROOT / ".cache/step10/structure/book" / f"{decision_key}.json", BookStructure, decision_key
)
archive = json.loads(
    (ROOT / "experiments/out/step11c/archive/spanish_us_history.json").read_text("utf8")
)
payload = read_json(Path(archive["output"]) / "page_000215.json.gz")
by_line = {line.id: line for line in layout.lines}
unit_text = {
    u["id"]: "\n".join(
        "".join(native.page.store.spans[sid].raw_text for sid in by_line[lid].span_ids)
        for lid in u["line_ids"]
    )
    for u in payload["units"]["units"]
}
rows = []
for line in native.page.store.lines:
    text = native.page.store.raw_line_text(line)
    if any(phrase in text for phrase in ("INQUIRY", "LEARN", "Progressive", "REVIEW")):
        rows.append(
            {
                "source_line_id": line.id,
                "text": text,
                "spans": [
                    {
                        "span_id": sid,
                        "step3_4_visible": visible.get(sid),
                        "traces": [
                            t.model_dump(mode="json")
                            for o in native.objects
                            if o.id == sid
                            for t in o.render_info
                        ],
                    }
                    for sid in line.span_ids
                ],
                "visual_lines": [
                    visual.model_dump(mode="json")
                    for visual in layout.lines
                    if set(visual.span_ids) & set(line.span_ids)
                ],
            }
        )
result = {
    "page": 215,
    "source_sha256": native.page.source_sha256,
    "lines": rows,
    "paint": extractor.paint(source, 215),
    "headings": [
        {"decision": h.model_dump(mode="json"), "unit_text": [unit_text.get(u) for u in h.unit_ids]}
        for h in structure.headings
        if h.page == 215
    ],
    "counterfactual_hidden_excluded_headings": (
        "unverified: no safe exclusion implementation or variant run"
    ),
}
(ROOT / "experiments/out/step11d/diagnosis/page215.json").write_text(
    json.dumps(result, indent=2, ensure_ascii=False) + "\n", "utf8"
)
print("headings", len(result["headings"]), "source English lines", len(rows))
