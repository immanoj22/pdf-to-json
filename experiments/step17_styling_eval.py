"""Step 17 Part 2: inline styling against the reference XML, token by token.

Our side: the assembly runs on the Step 16 final archive (as ``step17_assemble_dev``) with a
recorder on the text decorator, so every inline span is known as source characters
(span id, raw offsets). A ledger token (``[page, ordinal]`` over retained tokens, the
reference alignment's convention) has a kind when most of its characters lie in a span of
that kind (bold-italic counts as both bold and italic).

Reference side: the cached alignment links reference tokens to PDF tokens; a reference
token has a kind when it lies inside an inline element of that kind:

- italic: ``em``, ``i``, ``emphasis`` (DocBook without a bold role; CNXML ``effect`` italics),
  ``cite``/``title`` are not counted;
- bold: ``strong``, ``b``, ``emphasis`` with a bold or strong role (CNXML effect bold);
- superscript: ``sup``, ``superscript``, ``noteref``; subscript: ``sub``, ``subscript``;
- underline: ``u``, CNXML effect underline; link: ``a``, ``link``, ``ulink``, ``xref``;
- language: ``foreignphrase``, ``foreign``; small caps: role/class/effect small caps.

Precision and recall per kind and book over aligned token pairs, with counts; a kind the
reference never marks is reported as "no reference markup". Spans are also written per book
for the hand check (``step17_styling_check.py``).

Usage: python step17_styling_eval.py --book NAME
"""

import argparse
import gzip
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import regex

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.assembly import build as build_module
from book_core.assembly.assemble import assemble
from book_core.assembly.profile import load_profile
from book_core.cache_store import read_json
from book_core.ledger.tokenization import TOKEN_PATTERN
from book_core.model.spans import ExtractedPage

import step17_assemble_dev as dev
from reference_paths import reference_path

OUT = ROOT / "experiments/out/step17/styling"
CAPTURE = ROOT / "experiments/out/step16/final"
XML = {"spanish_us_history": "spanish_xml", "immigrant_children": "immigrant_xml",
       "art_therapy_index": "art_index_xml", "medical_anatomy": "medical_xml"}  # fmt: skip
KINDS = ("italic", "bold", "superscript", "subscript", "underline", "link", "language",
         "small_caps")  # fmt: skip
# Headings and titles: references style them by element (no strong/em inside), so bold and
# italic are also scored on body text only (tokens outside these elements).
HEADINGS = frozenset(
    {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hd",
        "title",
        "subtitle",
        "bridgehead",
        "titleabbrev",
        "levelhd",
        "doctitle",
        "docauthor",
    }
)


def record_spans(book):
    """{span id: {raw offset: set(kind)}} from an assembly run with a recorder; and the
    recorded spans for the hand check."""
    marks = defaultdict(lambda: defaultdict(set))
    samples = []
    original = build_module.decorate

    def recorder(built, **kwargs):
        content = original(built, **kwargs)
        for span in content.spans:
            kinds = {"bold_italic": ("bold", "italic")}.get(span.kind, (span.kind,))
            if span.kind in {"math", "run_in_heading"}:
                continue
            boxes, text = [], content.text[span.start : span.end]
            for seg in built.segments:
                lo, hi = max(seg.start, span.start), min(seg.end, span.end)
                if lo >= hi:
                    continue
                # Text offsets inside a segment map one to one to raw offsets when NFKC
                # keeps the length (else the whole segment range is marked).
                raw_len = seg.raw_end - seg.raw_start
                if raw_len == seg.end - seg.start:
                    a, b = (
                        seg.raw_start + lo - seg.start,
                        seg.raw_start + hi - seg.start,
                    )
                else:
                    a, b = seg.raw_start, seg.raw_end
                for k in range(a, b):
                    marks[seg.span.id][k].update(kinds)
                boxes.append(seg.span.bbox)
            if boxes:
                samples.append({"kind": span.kind, "text": text, "page": built.segments[0].span.page,
                                "box": [min(b.x0 for b in boxes), min(b.y0 for b in boxes),
                                        max(b.x1 for b in boxes), max(b.y1 for b in boxes)],
                                "href": span.href, "language": span.language})  # fmt: skip
        return content

    build_module.decorate = recorder
    run = json.loads((CAPTURE / "performance" / f"{book}.json").read_text())["run"]
    native, evidence = dev.providers(book, run)
    try:
        assemble(Path(run["output"]), native_page=native, evidence_page=evidence,
                 profile=load_profile(), converter={"name": "book_core", "version": "dev",
                                                    "producer": "0" * 64},
                 settings_sha256="0" * 64)  # fmt: skip
    finally:
        build_module.decorate = original
    return marks, samples, Path(run["output"]), run["pages"]


