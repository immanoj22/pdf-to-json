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
from .packager import write_delivery
from .profile_store import ProfileStore
from .settings import load_settings, settings_from_profile_only

WRITERS = {"docbook": DocBookWriter}


def run_book(
    book_dir, out_dir, settings_path=None, profile_ref=None, store=None, validate: bool = True
) -> dict:
    started = time.perf_counter()
    store = store or ProfileStore()
    out_dir = Path(out_dir)
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
    book = load_book(book_dir)
    rules_on = active_rules(profile, settings)
    doc = build_document(book, profile, settings, rules_on)
    for name in sorted(rules_on):
        if RULES[name].phase == "tree":
            RULES[name].func(doc, {"profile": profile, "settings": settings})
    writer = WRITERS[profile.get("writer")]()
    delivery = writer.write(doc, WriteContext(profile, settings, rules_on, book))
    if out_dir.exists():
        target = out_dir / delivery.root
        if target.exists():
            shutil.rmtree(target)
    root = write_delivery(delivery, book, profile, out_dir)
    report = {
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
        },
        "warnings": [],
    }
    if stored.status == "untested":
        report["warnings"].append(
            f"profile {stored.ref} is untested: it has not been run against example deliveries"
        )
    if settings.to_supply:
        report["warnings"].append("book settings to supply: " + ", ".join(settings.to_supply))
    reviews = [r.as_dict() for r in doc.reviews + delivery.reviews]
    if validate:
        from ..validate import run_checks

        report["checks"] = run_checks(root, delivery, doc, book, profile)
    report_dir = out_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    report["review_counts"] = _counts(reviews)
    (report_dir / "delivery_report.json").write_text(
        json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n", "utf-8"
    )
    (report_dir / "review.json").write_text(
        json.dumps(reviews, indent=1, sort_keys=True, ensure_ascii=False) + "\n", "utf-8"
    )
    elapsed = time.perf_counter() - started
    (report_dir / "run.json").write_text(json.dumps({"seconds": round(elapsed, 2)}) + "\n")
    report["seconds"] = round(elapsed, 2)
    report["root"] = str(root)
    return report


def _counts(reviews: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for r in reviews:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    return dict(sorted(counts.items()))
