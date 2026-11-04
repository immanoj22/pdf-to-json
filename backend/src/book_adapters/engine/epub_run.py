"""One ePub run: converted book + profile + book settings -> ``<out>/<ISBN>.epub`` and
``<out>/report/``. Same engine as the DocBook run (``prepare``), the ePub writer, then the
ePub checks."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from ..validate import epub_checks
from ..writers.base import WriteContext
from ..writers.epub3 import Epub3Writer
from .epub_packager import write_epub
from .profile import epub_section
from .profile_store import ProfileStore
from .run import ExportBlocked, _counts, prepare


def run_epub(
    book_dir,
    out_dir,
    settings_path=None,
    profile_ref=None,
    store=None,
    validate: bool = True,
    allow_alt_text_placeholders: bool = False,
    modified: str | None = None,
    epubcheck_jar=None,
) -> dict:
    """Make the ePub. Fails (ExportBlocked, no file written) while an alt-text placeholder
    remains, unless the override is given (recorded). ``modified`` is dcterms:modified
    (from the export record), so reruns are byte-identical."""
    started = time.perf_counter()
    store = store or ProfileStore()
    out_dir = Path(out_dir)
    profile, stored, settings, book, rules_on, doc, authors = prepare(
        book_dir, settings_path, profile_ref, store
    )
    ctx = WriteContext(profile, settings, rules_on, book, {"modified": modified})
    writer = Epub3Writer()
    delivery = writer.write(doc, ctx)
    cfg = writer.cfg
    placeholders = sorted(set(delivery.alt_placeholders))
    blocked = bool(placeholders) and not allow_alt_text_placeholders
    isbn = settings.data.get("isbn") or profile.get("delivery.missing_isbn_folder")
    epub_path = out_dir / cfg["package"]["file_name"].format(isbn=isbn)
    out_dir.mkdir(parents=True, exist_ok=True)
    if epub_path.exists():
        epub_path.unlink()
    if not blocked:
        write_epub(delivery.files, epub_path)
    report = {
        "format": "epub",
        "status": "failed: alt text missing" if blocked else "written",
        "alt_text": {
            "placeholders": len(placeholders),
            "units": placeholders,
            "override": bool(placeholders) and allow_alt_text_placeholders,
        },
        "book": {
            "folder": book.folder.name,
            "book_json_sha256": book.sha256,
            "content_sha256": book.data["metadata"].get("content_sha256"),
            "pages": len(book.pages),
        },
        "profile": {
            **profile.identity(),
            "origin": stored.origin,
            "status": stored.status,
            "ref": stored.ref,
        },  # fmt: skip
        "profile_has_epub": writer.has_epub_section,
        "settings": {
            "file": Path(settings_path).name if settings_path else None,
            "sha256": hashlib.sha256(Path(settings_path).read_bytes()).hexdigest()
            if settings_path
            else None,
            "to_supply": settings.to_supply,
        },
        "rules_on": sorted(rules_on),
        "delivery": {
            "root": epub_path.name,
            "main_file": delivery.main_file,
            "files": sorted(delivery.files),
            "divisions": delivery.divisions,
            "epub": epub_path.name if epub_path.exists() else None,
            "epub_sha256": hashlib.sha256(epub_path.read_bytes()).hexdigest()
            if epub_path.exists()
            else None,
        },
        "warnings": [],
    }
    if stored.status == "untested":
        report["warnings"].append(f"profile {stored.ref} is untested")
    if not writer.has_epub_section:
        report["warnings"].append("the profile has no epub section: schema defaults used")
    if placeholders and allow_alt_text_placeholders:
        report["warnings"].append(
            f"OVERRIDE: exported with {len(placeholders)} alt-text placeholder(s)"
        )
    if settings.to_supply:
        report["warnings"].append("book settings to supply: " + ", ".join(settings.to_supply))
    report["authors"] = {
        "source": "title_page" if authors else "settings"
        if settings.data.get("authorgroups") else "none",
        "people": len(authors),
        "must_check": sum(1 for p in authors if p.uncertain),
    }  # fmt: skip
    reviews = [r.as_dict() for r in doc.reviews + delivery.reviews]
    report_dir = out_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    if validate and not blocked:
        cfg_check = dict(cfg)
        cfg_check["_alt_placeholder"] = profile.get("figures.alt_text_placeholder")
        report["checks"] = {
            "epub": epub_checks.check_epub(
                epub_path, cfg_check, delivery, doc, book, delivery.ledger
            ),
            "epubcheck": epub_checks.run_epubcheck(epub_path, epubcheck_jar),
        }
    report["review_counts"] = _counts(reviews)
    from ..qc_epub import write as write_qc

    qc = write_qc(report_dir, report, reviews, profile, book, epub_path)
    report["qc_verdict"] = qc["verdict"]
    dump = lambda o: json.dumps(o, indent=1, sort_keys=True, ensure_ascii=False) + "\n"  # noqa: E731
    (report_dir / "delivery_report.json").write_text(dump(report), "utf-8")
    (report_dir / "review.json").write_text(dump(reviews), "utf-8")
    elapsed = time.perf_counter() - started
    (report_dir / "run.json").write_text(json.dumps({"seconds": round(elapsed, 2)}) + "\n")
    report["seconds"] = round(elapsed, 2)
    report["epub"] = str(epub_path) if epub_path.exists() else None
    if blocked:
        raise ExportBlocked(
            f"Export failed: {len(placeholders)} figure/equation alt text(s) are placeholders. "
            "Supply them, or pass the explicit override (recorded in the report).",
            report,
        )
    return report


_ = epub_section