def token_kinds(archive, pages, marks):
    """{(page, ordinal): set(kind)} over retained tokens in extraction order."""
    found = {}
    for number in range(1, pages + 1):
        page = ExtractedPage.model_validate(
            read_json(archive / f"page_{number:06d}.json.gz")["source"]
        )
        ordinal = 0
        for line in page.store.lines:
            raw = page.store.raw_line_text(line)
            if not raw.strip() or not page.geometry.content_bbox.contains_center(
                line.bbox
            ):
                continue
            owners = [
                (sid, k)
                for sid in line.span_ids
                for k in range(len(page.store.spans[sid].raw_text))
            ]
            fragments, normalized_owners = [], []
            for cluster in regex.finditer(r"\X", raw):
                fragment = unicodedata.normalize("NFKC", cluster.group())
                fragments.append(fragment)
                normalized_owners.extend([owners[cluster.start()]] * len(fragment))
            normalized = "".join(fragments)
            for match in TOKEN_PATTERN.finditer(normalized):
                chars = normalized_owners[match.start() : match.end()]
                votes = Counter(
                    kind for sid, k in chars for kind in marks.get(sid, {}).get(k, ())
                )
                found[(number, ordinal)] = {
                    kind for kind, n in votes.items() if n * 2 > len(chars)
                }
                ordinal += 1
    return found


def reference_kinds(doc, extra_attributes=None):
    """Per reference token: its inline kinds."""
    kinds_of = {}
    for element in doc.elements:
        name = element.name.casefold()
        attrs = {k.casefold(): str(v).casefold() for k, v in element.attributes.items()}
        if extra_attributes:
            attrs.update(extra_attributes.get(element.index, {}))
        role = " ".join(attrs.get(k, "") for k in ("role", "class", "effect"))
        found = set()
        if name in {"em", "i"}:
            found.add("italic")
        if name in {"strong", "b"}:
            found.add("bold")
        if name == "emphasis":
            if any(w in role for w in ("bold", "strong")):
                found.add("bold")
            elif "underline" in role:
                found.add("underline")
            elif "smallcaps" in role.replace("-", "").replace(" ", ""):
                found.add("small_caps")
            else:
                found.add("italic")
        if (
            "smallcaps" in role.replace("-", "").replace(" ", "")
            or "small-caps" in role
        ):
            found.add("small_caps")
        if name in {"sup", "superscript", "noteref"}:
            found.add("superscript")
        if name in {"sub", "subscript"}:
            found.add("subscript")
        if name == "u":
            found.add("underline")
        if name in {"a", "link", "ulink", "xref"}:
            found.add("link")
        if name in {"foreignphrase", "foreign"}:
            found.add("language")
        kinds_of[element.index] = found
    result, heading = [], []
    for token in doc.tokens:
        found = set(kinds_of.get(token.element, ()))
        chain = [token.element, *doc.ancestors(token.element)]
        for ancestor in chain[1:]:
            found |= kinds_of.get(ancestor, set())
        result.append(found)
        heading.append(any(doc.elements[e].name.casefold() in HEADINGS for e in chain))
    return result, heading


