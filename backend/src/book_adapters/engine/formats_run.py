"""One run of a format writer (HTML, DTBook/NIMAS, DAISY 3, JATS, BITS): converted book +
profile + book settings -> ``<out>/<delivery folder>/``, a ZIP of it and ``<out>/report/``.

The engine is the same as the DocBook and ePub runs (``prepare``); only the writer and its
checks differ. The report has the DocBook run's shape, so the QC report and review list are
the same."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from ..writers.base import WriteContext
from .format_profile import FORMAT_SECTIONS, has_section
from .packager import write_delivery, write_zip
from .profile_store import ProfileStore
from .run import ExportBlocked, _counts, prepare

FORMAT_LABELS = {
    "docbook": "DocBook XML 4.2",
    "epub": "ePub 3",
    "html": "HTML5",
    "dtbook": "NIMAS / DTBook",
    "daisy3": "DAISY 3 (text-only)",
    "jats": "JATS",
    "bits": "BITS",
}


@dataclass
class FormatSpec:
    name: str
    writer: str  # dotted path "module:Class"
    checker: str  # dotted path "module:function"


SPECS = {
    "html": FormatSpec("html", "book_adapters.writers.html5:HtmlWriter",
                       "book_adapters.validate.html_checks:check"),
}  # fmt: skip


def _load(path: str):
    import importlib

    module, _, attr = path.partition(":")
    return getattr(importlib.import_module(module), attr)


def supported_formats(profile) -> list[str]:
    """The formats a profile is meant for: its ``formats`` list, else DocBook plus every
    format whose section the profile has."""
    chosen = profile.get("formats")
    if chosen:
        return list(chosen)
    out = ["docbook"]
    if "epub" in profile.data:
        out.append("epub")
    out += [s for s in FORMAT_SECTIONS if has_section(profile, s)]
    return out


def run_format(
    fmt: str,
    book_dir,
    out_dir,
    settings_path=None,
    profile_ref=None,
    store=None,
    validate: bool = True,
    allow_alt_text_placeholders: bool = False,
    source_pdf=None,
) -> dict:
    """Make one format. Fails (ExportBlocked, no files written) while any alt-text placeholder
    remains, unless the override is given (recorded in the report)."""
    started = time.perf_counter()
    spec = SPECS[fmt]
    store = store or ProfileStore()
    out_dir = Path(out_dir)
    profile, stored, settings, book, rules_on, doc, authors = prepare(
        book_dir, settings_path, profile_ref, store
    )
    writer = _load(spec.writer)()
    delivery = writer.write(
        doc, WriteContext(profile, settings, rules_on, book, {"source_pdf": source_pdf})
    )
    placeholders = sorted(set(delivery.alt_placeholders))
    blocked = bool(placeholders) and not allow_alt_text_placeholders
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / delivery.root
    if target.exists():
        shutil.rmtree(target)
    isbn = settings.data.get("isbn") or profile.get("delivery.missing_isbn_folder")
    zip_path = out_dir / f"{delivery.root}.zip"
    if zip_path.exists():
        zip_path.unlink()
    root = None if blocked else write_delivery(delivery, book, profile, out_dir)
    if root is not None:
        write_zip(root, zip_path)
    report = {
        "format": fmt,
        "format_label": FORMAT_LABELS[fmt],
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
        "profile_has_section": has_section(profile, fmt),
        "settings": {
            "file": Path(settings_path).name if settings_path else None,
            "sha256": hashlib.sha256(Path(settings_path).read_bytes()).hexdigest()
            if settings_path
            else None,
            "to_supply": settings.to_supply,
        },
        "rules_on": sorted(rules_on),
        "delivery": {
            "root": delivery.root,
            "main_file": delivery.main_file,
            "files": sorted(delivery.files),
            "images": len(delivery.images),
            "big_images": 0,
            "divisions": delivery.divisions,
            "zip": zip_path.name if zip_path.exists() else None,
            "zip_sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest()
            if zip_path.exists()
            else None,
        },
        "warnings": [],
    }
    if stored.status == "untested":
        report["warnings"].append(f"profile {stored.ref} is untested")
    if not has_section(profile, fmt):
        report["warnings"].append(f"the profile has no {fmt} section: schema defaults used")
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
    if validate and root is not None:
        cfg = getattr(writer, "cfg", None)
        report["checks"] = _load(spec.checker)(root, delivery, doc, book, profile, cfg)
    report_dir = out_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    report["review_counts"] = _counts(reviews)
    from ..qc import write as write_qc

    qc = write_qc(report_dir, report, reviews, profile, book, root)
    report["qc_verdict"] = qc["verdict"]
    dump = lambda o: json.dumps(o, indent=1, sort_keys=True, ensure_ascii=False) + "\n"  # noqa: E731
    (report_dir / "delivery_report.json").write_text(dump(report), "utf-8")
    (report_dir / "review.json").write_text(dump(reviews), "utf-8")
    elapsed = time.perf_counter() - started
    (report_dir / "run.json").write_text(json.dumps({"seconds": round(elapsed, 2)}) + "\n")
    report["seconds"] = round(elapsed, 2)
    report["root"] = str(root) if root else None
    report["zip"] = str(zip_path) if zip_path.exists() else None
    _ = isbn
    if blocked:
        raise ExportBlocked(
            f"Export failed: {len(placeholders)} figure/equation alt text(s) are placeholders. "
            "Supply them, or pass the explicit override (recorded in the report).",
            report,
        )
    return report
