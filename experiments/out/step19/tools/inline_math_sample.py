"""40 seeded inline-math marks of the Statistics final2 publication, cropped from the source page."""
import json
import random
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import pymupdf as fitz
from reference_paths import reference_path
from step13c_evaluate import archive_records

out = Path(sys.argv[1])
run = json.loads((ROOT / "experiments/out/step19/final2/performance/statistics.json").read_text())["run"]
book = json.loads((Path(run["book_json"]) / "book.json").read_text())
marks = {}
def walk(n):
    if isinstance(n, dict):
        if n.get("kind") == "math" and n.get("equation"): marks.setdefault(n["equation"], n)
        for v in n.values(): walk(v)
    elif isinstance(n, list):
        for v in n: walk(v)
walk(book["content"])
regions, records = archive_records(run)
byid = {r.id[:16]: r for v in regions.values() for r in v if r.presentation == "inline"}
pool = sorted(k for k in marks if k in byid)
print("inline marks", len(marks), "with region", len(pool))
chosen = sorted(random.Random(19).sample(pool, 40), key=lambda k: (byid[k].page, byid[k].bbox.y0))
items = []
doc = fitz.open(reference_path("statistics_pdf"))
for start in range(0, 40, 10):
    sheet = fitz.open(); W = 600; page_out = sheet.new_page(width=W, height=10 * 66)
    for k, eid in enumerate(chosen[start:start + 10]):
        r = byid[eid]; p = doc[r.page - 1]; b = r.bbox
        clip = fitz.Rect(max(0, b.x0 - 200), b.y0 - 14, min(p.rect.width, b.x1 + 200), b.y1 + 14)
        p.add_rect_annot(fitz.Rect(b.x0 - 1, b.y0 - 1, b.x1 + 1, b.y1 + 1)).set_colors(stroke=(1, 0, 0))
        n = start + k + 1; top = k * 66
        latex = marks[eid].get("latex")
        page_out.insert_text((2, top + 10), f"#{n} p{r.page} {r.source} {latex}"[:150], fontsize=7, color=(0, 0, 1))
        page_out.show_pdf_page(fitz.Rect(0, top + 12, W, top + 64), doc, r.page - 1, clip=clip)
        items.append({"item": n, "equation": eid, "page": r.page, "source": r.source, "rules": r.rules,
                      "latex": latex, "review_status": marks[eid].get("review_status"), "judgment": None})
    sheet[0].get_pixmap(dpi=160).save(out / f"sheet_{start // 10 + 1}.png")
(out / "items.json").write_text(json.dumps({"seed": 19, "population": len(pool), "items": items}, indent=1))
