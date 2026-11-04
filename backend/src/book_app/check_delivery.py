"""Check an edited delivery: DTD, Jaypee house rules and, against the book's text, what was
removed or added. The user's files are never changed: the ZIP is unpacked into a folder of
its own and only read."""

from __future__ import annotations

import html
import json
import shutil
import types
import zipfile
from collections import Counter
from pathlib import Path

from lxml import etree

from book_adapters.compare.html import _e, _table, page
from book_adapters.qc import element_counts
from book_adapters.validate import dtd, house_rules, lossless

from .jobs import JobError, now, write_json

MAX_MEMBERS = 50_000
MAX_UNPACKED = 4_000_000_000


def safe_extract(zip_path: Path, dest: Path) -> int:
    """Unpack without trusting names: no absolute paths, no '..', no links, bounded size."""
    dest.mkdir(parents=True, exist_ok=True)
    total = count = 0
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise JobError(400, "This is not a ZIP file, or it is damaged.", "bad_zip") from exc
    with zf:
        for info in zf.infolist():
            name = info.filename
            parts = Path(name).parts
            if name.startswith(("/", "\\")) or ".." in parts or (parts and ":" in parts[0]):
                raise JobError(400, f"The ZIP has an unsafe file name: {name!r}.", "unsafe_zip")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise JobError(400, "The ZIP contains a link, which is not allowed.", "unsafe_zip")
            count += 1
            total += info.file_size
            if count > MAX_MEMBERS or total > MAX_UNPACKED:
                raise JobError(413, "The ZIP is too large to check.", "zip_too_large")
            target = dest.joinpath(*parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return count


def find_root(folder: Path) -> tuple[Path, Path] | None:
    """(delivery root, main file): the shallowest XML file whose root element is <book>."""
    parser = etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False, recover=True)
    candidates = sorted(
        (p for p in folder.rglob("*.xml") if "__MACOSX" not in p.parts),
        key=lambda p: (len(p.relative_to(folder).parts), str(p)),
    )
    for path in candidates:
        try:
            root = etree.parse(str(path), parser).getroot()
        except (etree.XMLSyntaxError, OSError):
            continue
        if root is not None and root.tag == "book":
            return path.parent, path
    return None


def run_check(zip_path: Path, work: Path, expected, profile, book_label: str | None) -> dict:
    """``expected`` is None, or (doc, delivery, book): the converter's own export of the book
    with the same profile, used for house rules and the text comparison."""
    files_dir = work / "files"
    if files_dir.exists():
        shutil.rmtree(files_dir)
    n_files = safe_extract(zip_path, files_dir)
    found = find_root(files_dir)
    result: dict = {"at": now(), "zip_files": n_files, "book": book_label}
    if found is None:
        result.update(
            verdict="fail",
            reasons=["No main DocBook file (a <book> XML file) was found in the ZIP."],
            dtd=None,
            house_rules=None,
            text=None,
        )
        return result
    root, main = found
    rels = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.xml"))
    result["main_file"] = main.relative_to(root).as_posix()
    result["dtd"] = dtd.validate_delivery(root, rels)
    reasons_fail, reasons_warn = [], []
    if result["dtd"]["errors"]:
        reasons_fail.append(f"{result['dtd']['errors']} DTD error(s)")
    result["element_counts"] = element_counts(main)
    if expected is None:
        result["house_rules"] = None
        result["text"] = None
        result["notes"] = ["House rules and the text comparison need the book it was made from."]
    else:
        doc, delivery, book = expected
        stub = types.SimpleNamespace(**{k: getattr(delivery, k) for k in vars(delivery)})
        stub.main_file = main.relative_to(root).as_posix()
        try:
            house = house_rules.run(root, stub, doc, book, profile)
            result["house_rules"] = {
                "violations": house.get("violations"),
                "by_rule": {
                    name: {
                        "item": c["item"],
                        "checked": c["checked"],
                        "violations": c["violations"],
                        "examples": c["examples"],
                    }
                    for name, c in sorted((house.get("checks") or {}).items())
                },
            }
            if house.get("violations"):
                bad = [k for k, v in house["checks"].items() if v["violations"]]
                reasons_warn.append(
                    f"{house['violations']} house-rule finding(s): {', '.join(bad)}"
                )
        except Exception as error:  # a heavily edited file can break a structural check
            result["house_rules"] = {
                "violations": None,
                "error": f"{type(error).__name__}: {error}",
            }
            reasons_warn.append("The house-rule check could not run on these files.")
        try:
            ours = Counter(lossless._ledger_tokens(delivery.ledger))
            theirs = Counter(lossless.xml_tokens(main))
            removed, added = ours - theirs, theirs - ours
            result["text"] = {
                "compared_with": "the converter's own text of this book",
                "tokens_converter": sum(ours.values()),
                "tokens_edited": sum(theirs.values()),
                "removed": sum(removed.values()),
                "added": sum(added.values()),
                "removed_examples": [w for w, _ in removed.most_common(20)],
                "added_examples": [w for w, _ in added.most_common(20)],
            }
            if removed or added:
                reasons_warn.append(
                    f"text differs from the converter's: {sum(removed.values())} word(s) removed, "
                    f"{sum(added.values())} added (expected if you edited the text)"
                )
        except Exception as error:
            result["text"] = {"error": f"{type(error).__name__}: {error}"}
            reasons_warn.append("The text could not be compared.")
    result["reasons"] = reasons_fail + reasons_warn
    result["verdict"] = "fail" if reasons_fail else ("warn" if reasons_warn else "pass")
    return result


