"""Synthetic diagnostic guard cases; originals and converter caches are untouched."""

# ruff: noqa: E402
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import pymupdf
from step11d2_hidden import AuditExtractor, candidates, compare_render, write


def fixture(kind):
    doc = pymupdf.open()
    page = doc.new_page(width=240, height=300)
    page.insert_text((35, 75), "Ordinary text", fontsize=14)
    if kind == "repeated":
        page.insert_text((35, 75), "Ordinary text", fontsize=14)
    if kind in {"hidden", "partial", "semi"}:
        rect = (25, 45, 80 if kind == "partial" else 210, 90)
        page.draw_rect(rect, color=None, fill=(1, 1, 1), fill_opacity=0.5 if kind == "semi" else 1)
    if kind == "soft_mask":
        mask = doc.get_new_xref()
        doc.update_object(
            mask,
            "<< /Type /XObject /Subtype /Form /BBox [0 0 240 300] "
            "/Group << /S /Transparency /CS /DeviceGray >> /Resources << >> >>",
        )
        doc.update_stream(mask, b"0.5 g 0 0 240 300 re f")
        state = doc.get_new_xref()
        doc.update_object(
            state, f"<< /Type /ExtGState /SMask << /S /Luminosity /G {mask} 0 R >> >>"
        )
        resources = int(doc.xref_get_key(page.xref, "Resources")[1].split()[0])
        doc.xref_set_key(resources, "ExtGState", f"<< /AuditMask {state} 0 R >>")
        stream = doc.get_new_xref()
        doc.update_object(stream, "<< >>")
        doc.update_stream(stream, b"q /AuditMask gs 1 1 1 rg 25 210 185 45 re f Q")
        original = page.get_contents()
        doc.xref_set_key(
            page.xref, "Contents", "[" + " ".join(f"{x} 0 R" for x in [*original, stream]) + "]"
        )
    if kind == "clipped":
        stream = doc.get_new_xref()
        doc.update_object(stream, "<< >>")
        doc.update_stream(stream, b"q 25 210 40 45 re W n 1 1 1 rg 25 210 185 45 re f Q")
        original = page.get_contents()
        doc.xref_set_key(
            page.xref, "Contents", "[" + " ".join(f"{x} 0 R" for x in [*original, stream]) + "]"
        )
    data = doc.tobytes()
    doc.close()
    return pymupdf.open(stream=data), hashlib.sha256(data).hexdigest()


def main():
    rows = []
    for kind in ("visible", "hidden", "partial", "semi", "soft_mask", "repeated", "clipped"):
        with fixture(kind)[0] as document:
            digest = hashlib.sha256(document.tobytes()).hexdigest()
            page = document[0]
            native, events, matched, attribution = AuditExtractor("cpu").page_evidence(page, digest)
            observations = candidates(native, matched, events)
            screened = [r for r in observations if r["screen_candidate"]]
            assert len(screened) == (1 if kind == "hidden" else 0), (kind, observations)
            results = {
                sid: compare_render(page, pairs)
                for sid, pairs in matched.items()
                if native.store.spans[sid].raw_text.strip()
            }
            if kind == "hidden":
                assert all(r["valid"] and r["no_pixel_change"] for r in results.values())
            elif kind != "repeated":
                assert all(r["valid"] and not r["no_pixel_change"] for r in results.values())
            rows.append(
                {
                    "fixture": kind,
                    "attribution": attribution,
                    "screen_candidates": len(screened),
                    "observations": observations,
                    "renders": results,
                    "passed": True,
                }
            )
    write(ROOT / "experiments/out/step11d2/diagnostic_guards.json", {"cases": rows, "passed": True})
    print("Seven diagnostic false-positive/suppression guard cases passed", flush=True)


if __name__ == "__main__":
    main()
