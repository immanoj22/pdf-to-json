"""Delivery checks: DTD, house rules from the profile, lossless."""

from __future__ import annotations

from pathlib import Path

from . import dtd, house_rules, lossless


def run_checks(root: Path, delivery, doc, book, profile) -> dict:
    files = sorted(delivery.files)
    return {
        "dtd": dtd.validate_delivery(root, files),
        "house_rules": house_rules.run(root, delivery, doc, book, profile),
        "lossless": lossless.check(root / delivery.main_file, doc, delivery.ledger),
    }
