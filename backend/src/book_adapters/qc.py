"""QC report and review list of one delivery (``<out>/report/``).

- ``qc_report.json`` / ``qc_report.html``: DTD result, house-rule findings by rule (with
  the guideline item), lossless result, element counts, profile identity, overrides used,
  the profile's "confirm with the client" settings, and a verdict:
  ``fail`` (not delivered, DTD errors, text lost or added, an unexplained character change),
  ``warn`` (house-rule findings, undeclared order exceptions, an override, an untested
  profile, settings to supply, items a person must check), else ``pass``.
- ``review_list.json`` / ``review_list.html``: every item a person must check: the adapter's
  review entries and Stage 1's review items for delivered text, ``must_check`` first, each
  with page, reason and a crop image from the publication (the Stage 1 crop of the unit, or
  the figure image) when the publication has one.

No time stamps: the same inputs give byte-identical files.
"""

from __future__ import annotations

import json
import shutil
import unicodedata
from collections import Counter
from pathlib import Path

import regex
from book_core.assembly.lossless import single_furniture_lines
from lxml import etree

from .compare.html import _e, _table, page
from .validate.declared import declared_changes

MUST_CHECK_KINDS = frozenset({"alt_text", "settings"})


def severity(entry: dict) -> str:
    if entry.get("severity"):
        return entry["severity"]
    if entry["kind"] in MUST_CHECK_KINDS:
        return "must_check"
    if entry["kind"] == "adapter-inferred" and (entry.get("rule") or "").startswith("outline."):
        return "must_check"  # part/chapter starts and titles the adapter inferred
    return "needs_review"


HYPHEN_SPACE = regex.compile(r"(?<=[\p{L}\p{M}])-( )(?=[\p{L}\p{M}])")
# "pre- and post-operative": a hyphen and a space before one of these words is a suspended hyphen
SUSPENDED_BEFORE = ("and", "or", "to", "nor")
HYPHEN_SPACE_QUESTION = "Hyphen followed by a space"


def hyphen_space_items(book, profile) -> list[dict]:
    """Review items for a hyphen followed by a space inside a text ("acid- base", "non-
    judgmental"). Such a space is in the PDF's own text layer, so it is never rewritten
    automatically: each place is offered to a person ("remove the space?", one click, recorded
    in the audit log). The profile setting ``characters.hyphen_space`` turns the items off
    (``off``; the default is ``review``). Only a unit's own text is offered (the fix edits it).
    When the same compound is written without the space elsewhere in the book, the item says so."""
    if profile is not None and profile.get("characters.hyphen_space", "review") == "off":
        return []
    from .engine.joins import vocabulary

    skip = set(profile.get("characters.hyphen_space_skip_before", SUSPENDED_BEFORE) if profile else SUSPENDED_BEFORE)
    _, compounds = vocabulary(book.records.values())
    out = []
    for addr, content in book.records.items():
        unit = book.units.get(addr)
        if not unit or not unit.get("pages"):
            continue  # a marker, a cell, a caption or a note: the fix edits a unit's own text
        text = content.get("text") or ""
        for m in HYPHEN_SPACE.finditer(text):
            at = m.start(1)
            before = regex.search(r"[\p{L}\p{M}]+$", text[: at - 1])
            after = regex.match(r"[\p{L}\p{M}]+", text[at + 1 :])
            if not before or not after or after.group().casefold() in skip:
                continue
            joined = f"{before.group()}-{after.group()}"
            known = compounds[unicodedata.normalize("NFKC", joined).casefold()] > 0
            page = unit["pages"][0]
            out.append({
                "source": "adapter", "severity": "needs_review", "kind": "character",
                "page": page, "page_label": _label(book, page), "unit": addr,
                "reason": f"{HYPHEN_SPACE_QUESTION} at offset {at}: “{before.group()}- {after.group()}”"
                          + (f" (written “{joined}” elsewhere in the book)" if known else "")
                          + ": remove the space?",
                "rule": "hyphen_space", "crop": None,
            })  # fmt: skip
    return out


