"""``profile test``: try a profile YAML on example books against the client's deliveries.

Nothing is converted. Each example names an existing publication (the converter's output
folder), the client's finished delivery of the same book and, optionally, book settings.
The book is exported with the profile and compared with the delivery. The result lists the
differences a profile change can fix:

- DTD errors and house-rule findings;
- file names (digits generalised: ``Chapters/chN.xml``, ``Chapters/images/N-N.jpg``) present
  on one side only;
- id patterns per element (``chNlevNsecN``) present on one side only;
- attribute values (role, mark, numeration, frame) that one side never uses;
- elements the reference uses and the delivery never writes (or the reverse);
- element-count differences the compare labels ``adapter`` or ``check``;
- page_info.xml.

Differences labelled Stage 1 or source are listed apart: no profile can fix them. The loop is
write YAML -> test -> adjust -> test until only those remain (exit code 0).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

from .compare import _main_file, _parse, compare_deliveries
from .engine.profile_store import ProfileStore
from .engine.run import run_book


def load_examples(path: Path) -> tuple[list[dict], Path, list[dict]]:
    """The examples file (``examples.yaml``, or a folder holding one). Paths are relative to
    the file, absolute, or use ${ENV} variables."""
    path = Path(path)
    file = path / "examples.yaml" if path.is_dir() else path
    data = yaml.safe_load(file.read_text("utf-8")) or {}
    out = []
    for ex in data.get("examples") or []:
        item = {"name": ex["name"]}
        for key in ("book", "delivery", "settings"):
            if ex.get(key):
                value = Path(os.path.expandvars(str(ex[key]))).expanduser()
                item[key] = value if value.is_absolute() else (file.parent / value).resolve()
        item["accept"] = ex.get("accept") or []
        out.append(item)
    return out, file, data.get("accept") or []


def _generalise(text: str) -> str:
    return re.sub(r"\d+", "N", text)


def _file_patterns(folder: Path) -> set[str]:
    return {_generalise(str(p.relative_to(folder))) for p in folder.rglob("*") if p.is_file()}


def _id_patterns(root) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for el in root.iter():
        if isinstance(el.tag, str) and el.get("id"):
            out.setdefault(el.tag, set()).add(_generalise(el.get("id")))
        if isinstance(el.tag, str) and el.tag == "title" and el.get("role"):
            out.setdefault("title@role", set()).add(_generalise(el.get("role")))
    return out


# elements whose presence depends on book.json content (index entries, sections...)
_STAGE1_ONLY = frozenset(
    {"section", "caption", "qandaset", "qandadiv", "qandaentry", "question", "answer",
     "variablelist", "varlistentry", "term", "glossary", "epigraph", "attribution", "subscript",
     "informaltable", "informalequation"}
)  # fmt: skip


def differences(root: Path, reference: Path, report: dict, cmp: dict, accept=()) -> dict:
    """Differences in three groups: ``fix`` (a profile value decides it), ``check`` (a
    person decides: a missing mapping, a field the schema lacks, or a delivery slip; an
    examples file can accept one with a reason) and ``stage1`` (book.json or the PDF decides
    it). ``accept``: [{what, why}] from the examples file."""
    from .compare.explain import DEFAULT_LABELS, INDEX_ELEMENTS

    ours_root, ref_root = _parse(_main_file(root)), _parse(_main_file(reference))
    has_index = ours_root.find(".//index") is not None
    fix: list[dict] = []
    check: list[dict] = []
    stage1: list[dict] = []
    checks = report.get("checks") or {}
    if checks.get("dtd", {}).get("errors"):
        fix.append({"what": "DTD errors", "detail": checks["dtd"]["by_file"]})
    for name, c in sorted((checks.get("house_rules", {}).get("checks") or {}).items()):
        if not c["violations"]:
            continue
        row = {"what": f"house rule {name} (item {c['item']})", "detail": c["examples"][:3]}
        # an id with a _2 suffix: one printed number twice in a chapter (merged chapters)
        dup = all(re.search(r"_\d+'?>?$|_\d+'", e) for e in c["examples"])
        (stage1 if dup and name.startswith("ids.") else fix).append(row)
    fa, fb = _file_patterns(root), _file_patterns(reference)
    only_a, only_b = sorted(fa - fb), sorted(fb - fa)
    if not has_index:
        moved = [f for f in only_b if "index" in f.lower()]
        if moved:
            stage1.append({"what": "file names", "only_reference": moved,
                           "why": "book.json has no index"})  # fmt: skip
            only_b = [f for f in only_b if f not in moved]
    if only_a or only_b:
        fix.append({"what": "file names", "only_ours": only_a, "only_reference": only_b})
    ia, ib = _id_patterns(ours_root), _id_patterns(ref_root)
    for tag in sorted(set(ia) | set(ib)):
        a, b = ia.get(tag, set()), ib.get(tag, set())
        dups = {x for x in a - b if x.endswith("_N") and re.sub(r"(_N)+$", "", x) in a | b}
        if dups:
            stage1.append({"what": f"{tag} ids with a uniqueness suffix", "ids": sorted(dups),
                           "why": "a printed number repeats inside one chapter"})  # fmt: skip
        a = a - dups
        if a and b and a != b:
            fix.append({"what": f"{tag} id patterns", "only_ours": sorted(a - b),
                        "only_reference": sorted(b - a)})  # fmt: skip
    for key, v in cmp["attribute_values_differing"].items():
        if (v["ours"] == 0) == (v["reference"] == 0):
            continue
        row = {"what": f"attribute value {key}", "ours": v["ours"], "reference": v["reference"]}
        tag = key.split("@")[0]
        one_side = (cmp["elements"].get(tag, {}).get("ours", 0) == 0) != (
            cmp["elements"].get(tag, {}).get("reference", 0) == 0
        )
        if re.search(r"@role=\d+$", key) or (one_side and tag in _STAGE1_ONLY):
            stage1.append(row)  # a list's start number, or an element book.json decides
        elif v["reference"] == 0:
            fix.append(row)  # a value only we write comes from the profile
        else:
            check.append(row)
    for tag, v in sorted(cmp["elements"].items()):
        if (v["ours"] == 0) == (v["reference"] == 0):
            continue
        row = {"what": f"element <{tag}> used on one side only", **v}
        label = DEFAULT_LABELS.get(tag, ("check", ""))[0]
        if tag in INDEX_ELEMENTS or tag in _STAGE1_ONLY or label in ("Stage 1", "source"):
            stage1.append(row)
        else:
            check.append(row)
    for d in cmp["biggest_differences"]:
        row = {"what": f"<{d['element']}> count", "ours": d["ours"], "reference": d["reference"],
               "label": d["label"], "why": d["why"]}  # fmt: skip
        {"adapter": fix, "check": check}.get(d["label"], stage1).append(row)
    if not cmp["page_info"]["equal"]:
        stage1.append(
            {"what": "page_info.xml rows differ", "why": "chapter starts come from book.json"}
        )
    accepted = []
    for item in accept or ():
        for group in (fix, check):
            for row in list(group):
                if row["what"] == item["what"]:
                    group.remove(row)
                    accepted.append({**row, "accepted": item.get("why", "")})
    return {"fix": fix, "check": check, "accepted": accepted, "stage1_or_source": stage1}


def test_profile(yaml_path: Path, examples: Path, out: Path) -> dict:
    items, file, accept = load_examples(examples)
    out = Path(out)
    store = ProfileStore(store=out / "_store")  # the YAML under test is not added to the real store
    results = {}
    for ex in items:
        target = out / ex["name"]
        report = run_book(
            ex["book"],
            target,
            ex.get("settings"),
            str(yaml_path),
            store,
            allow_alt_text_placeholders=True,
        )
        root = Path(report["root"])
        cmp = compare_deliveries(root, ex["delivery"], book=ex["book"])
        (target / "report/compare.json").write_text(
            json.dumps(cmp, indent=1, ensure_ascii=False) + "\n", "utf-8"
        )
        from .compare.html import compare_html

        (target / "report/compare.html").write_text(
            compare_html(cmp, str(root), str(ex["delivery"])), "utf-8"
        )
        results[ex["name"]] = {
            "delivery": str(ex["delivery"]),
            "qc_verdict": report.get("qc_verdict"),
            **differences(root, ex["delivery"], report, cmp, accept + ex["accept"]),
        }
    summary = {
        "profile": str(yaml_path),
        "examples_file": str(file),
        "examples": results,
        "remaining": sum(len(r["fix"]) + len(r["check"]) for r in results.values()),
    }
    (out / "profile_test.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    return summary


def print_summary(summary: dict) -> None:
    for name, r in summary["examples"].items():
        print(f"== {name} (QC {r['qc_verdict']})")
        for group, title in (("fix", "fix in the profile"), ("check", "check (a person decides)")):
            print(f"  {title}: {len(r[group])}")
            for d in r[group]:
                rest = {k: v for k, v in d.items() if k != "what"}
                print(f"    - {d['what']}: {json.dumps(rest, ensure_ascii=False)[:240]}")
        print(f"  accepted: {len(r['accepted'])}; Stage 1 / source (no profile fixes these): "
              f"{len(r['stage1_or_source'])}")  # fmt: skip
