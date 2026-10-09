"""Evidence overlay only: typography, repeated edge text and navigation links."""

from pathlib import Path

import cv2
import numpy as np

from book_core.objects.roles import raster_array


def render_document_overlay(raster, page, evidence, output: Path):
    original = raster_array(raster)
    canvas = np.full((original.shape[0] + 100, original.shape[1], 3), 255, dtype=np.uint8)
    canvas[100:] = original
    sx, sy = raster.width / raster.page_width, raster.height / raster.page_height
    clusters = {r["id"]: i for i, r in enumerate(evidence["style"]["style_clusters"], 1)}
    styles = {
        r["line_id"]: r for r in evidence["style"]["lines"] if r["page"] == page.geometry.page
    }
    repeats = {}
    for item in evidence["repetition"]["candidates"]:
        for row in item["occurrences"]:
            if row["page"] == page.geometry.page:
                repeats.setdefault(row["line_id"], []).append(item)
    links = {}
    incoming = []
    for entry in evidence["navigation"]["entries"]:
        if page.geometry.page in entry["target_pages"]:
            incoming.append(entry["id"])
        if entry["source_page"] == page.geometry.page:
            for line_id in entry.get("line_ids", []):
                links.setdefault(line_id, []).append(entry)
    rows = []
    for line in page.store.lines:
        style = styles[line.id]
        index = clusters.get(style["style_cluster_id"], 0)
        color = (50 + index * 67 % 170, 50 + index * 97 % 170, 50 + index * 37 % 170)
        p0 = round(line.bbox.x0 * sx), round(line.bbox.y0 * sy) + 100
        p1 = round(line.bbox.x1 * sx), round(line.bbox.y1 * sy) + 100
        cv2.rectangle(canvas, p0, p1, color, 1, cv2.LINE_AA)
        flags = []
        if line.id in repeats:
            cv2.rectangle(canvas, (p0[0] - 2, p0[1] - 2), (p1[0] + 2, p1[1] + 2), (0, 0, 230), 2)
            flags.append("R")
        if line.id in links:
            cv2.rectangle(canvas, (p0[0] - 4, p0[1] - 4), (p1[0] + 4, p1[1] + 4), (230, 90, 0), 2)
            destinations = sorted({p for e in links[line.id] for p in e["target_pages"]})
            flags.append("T>" + ",".join(map(str, destinations)))
        cv2.putText(
            canvas,
            f"S{index} " + " ".join(flags),
            (p0[0], max(108, p0[1] - 3)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.28,
            color,
            1,
            cv2.LINE_AA,
        )
        rows.append(
            {
                "line_id": line.id,
                "style_cluster_index": index,
                "style_cluster_id": style["style_cluster_id"],
                "repetition_candidates": [c["id"] for c in repeats.get(line.id, [])],
                "toc_links": [e["id"] for e in links.get(line.id, [])],
            }
        )
    title = f"PDF page {page.geometry.page} | S=style cluster, R=repetition, T>PDF target"
    cv2.putText(canvas, title, (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1)
    cv2.putText(
        canvas,
        f"{len(incoming)} incoming navigation links (IDs in sidecar)",
        (12, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (20, 20, 20),
        1,
    )
    cv2.putText(
        canvas,
        "Evidence only; red/blue frames make no role or order decision",
        (12, 75),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (20, 20, 20),
        1,
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), canvas):
        raise OSError("Overlay image could not be written")
    return {"page": page.geometry.page, "lines": rows, "incoming_navigation": incoming}