def render_html(result: dict, name: str) -> str:
    colour = {"pass": "#1e7b34", "warn": "#9a6700", "fail": "#b42318"}[result["verdict"]]
    reasons = "".join(f"<li>{_e(r)}</li>" for r in result.get("reasons", []))
    intro = (
        f"<p style='font-size:18px'><b style='color:{colour}'>{result['verdict'].upper()}</b> "
        f"&middot; {_e(name)}</p><ul>{reasons}</ul>"
        "<p class='muted'>Your files were only read; nothing was changed.</p>"
    )
    sections = []
    if result.get("dtd"):
        d = result["dtd"]
        rows = [
            [_e(f), v["errors"], _e("; ".join(v["first"][:2]))] for f, v in d["by_file"].items()
        ]
        sections.append(
            (
                "DTD",
                f"<p>{d['errors']} error(s) in {d['files']} file(s). {_e(d['dtd'])}</p>"
                + (_table(["File", "Errors", "First"], rows, {1}) if rows else ""),
            )
        )
    house = result.get("house_rules")
    if house and house.get("by_rule"):
        sections.append(
            (
                "House rules",
                _table(
                    ["Rule", "Guideline item", "Checked", "Findings", "Examples"],
                    [
                        [
                            _e(k),
                            _e(v["item"]),
                            v["checked"],
                            v["violations"],
                            _e("; ".join(v["examples"][:3])),
                        ]
                        for k, v in house["by_rule"].items()
                    ],
                    {2, 3},
                ),
            )
        )
    text = result.get("text")
    if text and "removed" in text:
        sections.append(
            (
                "Text",
                f"<p>{_e(text['compared_with'])}: {text['removed']} word(s) removed, "
                f"{text['added']} added.</p>"
                f"<p>Removed: {_e(', '.join(text['removed_examples']))}</p>"
                f"<p>Added: {_e(', '.join(text['added_examples']))}</p>",
            )
        )
    if result.get("element_counts"):
        sections.append(
            (
                "Element counts",
                _table(
                    ["Element", "Count"],
                    [[_e(k), v] for k, v in result["element_counts"].items()],
                    {1},
                ),
            )
        )
    return page("Check of an edited delivery", sections, intro)


def save(work: Path, result: dict, name: str) -> None:
    write_json(work / "check.json", result)
    (work / "check.html").write_text(render_html(result, html.unescape(name)), "utf-8")


__all__ = ["run_check", "save", "safe_extract", "find_root", "json"]