def review_items(adapter_reviews: list[dict], book, profile=None) -> list[dict]:
    """Adapter entries (deduplicated) and Stage 1 items, with page and crop source."""
    stage1 = (book.data.get("review") or {}).get("items") or []
    crop_of_unit: dict[str, str] = {}
    for item in stage1:
        if item.get("unit") and item.get("crop"):
            crop_of_unit.setdefault(item["unit"], item["crop"])
    out, seen = [], set()
    for entry in adapter_reviews:
        key = (entry["kind"], entry["message"], entry.get("unit"))
        if key in seen:
            continue
        seen.add(key)
        unit = book.units.get(entry.get("unit") or "") or {}
        page = entry.get("page") or (unit.get("pages") or [None])[0]
        crop = crop_of_unit.get(entry.get("unit") or "")
        if crop is None and (unit.get("image") or {}).get("file"):
            crop = f"images/{unit['image']['file']}"  # the figure itself
        out.append(
            {
                "source": "adapter",
                "severity": severity(entry),
                "kind": entry["kind"],
                "page": page,
                "page_label": _label(book, page),
                "unit": entry.get("unit"),
                "reason": entry["message"],
                "rule": entry.get("rule"),
                "crop": crop,
            }
        )
    out.extend(hyphen_space_items(book, profile))
    for item in stage1:
        if item.get("kind") == "alt_text":
            continue  # the adapter lists every alt-text placeholder it wrote
        out.append(
            {
                "source": "Stage 1",
                "severity": item.get("severity") or "needs_review",
                "kind": item.get("kind"),
                "page": item.get("page"),
                "page_label": _label(book, item.get("page")),
                "unit": item.get("unit"),
                "reason": item.get("reason")
                + (f" ({item['action']})" if item.get("action") else ""),
                "rule": None,
                "crop": item.get("crop"),
            }
        )
    rank = {"must_check": 0, "needs_review": 1}
    out.sort(
        key=lambda r: (
            rank.get(r["severity"], 2),
            r["page"] if r["page"] is not None else 10**9,
            r["source"],
            r["kind"] or "",
            r["unit"] or "",
            r["reason"],
        )
    )
    return out



def _split_text(split) -> str:
    if not split:
        return "not checked"
    return (f"{split['split']} split, {split['unjoined_known_word']} written apart though the word is in "
            f"the book, {split['unjoined_other']} not a continuation, of {split['soft_hyphen_line_ends']} "
            "soft-hyphen line ends")


def _label(book, page):
    if not page or page > len(book.pages):
        return None
    return book.pages[page - 1].get("label")


def verdict(report: dict) -> tuple[str, list[str]]:
    fail, warn = [], []
    checks = report.get("checks") or {}
    if report["status"] != "written":
        fail.append(f"delivery not written: {report['status']}")
    dtd = checks.get("dtd") or {}
    if dtd.get("errors"):
        fail.append(f"{dtd['errors']} DTD error(s)")
    loss = checks.get("lossless") or {}
    if loss and (loss.get("missing") or loss.get("extra")):
        fail.append(f"lossless: {loss['missing']} missing, {loss['extra']} extra token(s)")
    if loss and not loss.get("output", {}).get("matches_ledger", True):
        fail.append("the written XML does not match the emission ledger")
    chars = loss.get("character_changes") or {}
    if chars.get("unexplained"):
        fail.append(f"{chars['unexplained']} written text(s) differ from source + recorded changes")
    split = loss.get("split_words") or {}
    if split.get("split"):
        fail.append(f"{split['split']} word(s) the source joins across a line end are written in two parts")
    if split.get("unjoined_known_word"):
        warn.append(f"{split['unjoined_known_word']} line-end hyphenated word(s) written apart, though the "
                    "whole word is in the book")
    singles = loss.get("furniture_singletons") or {}
    if singles.get("count"):
        pages = ", ".join(str(e["page"]) for e in singles["examples"][:6])
        warn.append(f"{singles['count']} running head/foot line(s) printed once while the others repeat "
                    f"(a title read as page furniture?): page {pages}")
    house = checks.get("house_rules") or {}
    if house.get("violations"):
        failed = [k for k, v in house["checks"].items() if v["violations"]]
        warn.append(f"{house['violations']} house-rule finding(s): {', '.join(failed)}")
    order = loss.get("order") or {}
    if order.get("undeclared_out_of_order"):
        warn.append(f"{order['undeclared_out_of_order']} text piece(s) out of book order")
    declared = report.get("declared") or {}
    if declared.get("added"):
        warn.append(f"{len(declared['added'])} block(s) of words added by hand "
                    f"({declared['added_tokens']} words): listed in the QC report")
    if declared.get("removed"):
        warn.append(f"{len(declared['removed'])} block(s) removed from the book by a reviewer "
                    f"({declared['removed_tokens']} words): listed in the QC report")
    if report["alt_text"].get("override"):
        warn.append(f"exported with {report['alt_text']['placeholders']} alt-text placeholder(s)")
    if report["profile"].get("status") == "untested":
        warn.append("the profile is untested")
    if report["settings"].get("to_supply"):
        warn.append("book settings to supply: " + ", ".join(report["settings"]["to_supply"]))
    must = report.get("review_severity", {}).get("must_check", 0)
    if must:
        warn.append(f"{must} item(s) a person must check (review list)")
    if fail:
        return "fail", fail + warn
    return ("warn" if warn else "pass"), warn


