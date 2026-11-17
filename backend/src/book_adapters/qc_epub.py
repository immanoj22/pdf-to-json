"""QC report of one ePub (``<out>/report/qc_report.json`` / ``.html`` plus the review list).

Verdict: ``fail`` when the ePub was not written, one of our checks has a finding, text was lost
or added, a written text differs from its source by more than the recorded character changes,
or EPUBCheck reports an error. ``warn`` for an alt-text override, an untested profile, settings
to supply, must-check items, EPUBCheck warnings or EPUBCheck not run. Else ``pass``.
No time stamps: the same inputs give byte-identical files."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .compare.html import _e, _table, page
from .validate.declared import declared_changes
from .qc import (
    _severity_text,
    confirm_settings,
    copy_crops,
    declared_line,
    declared_sections,
    review_html,
    review_items,
)


def verdict(report: dict) -> tuple[str, list[str]]:
    fail, warn = [], []
    checks = report.get("checks") or {}
    own = checks.get("epub") or {}
    if report["status"] != "written":
        fail.append(f"ePub not written: {report['status']}")
    for name, c in (own.get("checks") or {}).items():
        if c["violations"]:
            fail.append(f"{c['violations']} finding(s) in check {name} ({c['item']})")
    loss = own.get("lossless") or {}
    if loss and (loss.get("missing") or loss.get("extra")):
        fail.append(f"lossless: {loss['missing']} missing, {loss['extra']} extra token(s)")
    if loss and not loss.get("output", {}).get("matches_ledger", True):
        fail.append("the written pages do not match the emission ledger")
    chars = loss.get("character_changes") or {}
    if chars.get("unexplained"):
        fail.append(f"{chars['unexplained']} written text(s) differ from source + recorded changes")
    ec = checks.get("epubcheck") or {}
    if ec.get("status") == "run":
        if ec["errors"]:
            fail.append(f"EPUBCheck: {ec['errors']} error(s)")
        if ec["warnings"]:
            warn.append(f"EPUBCheck: {ec['warnings']} warning(s)")
    else:
        warn.append("EPUBCheck not run: " + ec.get("reason", "no result"))
    if (loss.get("order") or {}).get("undeclared_out_of_order"):
        warn.append(f"{loss['order']['undeclared_out_of_order']} text piece(s) out of book order")
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
    if not report.get("profile_has_epub"):
        warn.append("the profile has no epub section: defaults used")
    if report["settings"].get("to_supply"):
        warn.append("book settings to supply: " + ", ".join(report["settings"]["to_supply"]))
    must = report.get("review_severity", {}).get("must_check", 0)
    if must:
        warn.append(f"{must} item(s) a person must check (review list)")
    if fail:
        return "fail", fail + warn
    return ("warn" if warn else "pass"), warn


def write(report_dir: Path, report: dict, reviews: list[dict], profile, book, epub_path) -> dict:
    items = review_items(reviews, book)
    report["declared"] = declared_changes(book.data)
    report["review_severity"] = dict(sorted(Counter(i["severity"] for i in items).items()))
    copy_crops(items, book, report_dir)
    v, reasons = verdict(report)
    checks = report.get("checks") or {}
    own = checks.get("epub") or {}
    loss = own.get("lossless") or {}
    counts = dict(own.get("counts") or {})
    element_counts = counts.pop("element_counts", {})
    qc = {
        "format": "epub",
        "verdict": v,
        "reasons": reasons,
        "book": report["book"],
        "profile": report["profile"],
        "status": report["status"],
        "own_checks": {
            name: {k: c[k] for k in ("item", "checked", "violations", "examples")}
            for name, c in sorted((own.get("checks") or {}).items())
        },
        "epubcheck": checks.get("epubcheck") or {"status": "not run", "reason": "no result"},
        "lossless": {
            "tokens": loss.get("coverage", {}).get("tokens"),
            "missing": loss.get("missing"),
            "extra": loss.get("extra"),
            "omitted_by_reason": loss.get("coverage", {}).get("omitted_by_reason"),
            "declared_moves": loss.get("order", {}).get("declared_moves"),
            "undeclared_out_of_order": loss.get("order", {}).get("undeclared_out_of_order"),
            "xml_matches_ledger": loss.get("output", {}).get("matches_ledger"),
            "declared_removed_words": report["declared"]["removed_tokens"],
            "declared_added_words": report["declared"]["added_tokens"],
            "character_changes": {
                k: loss.get("character_changes", {}).get(k)
                for k in ("changes", "by_rule", "texts_checked", "unexplained")
            },
        },
        "counts": counts,
        "element_counts": element_counts,
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
    (report_dir / "qc_report.json").write_text(
        json.dumps(qc, indent=1, sort_keys=True, ensure_ascii=False) + "\n", "utf-8"
    )
    (report_dir / "qc_report.html").write_text(qc_html(qc), "utf-8")
    (report_dir / "review_list.json").write_text(
        json.dumps(items, indent=1, sort_keys=True, ensure_ascii=False) + "\n", "utf-8"
    )
    (report_dir / "review_list.html").write_text(review_html(items, qc), "utf-8")
    return qc


def qc_html(qc: dict) -> str:
    colour = {"pass": "#1e7b34", "warn": "#9a6700", "fail": "#b42318"}[qc["verdict"]]
    prof = qc["profile"]
    reasons = "".join(f"<li>{_e(r)}</li>" for r in qc["reasons"])
    intro = (
        f"<p style='font-size:18px'><b style='color:{colour}'>{qc['verdict'].upper()}</b> "
        f"&middot; ePub &middot; {_e(qc['book']['folder'])} &middot; profile {_e(prof['ref'])} "
        f"({_e(prof['status'])})</p>"
        + (f"<ul>{reasons}</ul>" if reasons else "")
        + "<p><a href='review_list.html'>Review list</a> "
        f"({qc['review']['items']} items: {_severity_text(qc['review']['by_severity'])})</p>"
    )
    ec = qc["epubcheck"]
    ec_text = (
        f"EPUBCheck {_e(ec.get('version'))}: {ec['errors']} error(s), {ec['warnings']} warning(s)"
        if ec.get("status") == "run"
        else "not run: " + _e(ec.get("reason"))
    )
    loss = qc["lossless"]
    own = _table(
        ["Check", "Rule", "Checked", "Findings", "Examples"],
        [
            [_e(k), _e(v["item"]), v["checked"], v["violations"], _e("; ".join(v["examples"][:3]))]
            for k, v in qc["own_checks"].items()
        ],
        {2, 3},
    )
    summary = _table(
        ["Check", "Result"],
        [
            ["EPUBCheck", ec_text],
            ["Lossless", f"{loss['missing']} missing, {loss['extra']} extra of {loss['tokens']} tokens" + declared_line(qc)],  # noqa: E501
            ["Pages match the ledger", _e(loss["xml_matches_ledger"])],
            ["Character changes", f"{loss['character_changes']['changes']} recorded, "
             f"{loss['character_changes']['unexplained']} unexplained"],
        ],
    )  # fmt: skip
    counts = _table(
        ["Count", "Value"],
        [[_e(k), _e(v)] for k, v in qc["counts"].items() if isinstance(v, (int, str))],
    )
    elements = _table(
        ["Element", "Count"], [[_e(k), v] for k, v in qc["element_counts"].items()], {1}
    )
    confirm = _table(
        ["Setting", "Value", "Why it needs confirming"],
        [[_e(c["field"]), _e(json.dumps(c["value"], ensure_ascii=False)), _e(c["note"])]
         for c in qc["confirm_with_client"]],
    )  # fmt: skip
    return page(
        "ePub QC report",
        [
            ("Checks", summary),
            ("Our checks", own),
            *declared_sections(qc),
            ("Counts", counts),
            ("Confirm with the client", confirm),
            ("Warnings", "<ul>" + "".join(f"<li>{_e(w)}</li>" for w in qc["warnings"]) + "</ul>"),
            ("Elements", elements),
        ],
        intro,
    )
