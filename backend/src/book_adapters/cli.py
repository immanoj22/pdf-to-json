"""book-adapters command line.

book-adapters profile test FILE.yaml --examples FOLDER|examples.yaml [--out DIR]
book-adapters profiles list
book-adapters profiles validate FILE.yaml
book-adapters profiles add FILE.yaml
book-adapters settings draft BOOK_DIR --profile NAME [--out books/ISBN.yaml]
book-adapters run BOOK_DIR --out DIR [--settings books/ISBN.yaml] [--profile NAME|FILE.yaml]
book-adapters compare OUR_DELIVERY REFERENCE_DELIVERY [--book BOOK_DIR] [--out compare.json]
                       [--html compare.html]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine.profile import ProfileError
from .engine.profile_store import ProfileStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="book-adapters")
    parser.add_argument("--profiles-store", help="user profile store (default: profiles/_store)")
    sub = parser.add_subparsers(dest="command", required=True)
    prof = sub.add_parser("profiles").add_subparsers(dest="action", required=True)
    prof.add_parser("list")
    v = prof.add_parser("validate")
    v.add_argument("file")
    a = prof.add_parser("add")
    a.add_argument("file")
    pt = sub.add_parser("profile").add_subparsers(dest="action", required=True)
    t = pt.add_parser("test", help="export example books with a profile and compare them")
    t.add_argument("file")
    t.add_argument("--examples", required=True, help="examples.yaml, or a folder holding it")
    t.add_argument("--out", default="profile_test_out")
    st = sub.add_parser("settings").add_subparsers(dest="action", required=True)
    d = st.add_parser("draft")
    d.add_argument("book")
    d.add_argument("--profile", required=True)
    d.add_argument("--out")
    r = sub.add_parser("run")
    r.add_argument("book")
    r.add_argument("--out", required=True)
    r.add_argument("--settings")
    r.add_argument(
        "--profile",
        help="profile name[@version] or a profile YAML (stored as a new untested version)",
    )
    r.add_argument(
        "--allow-alt-text-placeholders",
        action="store_true",
        help="export even though figures/equations lack alt text (recorded in the report)",
    )
    r.add_argument(
        "--format",
        choices=["docbook", "epub", "html", "dtbook", "daisy3", "jats", "bits"],
        default="docbook",
        help="docbook (default) or epub (needs a profile with an epub section, e.g. jaypee_v4)",
    )
    r.add_argument("--modified", help="ePub dcterms:modified (CCYY-MM-DDThh:mm:ssZ)")
    r.add_argument("--epubcheck-jar", help="EPUBCheck jar (default: $EPUBCHECK_JAR or tools/)")
    c = sub.add_parser("compare")
    c.add_argument("ours")
    c.add_argument("reference")
    c.add_argument("--book", help="our converted book folder: evidence for the labels")
    c.add_argument("--out", help="compare.json (an HTML page is written next to it)")
    c.add_argument("--html", help="HTML page path (default: next to --out)")
    args = parser.parse_args(argv)
    store = ProfileStore(store=Path(args.profiles_store) if args.profiles_store else None)
    try:
        if args.command == "profiles":
            return _profiles(args, store)
        if args.command == "profile":
            from .profile_test import print_summary, test_profile

            summary = test_profile(Path(args.file), Path(args.examples), Path(args.out))
            print_summary(summary)
            print(f"report: {Path(args.out) / 'profile_test.json'}")
            return 0 if summary["remaining"] == 0 else 1
        if args.command == "settings":
            from .engine.load import load_book
            from .engine.settings import draft_settings, dump_settings

            data, missing = draft_settings(load_book(args.book).data, args.profile)
            text = dump_settings(data)
            if args.out:
                out = Path(args.out)
                if out.exists():
                    print(f"{out} exists; not overwritten", file=sys.stderr)
                    return 2
                out.write_text(text, "utf-8")
            else:
                print(text)
            if missing:
                print("to supply: " + ", ".join(missing), file=sys.stderr)
            return 0
        if args.command == "run":
            from .engine.run import ExportBlocked, run_book

            if args.format == "epub":
                return _run_epub(args, store)
            if args.format != "docbook":
                return _run_format(args, store)
            try:
                report = run_book(
                    args.book,
                    args.out,
                    args.settings,
                    args.profile,
                    store,
                    allow_alt_text_placeholders=args.allow_alt_text_placeholders,
                )
            except ExportBlocked as exc:
                print(str(exc), file=sys.stderr)
                return 3
            checks = report.get("checks", {})
            lossless = checks.get("lossless", {})
            print(
                json.dumps(
                    {
                        "delivery": report["root"],
                        "profile": report["profile"]["ref"],
                        "profile_status": report["profile"]["status"],
                        "dtd_errors": checks.get("dtd", {}).get("errors"),
                        "house_rule_violations": checks.get("house_rules", {}).get("violations"),
                        "lossless_missing": lossless.get("missing"),
                        "lossless_extra": lossless.get("extra"),
                        "warnings": report["warnings"],
                        "seconds": report["seconds"],
                    },
                    indent=1,
                )
            )
            return 0
        if args.command == "compare":
            from .compare import compare_deliveries
            from .compare.html import compare_html

            result = compare_deliveries(
                Path(args.ours), Path(args.reference), Path(args.book) if args.book else None
            )
            text = json.dumps(result, indent=1, ensure_ascii=False)
            if args.out:
                Path(args.out).write_text(text + "\n", "utf-8")
            html_path = args.html or (
                str(Path(args.out).with_suffix(".html")) if args.out else None
            )
            if html_path:
                Path(html_path).write_text(compare_html(result, args.ours, args.reference), "utf-8")
            _print_compare(result)
            return 0
    except ProfileError as exc:
        print(f"Profile problems:\n{exc}", file=sys.stderr)
        return 1
    return 2


def _run_epub(args, store) -> int:
    from .engine.epub_run import run_epub
    from .engine.run import ExportBlocked

    try:
        report = run_epub(
            args.book,
            args.out,
            args.settings,
            args.profile,
            store,
            allow_alt_text_placeholders=args.allow_alt_text_placeholders,
            modified=args.modified,
            epubcheck_jar=args.epubcheck_jar,
        )
    except ExportBlocked as exc:
        print(str(exc), file=sys.stderr)
        return 3
    checks = report.get("checks", {})
    own = checks.get("epub", {})
    ec = checks.get("epubcheck", {})
    print(
        json.dumps(
            {
                "epub": report["epub"],
                "profile": report["profile"]["ref"],
                "verdict": report["qc_verdict"],
                "own_check_findings": own.get("violations"),
                "epubcheck": ec
                if ec.get("status") != "run"
                else {"version": ec["version"], "errors": ec["errors"], "warnings": ec["warnings"]},
                "lossless_missing": own.get("lossless", {}).get("missing"),
                "lossless_extra": own.get("lossless", {}).get("extra"),
                "warnings": report["warnings"],
                "seconds": report["seconds"],
            },
            indent=1,
        )
    )
    return 0


def _print_compare(result: dict) -> None:
    print(f"{'element':16} {'ours':>7} {'reference':>9} {'diff':>6}  label: why")
    for d in result["biggest_differences"]:
        print(
            f"{d['element']:16} {d['ours']:7d} {d['reference']:9d} {d['diff']:+6d}  "
            f"{d['label']}: {d['why']}"
        )
    wf = result["well_formed"]
    for side in ("ours", "reference"):
        if wf[side] != "all":
            for file, err in wf[side].items():
                print(f"not well-formed ({side}): {file}: {err}")


def _profiles(args, store: ProfileStore) -> int:
    if args.action == "list":
        for p in store.list():
            print(f"{p.ref:40} {p.status:9} {p.sha256[:12]}  {p.file}")
        return 0
    if args.action == "validate":
        profile = store.validate(Path(args.file))
        print(
            f"OK: {profile.name} {profile.version} ({profile.date}); sha256 {profile.file_sha256}"
        )
        return 0
    if args.action == "add":
        stored = store.add(Path(args.file))
        print(f"stored {stored.ref} ({stored.status}) at {stored.file}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


def _run_format(args, store) -> int:
    from .engine.formats_run import run_format
    from .engine.run import ExportBlocked

    try:
        report = run_format(
            args.format,
            args.book,
            args.out,
            args.settings,
            args.profile,
            store,
            allow_alt_text_placeholders=args.allow_alt_text_placeholders,
        )
    except ExportBlocked as exc:
        print(str(exc), file=sys.stderr)
        return 3
    checks = report.get("checks", {})
    lossless = checks.get("lossless", {})
    print(
        json.dumps(
            {
                "delivery": report["root"],
                "zip": report["zip"],
                "format": report["format_label"],
                "profile": report["profile"]["ref"],
                "verdict": report["qc_verdict"],
                "schema_errors": checks.get("dtd", {}).get("errors"),
                "rule_findings": checks.get("house_rules", {}).get("violations"),
                "lossless_missing": lossless.get("missing"),
                "lossless_extra": lossless.get("extra"),
                "warnings": report["warnings"],
                "seconds": report["seconds"],
            },
            indent=1,
        )
    )
    return 0
