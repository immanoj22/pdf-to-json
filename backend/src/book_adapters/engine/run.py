"""One adapter run: book folder + profile + book settings -> delivery folder and report.

The delivery folder holds only client files. The report (``<out>/report/``) records the
profile name, version and hashes, the book settings, the checks and the review list; its
``run.json`` alone holds times."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

from ..rules import RULES, active_rules
from ..writers.base import WriteContext
from ..writers.docbook import DocBookWriter
from .load import load_book
from .outline import build_document
from .packager import write_delivery, write_zip
from .profile_store import ProfileStore
from .settings import load_settings, settings_from_profile_only

WRITERS = {"docbook": DocBookWriter}


class ExportBlocked(RuntimeError):
    """The delivery was not written (alt-text placeholders remain); the report says why."""

    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report


def prepare(book_dir, settings_path, profile_ref, store):
    """Profile, settings, book and adapter document tree (shared by every output format)."""
    raw_settings = None
    if settings_path:
        import yaml

        raw_settings = yaml.safe_load(Path(settings_path).read_text("utf-8")) or {}
    ref = profile_ref or (raw_settings or {}).get("profile")
    if not ref:
        raise ValueError("No profile: give --profile or set profile in the book settings")
    if (
        raw_settings
        and raw_settings.get("profile_version")
        and "@" not in ref
        and not ref.endswith((".yaml", ".yml"))
    ):
        ref = f"{ref}@{raw_settings['profile_version']}"
    profile, stored = store.load(ref)
    settings = (
        load_settings(settings_path, profile) if settings_path else settings_from_profile_only(ref)
    )
    word = str((settings.data.get("options") or {}).get("part_label") or "").strip()
    if word:  # the word printed before a part's number in this book (UNIT, SECTION, PART)
        profile.data = {**profile.data, "labels": {**profile.data.get("labels", {}),
                                                    "part": f"{word} {{n}}"}}  # fmt: skip
    book = load_book(book_dir)
    rules_on = active_rules(profile, settings)
    doc = build_document(book, profile, settings, rules_on)
    title_page_authors = [p for group in doc.bookinfo.authors for p in group]
    if title_page_authors:
        settings.to_supply = [f for f in settings.to_supply if f != "authorgroups"]
    for name in sorted(rules_on):
        if RULES[name].phase == "tree":
            RULES[name].func(doc, {"profile": profile, "settings": settings})
    return profile, stored, settings, book, rules_on, doc, title_page_authors


def run_book(
    book_dir,
    out_dir,
    settings_path=None,
    profile_ref=None,
    store=None,
    validate: bool = True,
    allow_alt_text_placeholders: bool = False,
) -> dict:
    """Run one book. Fails (ExportBlocked, no delivery written) while any alt-text
    placeholder remains, unless ``allow_alt_text_placeholders`` is given; the report records
    the override."""
    started = time.perf_counter()
    store = store or ProfileStore()
    out_dir = Path(out_dir)
    profile, stored, settings, book, rules_on, doc, title_page_authors = prepare(
        book_dir, settings_path, profile_ref, store
    )
    writer = WRITERS[profile.get("writer")]()
    delivery = writer.write(doc, WriteContext(profile, settings, rules_on, book))
    placeholders = sorted(set(delivery.alt_placeholders))
    blocked = bool(placeholders) and not allow_alt_text_placeholders
    if out_dir.exists():
        target = out_dir / delivery.root
        if target.exists():
            shutil.rmtree(target)
    root = None if blocked else write_delivery(delivery, book, profile, out_dir)
    zip_name = profile.get("delivery.zip")
    zip_path = None
    if zip_name:
        isbn = settings.data.get("isbn") or profile.get("delivery.missing_isbn_folder")
        zip_path = out_dir / zip_name.format(isbn=isbn)
        if zip_path.exists():
            zip_path.unlink()
        if root is not None:
            write_zip(root, zip_path)
    report = {
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
        },
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
            "big_images": sum(1 for j in delivery.images if j.big),
            "divisions": delivery.divisions,
            "zip": zip_path.name if zip_path and zip_path.exists() else None,
            "zip_sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest()
            if zip_path and zip_path.exists()
            else None,
        },
        "warnings": [],
    }
    if stored.status == "untested":
        report["warnings"].append(
            f"profile {stored.ref} is untested: it has not been run against example deliveries"
        )
    if placeholders and allow_alt_text_placeholders:
        report["warnings"].append(
            f"OVERRIDE: exported with {len(placeholders)} alt-text placeholder(s) "
            "(allow_alt_text_placeholders)"
        )
    if settings.to_supply:
        report["warnings"].append("book settings to supply: " + ", ".join(settings.to_supply))
    if title_page_authors:
        unclear = sum(1 for p in title_page_authors if p.uncertain)
        report["warnings"].append(
            f"authors read from the title page: {len(title_page_authors)} "
            f"({unclear} must be checked); give authorgroups in the book settings to override"
        )
    report["authors"] = {
        "source": "title_page"
        if title_page_authors
        else "settings"
        if settings.data.get("authorgroups")
        else "none",
        "people": len(title_page_authors),
        "must_check": sum(1 for p in title_page_authors if p.uncertain),
    }
    reviews = [r.as_dict() for r in doc.reviews + delivery.reviews]
    if validate and root is not None:
        from ..validate import run_checks

        report["checks"] = run_checks(root, delivery, doc, book, profile)
    report_dir = out_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    report["review_counts"] = _counts(reviews)
    from ..qc import write as write_qc

    qc = write_qc(report_dir, report, reviews, profile, book, root)
    report["qc_verdict"] = qc["verdict"]
    (report_dir / "delivery_report.json").write_text(
        json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n", "utf-8"
    )
    (report_dir / "review.json").write_text(
        json.dumps(reviews, indent=1, sort_keys=True, ensure_ascii=False) + "\n", "utf-8"
    )
    elapsed = time.perf_counter() - started
    (report_dir / "run.json").write_text(json.dumps({"seconds": round(elapsed, 2)}) + "\n")
    report["seconds"] = round(elapsed, 2)
    report["root"] = str(root) if root else None
    if blocked:
        raise ExportBlocked(
            f"Export failed: {len(placeholders)} figure/equation alt text(s) are placeholders. "
            f"Supply them, or pass the explicit override (recorded in the report). "
            f"Report: {report_dir / 'delivery_report.json'}",
            report,
        )
    return report


def _counts(reviews: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for r in reviews:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    return dict(sorted(counts.items()))