def element_counts(main_file: Path) -> dict[str, int]:
    parser = etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)
    try:
        root = etree.parse(str(main_file), parser).getroot()
    except etree.XMLSyntaxError:  # an HTML5 page (void elements): read with the strict HTML reader
        from .validate.format_checks import parse_html

        root = parse_html(Path(main_file).read_bytes())[0]
    c = Counter(e.tag for e in root.iter() if isinstance(e.tag, str))
    return dict(sorted(c.items()))


def confirm_settings(profile) -> list[dict]:
    out = []
    for item in profile.get("confirm_with_client") or []:
        out.append(
            {"field": item["field"], "value": profile.get(item["field"]), "note": item["note"]}
        )
    return out


def copy_crops(items: list[dict], book, report_dir: Path) -> None:
    """Copy each item's crop image next to the report (``review_crops/``)."""
    crops_dir = report_dir / "review_crops"
    if crops_dir.exists():
        shutil.rmtree(crops_dir)
    for item in items:
        src = item["crop"]
        if not src:
            continue
        path = book.folder / src
        if not path.is_file():
            item["crop"] = None
            continue
        target = crops_dir / Path(src).name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        item["crop"] = f"review_crops/{target.name}"


def write(report_dir: Path, report: dict, reviews: list[dict], profile, book, root) -> dict:
    """Write the QC report and the review list; returns the QC report."""
    items = review_items(reviews, book, profile)
    report["declared"] = declared_changes(book.data)
    report["review_severity"] = dict(sorted(Counter(i["severity"] for i in items).items()))
    copy_crops(items, book, report_dir)
    checks = report.get("checks") or {}
    if checks.get("lossless") is not None:  # page lines printed once (see lossless.single_furniture_lines)
        checks["lossless"]["furniture_singletons"] = single_furniture_lines(book.data)
    v, reasons = verdict(report)
    loss = checks.get("lossless") or {}
    qc = {
        "verdict": v,
        "reasons": reasons,
        "book": report["book"],
        "profile": report["profile"],
        "status": report["status"],
        "dtd": {k: checks.get("dtd", {}).get(k) for k in ("dtd", "files", "errors", "by_file")},
        "house_rules": {
            "violations": checks.get("house_rules", {}).get("violations"),
            "by_rule": {
                name: {
                    "item": c["item"],
                    "checked": c["checked"],
                    "violations": c["violations"],
                    "examples": c["examples"],
                }
                for name, c in sorted((checks.get("house_rules", {}).get("checks") or {}).items())
            },
        },  # fmt: skip
        "lossless": {
            "tokens": loss.get("coverage", {}).get("tokens"),
            "missing": loss.get("missing"),
            "extra": loss.get("extra"),
            "omitted_by_reason": loss.get("coverage", {}).get("omitted_by_reason"),
            "declared_moves": loss.get("order", {}).get("declared_moves"),
            "undeclared_out_of_order": loss.get("order", {}).get("undeclared_out_of_order"),
            "furniture_singletons": loss.get("furniture_singletons"),
            "xml_matches_ledger": loss.get("output", {}).get("matches_ledger"),
            "declared_removed_words": report["declared"]["removed_tokens"],
            "declared_added_words": report["declared"]["added_tokens"],
            "character_changes": {
                k: loss.get("character_changes", {}).get(k)
                for k in ("changes", "by_rule", "texts_checked", "unexplained")
            },
            "split_words": {
                k: (loss.get("split_words") or {}).get(k)
                for k in ("soft_hyphen_line_ends", "joined", "split", "unjoined_known_word",
                          "unjoined_other", "examples")
            },
        },
        "element_counts": element_counts(Path(root) / report["delivery"]["main_file"])
        if root
        else {},
        "overrides": {
            "alt_text_placeholders": report["alt_text"]["placeholders"]
            if report["alt_text"].get("override")
            else 0,
            "profile_upload": report["profile"].get("origin") != "builtin",
        },
        "declared_changes": {k: report["declared"][k] for k in ("removed", "added")},
        "confirm_with_client": confirm_settings(profile),
        "authors": report.get("authors"),
        "settings_to_supply": report["settings"].get("to_supply"),
        "warnings": report["warnings"],
        "review": {
            "items": len(items),
            "by_severity": report["review_severity"],
            "by_kind": dict(sorted(Counter(f"{i['source']}: {i['kind']}" for i in items).items())),
        },
    }
    dump = json.dumps(qc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    (report_dir / "qc_report.json").write_text(dump, "utf-8")
    (report_dir / "qc_report.html").write_text(qc_html(qc), "utf-8")
    (report_dir / "review_list.json").write_text(
        json.dumps(items, indent=1, sort_keys=True, ensure_ascii=False) + "\n", "utf-8"
    )
    (report_dir / "review_list.html").write_text(review_html(items, qc), "utf-8")
    return qc


def declared_sections(qc: dict) -> list[tuple[str, str]]:
    """The sections for the blocks a reviewer removed or typed (only when there are any)."""
    out = []
    declared = qc.get("declared_changes") or {}
    for key, title in (("added", "Words added by hand (declared additions)"),
                       ("removed", "Blocks removed from the book (declared removals)")):  # fmt: skip
        rows = declared.get(key) or []
        if rows:
            out.append((title, _table(
                ["Page", "Text", "By", "Kind"],
                [[r["page"], _e(r["text"]), _e(r["who"] or ""), _e((r["block"] or "").replace("_", " "))]
                 for r in rows],
                {0},
            )))  # fmt: skip
    return out


def declared_line(qc: dict) -> str:
    loss = qc["lossless"]
    add, rem = loss.get("declared_added_words") or 0, loss.get("declared_removed_words") or 0
    if not (add or rem):
        return ""
    parts = ([f"{add} word(s) added by hand"] if add else []) + ([f"{rem} word(s) removed on purpose"] if rem else [])
    return " (declared: " + ", ".join(parts) + ")"


def _severity_text(counts: dict) -> str:
    return f"{counts.get('must_check', 0)} must check, {counts.get('needs_review', 0)} to review"


def qc_html(qc: dict) -> str:
    colour = {"pass": "#1e7b34", "warn": "#9a6700", "fail": "#b42318"}[qc["verdict"]]
    prof = qc["profile"]
    reasons = "".join(f"<li>{_e(r)}</li>" for r in qc["reasons"])
    intro = (
        f"<p style='font-size:18px'><b style='color:{colour}'>{qc['verdict'].upper()}</b> "
        f"&middot; {_e(qc['book']['folder'])} &middot; profile {_e(prof['ref'])} "
        f"({_e(prof['status'])}, sha256 {_e(prof['resolved_sha256'][:12])}…)</p>"
        + (f"<ul>{reasons}</ul>" if reasons else "")
        + "<p><a href='review_list.html'>Review list</a> "
        f"({qc['review']['items']} items: {_severity_text(qc['review']['by_severity'])})</p>"
    )
    loss = qc["lossless"]
    checks = _table(
        ["Check", "Result"],
        [
            ["DTD", f"{qc['dtd']['errors']} error(s) in {qc['dtd']['files']} file(s)"],
            ["House rules", f"{qc['house_rules']['violations']} finding(s)"],
            [
                "Lossless",
                f"{loss['missing']} missing, {loss['extra']} extra of {loss['tokens']} tokens"
                + declared_line(qc),
            ],
            ["XML matches the ledger", _e(loss["xml_matches_ledger"])],
            ["Split words", _split_text(loss.get("split_words"))],
            ["Character changes", f"{loss['character_changes']['changes']} recorded, "
             f"{loss['character_changes']['unexplained']} unexplained"],
            ["Out of book order (undeclared)", _e(loss["undeclared_out_of_order"])],
        ],
    )  # fmt: skip
    house = _table(
        ["Rule", "Guideline item", "Checked", "Findings", "Examples"],
        [
            [_e(k), _e(v["item"]), v["checked"], v["violations"], _e("; ".join(v["examples"][:3]))]
            for k, v in qc["house_rules"]["by_rule"].items()
        ],
        {2, 3},
    )
    omitted = _table(
        ["Not delivered (by profile)", "Tokens"],
        [[_e(k), v] for k, v in (loss["omitted_by_reason"] or {}).items()],
        {1},
    )
    moves = _table(
        ["Declared move", "Text pieces"],
        [[_e(k), v] for k, v in (loss["declared_moves"] or {}).items()],
        {1},
    )
    chars = _table(
        ["Character rule", "Changes"],
        [[_e(k), v] for k, v in (loss["character_changes"]["by_rule"] or {}).items()],
        {1},
    )
    confirm = _table(
        ["Setting", "Value", "Why it needs confirming"],
        [[_e(c["field"]), _e(json.dumps(c["value"], ensure_ascii=False)), _e(c["note"])]
         for c in qc["confirm_with_client"]],
    )  # fmt: skip
    counts = _table(
        ["Element", "Count"], [[_e(k), v] for k, v in qc["element_counts"].items()], {1}
    )
    overrides = _table(["Override", "Value"], [[_e(k), _e(v)] for k, v in qc["overrides"].items()])
    return page(
        "QC report",
        [
            ("Checks", checks),
            ("House rules", house),
            ("Lossless", omitted + moves + chars),
            *declared_sections(qc),
            ("Overrides", overrides),
            ("Confirm with the client", confirm),
            ("Warnings", "<ul>" + "".join(f"<li>{_e(w)}</li>" for w in qc["warnings"]) + "</ul>"),
            ("Element counts", counts),
        ],
        intro,
    )


def review_html(items: list[dict], qc: dict) -> str:
    rows = []
    for i in items:
        crop = (
            f"<a href='{_e(i['crop'])}'><img src='{_e(i['crop'])}' alt='crop' "
            "style='max-width:280px;max-height:180px'></a>"
            if i["crop"]
            else "<span class='muted'>no crop in the publication</span>"
        )
        page_text = f"{i['page']}" + (f" ({_e(i['page_label'])})" if i["page_label"] else "")
        rows.append(
            [
                "<b>must check</b>" if i["severity"] == "must_check" else "review",
                page_text if i["page"] else "",
                _e(i["source"]),
                _e(i["kind"]),
                _e(i["reason"]),
                crop,
            ]
        )
    intro = (
        f"<p>{_e(qc['book']['folder'])} &middot; {len(items)} items "
        f"({_severity_text(qc['review']['by_severity'])}). Pages are physical pages "
        "(printed label in brackets). <a href='qc_report.html'>QC report</a></p>"
    )
    return page(
        "Review list",
        [("Items", _table(["Severity", "Page", "From", "Kind", "Reason", "Crop"], rows))],
        intro,
    )
