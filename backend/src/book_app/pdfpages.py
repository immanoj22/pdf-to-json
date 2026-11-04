"""PDF page pictures for the review screen (rendered on demand, cached per job)."""

from __future__ import annotations

from pathlib import Path

import pymupdf


def page_info(pdf: Path) -> list[dict]:
    with pymupdf.open(pdf) as doc:
        return [
            {"index": i + 1, "width": p.rect.width, "height": p.rect.height}
            for i, p in enumerate(doc)
        ]


def page_png(pdf: Path, number: int, scale: float, cache: Path) -> Path:
    scale = max(0.5, min(3.0, round(scale * 4) / 4))
    target = cache / f"p{number:05d}_{scale:g}.png"
    if target.is_file():
        return target
    cache.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(pdf) as doc:
        page = doc[number - 1]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(pix.tobytes("png"))
        tmp.replace(target)
    return target


def check_pdf(path: Path) -> tuple[int, str | None]:
    """(page count, problem). A PDF is judged by its content, never by its name."""
    with open(path, "rb") as f:
        head = f.read(1024)
    if b"%PDF-" not in head:
        return 0, "This file is not a PDF."
    try:
        with pymupdf.open(path) as doc:
            if doc.needs_pass or doc.is_encrypted:
                return 0, "This PDF is password protected. Remove the password and upload it again."
            if doc.page_count < 1:
                return 0, "This PDF has no pages."
            return doc.page_count, None
    except Exception:
        return 0, "This PDF cannot be opened; it may be damaged."
