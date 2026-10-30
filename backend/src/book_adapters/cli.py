"""book-adapters command line.

book-adapters profiles list
book-adapters profiles validate FILE.yaml
book-adapters profiles add FILE.yaml
book-adapters settings draft BOOK_DIR --profile NAME [--out books/ISBN.yaml]
book-adapters run BOOK_DIR --out DIR [--settings books/ISBN.yaml] [--profile NAME|FILE.yaml]
book-adapters compare OUR_DELIVERY REFERENCE_DELIVERY [--out compare.json]
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
    c = sub.add_parser("compare")
    c.add_argument("ours")
    c.add_argument("reference")
    c.add_argument("--out")
    args = parser.parse_args(argv)
    store = ProfileStore(store=Path(args.profiles_store) if args.profiles_store else None)
    try:
        if args.command == "profiles":
            return _profiles(args, store)
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
            from .engine.run import run_book

            report = run_book(args.book, args.out, args.settings, args.profile, store)
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

            result = compare_deliveries(Path(args.ours), Path(args.reference))
            text = json.dumps(result, indent=1, ensure_ascii=False)
            if args.out:
                Path(args.out).write_text(text + "\n", "utf-8")
            print(text[:4000])
            return 0
    except ProfileError as exc:
        print(f"Profile problems:\n{exc}", file=sys.stderr)
        return 1
    return 2


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
