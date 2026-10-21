"""Step 14b navigation development check: old (HEAD) vs new printed-navigation decisions.

The cached Step 10 pass-1 evidence of each book gets the new per-line entry evidence
(``structure.features.line_entries``) computed from the cached Step 9 units, layout and span
store, exactly as the evidence pass now records it; then the whole-book structure decision
runs with the navigation module at the 14a commit and with the current one. Navigation
kinds per page and the headings decided are compared; every changed page is listed.

Usage: python step14b_navigation.py [--book NAME] [--base d590e9d]
"""

# ruff: noqa: E402
import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
from step9_run import CACHE9
from step10_run import CACHE10

from book_core.cache_store import read_json
from book_core.paragraphs.geometry import frame
from book_core.structure import decide
from book_core.structure.evidence import _read
from book_core.structure.features import line_entries

OUT = ROOT / "experiments/out/step14b/navigation"


def old_navigation(base):
    source = subprocess.run(
        ["git", "show", f"{base}:backend/src/book_core/structure/navigation.py"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout  # fmt: skip
    path = OUT / "_navigation_base.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, "utf-8", newline="\n")
    spec = importlib.util.spec_from_file_location("navigation_base", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path.unlink()
    return module


def evidence_with_lines(book):
    keys = common.keys(book)
    evidence = _read(
        CACHE10 / "structure/evidence" / f"{keys['structure_evidence']}.json.gz",
        keys["structure_evidence"],
    )
    for page in evidence["pages"]:
        number = page["page"]
        layout = common.layout_page(book, number)
        store = common.text_page(book, number).store
        entry = read_json(CACHE9 / "paragraphs/page" / keys["paragraphs"] / f"{number}.json")
        import json

        units = {u["id"]: u["line_ids"] for u in json.loads(entry["payload"])["units"]}
        lines = {line.id: line for line in layout.lines}
        frames = {lid: frame(line) for lid, line in lines.items()}
        for unit in page["units"]:
            unit["line_entries"] = line_entries(store, lines, frames, units[unit["unit"]])
    return evidence


def decided(evidence, classify):
    decide.classify = classify
    result = decide.decide_book(evidence, dict(decide.DEFAULT_CONFIG))
    kinds = {n.page: n.kind for n in result["navigation_pages"]}
    headings = {(h.page, tuple(h.unit_ids)) for h in result["headings"]}
    return kinds, headings, result


def check(book, base):
    old = old_navigation(base)
    evidence = evidence_with_lines(book)
    new_classify = decide.classify
    try:
        kinds_old, heads_old, _ = decided(evidence, old.classify)
        kinds_new, heads_new, result = decided(evidence, new_classify)
    finally:
        decide.classify = new_classify
    pages = sorted(set(kinds_old) | set(kinds_new))
    changed = [
        {"page": n, "before": kinds_old.get(n), "after": kinds_new.get(n),
         "reasons": next((p.reasons for p in result["navigation_pages"] if p.page == n), [])}
        for n in pages if kinds_old.get(n) != kinds_new.get(n)
    ]  # fmt: skip
    gone = sorted(heads_old - heads_new)
    added = sorted(heads_new - heads_old)
    by_kind = {}
    for kinds, label in ((kinds_old, "before"), (kinds_new, "after")):
        for kind in kinds.values():
            by_kind.setdefault(kind, {"before": 0, "after": 0})[label] += 1
    row = {
        "book": book,
        "navigation_pages": {"before": len(kinds_old), "after": len(kinds_new)},
        "by_kind": by_kind,
        "changed_pages": changed,
        "kinds_after": {str(k): v for k, v in sorted(kinds_new.items())},
        "headings": {"before": len(heads_old), "after": len(heads_new),
                     "removed": [list(h) for h in gone], "added": [list(h) for h in added]},
    }  # fmt: skip
    common.write(OUT / f"{book}.json", row)
    print(book, row["navigation_pages"], [(c["page"], c["before"], c["after"]) for c in changed],
          "headings -", len(gone), "+", len(added), flush=True)  # fmt: skip
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--base", default="d590e9d")
    args = parser.parse_args()
    for name in [args.book] if args.book else common.BOOK_ORDER:
        check(name, args.base)