def alignment(xml_sha256):
    candidates = []
    roots = [ROOT / ".cache/step5/alignment", ROOT / ".cache/step13/gold"]
    for root in roots:
        for path in root.glob("*.json*"):
            raw = path.read_bytes()
            data = json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
            payload = data.get("payload", data)
            if isinstance(payload, str):
                payload = json.loads(payload)
            if payload.get("xml_sha256") == xml_sha256:
                candidates.append((path.stat().st_mtime, payload))
    if not candidates:
        raise SystemExit("no cached alignment for this reference")
    return max(candidates, key=lambda c: c[0])[1]


def reference(book):
    from book_core.reference.dialects import load_dialects
    from book_core.reference.xml_reader import read_reference

    if book == "statistics":
        from book_core.evaluation import math_gold

        import step14a_gold as gold

        profile = math_gold.profile_data()
        found = math_gold.read_math_reference(reference_path(gold.CNXML[book]), profile)
        return found.document
    data = reference_path(XML[book]).read_bytes()
    return read_reference(
        data, load_dialects(ROOT / "backend/reference_dialects/dialects.json")
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    args = parser.parse_args()
    marks, samples, archive, pages = record_spans(args.book)
    ours = token_kinds(archive, pages, marks)
    doc = reference(args.book)
    aligned = alignment(doc.sha256)
    ref, in_heading = reference_kinds(doc)
    page_of = aligned["pages"]
    counts = {k: Counter() for k in KINDS}
    body = {k: Counter() for k in KINDS}
    examples = {k: {"fp": [], "fn": []} for k in KINDS}
    for index, token in enumerate(doc.tokens):
        page_index = aligned["xml_page"][index]
        if page_index < 0:
            continue
        key = (page_of[page_index], aligned["xml_ordinal"][index])
        if key not in ours:
            continue
        for kind in KINDS:
            r, o = kind in ref[index], kind in ours[key]
            counts[kind]["ref"] += r
            counts[kind]["ours"] += o
            counts[kind]["tp"] += r and o
            if not in_heading[index]:
                body[kind]["ref"] += r
                body[kind]["ours"] += o
                body[kind]["tp"] += r and o
            if o and not r and len(examples[kind]["fp"]) < 15:
                examples[kind]["fp"].append([*key, token.value])
            if r and not o and len(examples[kind]["fn"]) < 15:
                examples[kind]["fn"].append([*key, token.value])
        counts["_all"] = counts.get("_all", Counter())
        counts["_all"]["aligned_tokens"] += 1
    rows = {}
    for kind in KINDS:
        c = counts[kind]
        rows[kind] = {
            "reference_tokens": c["ref"], "our_tokens": c["ours"], "both": c["tp"],
            "precision": round(c["tp"] / c["ours"], 4) if c["ours"] else None,
            "recall": round(c["tp"] / c["ref"], 4) if c["ref"] else None,
            "note": "no reference markup" if not c["ref"] else "",
            "body_only": {"reference_tokens": body[kind]["ref"], "our_tokens": body[kind]["ours"],
                          "both": body[kind]["tp"],
                          "precision": round(body[kind]["tp"] / body[kind]["ours"], 4)
                          if body[kind]["ours"] else None,
                          "recall": round(body[kind]["tp"] / body[kind]["ref"], 4)
                          if body[kind]["ref"] else None},
        }  # fmt: skip
    result = {"book": args.book, "aligned_tokens": counts["_all"]["aligned_tokens"],
              "reference_tokens": len(doc.tokens), "kinds": rows, "examples": examples,
              "our_spans": Counter(s["kind"] for s in samples)}  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.book}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n",
                                           "utf-8", newline="\n")  # fmt: skip
    with gzip.open(
        OUT / f"{args.book}_spans.json.gz", "wt", encoding="utf-8"
    ) as stream:
        json.dump(samples, stream, ensure_ascii=False)
    print(json.dumps({k: (v["precision"], v["recall"], v["reference_tokens"], v["our_tokens"],
                          "body", v["body_only"]["precision"], v["body_only"]["recall"])
                      for k, v in rows.items()}))  # fmt: skip


if __name__ == "__main__":
    main()
