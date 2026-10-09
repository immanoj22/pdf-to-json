"""Evaluate document evidence against immutable provisional reference units per book."""

from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict

import networkx as nx
import regex
from rapidfuzz.fuzz import ratio

from book_core.document_analysis.navigation import normalize_label, resolve_title
from book_core.evaluation.derived_harness import DerivedGold
from book_core.reference.pdf_tokens import page_tokens


def title_key(title):
    return " ".join(
        regex.findall(r"[\p{L}\p{M}\p{N}]+", unicodedata.normalize("NFKC", title).casefold())
    )


def _navigation(entries, headings, titles, pages, similarity):
    graph = nx.Graph()
    keys = {u["unit"]: title_key(titles.get(u["unit"], "")) for u in headings}
    for i, entry in enumerate(entries):
        key = title_key(resolve_title(entry, pages))
        if not key:
            continue
        for unit in headings:
            expected = keys[unit["unit"]]
            if not expected:
                continue
            score = ratio(key, expected)
            if score >= similarity:
                correct_page = bool(set(entry["target_pages"]) & {p for p, _, _ in unit["pdf"]})
                # Target-page evidence breaks ties between repeated identical heading titles.
                graph.add_edge(
                    ("entry", i),
                    ("unit", unit["unit"]),
                    weight=score + int(correct_page) / 100,
                    score=score,
                )
    pairs = nx.max_weight_matching(graph, maxcardinality=True)
    units = {u["unit"]: u for u in headings}
    matches = []
    for left, right in pairs:
        if left[0] != "entry":
            left, right = right, left
        entry, unit = entries[left[1]], units[right[1]]
        expected_pages = sorted({p for p, _, _ in unit["pdf"]})
        unique_target = len(entry["target_pages"]) == 1
        matches.append(
            {
                "entry_id": entry["id"],
                "unit": unit["unit"],
                "title_similarity": graph.edges[left, right]["score"],
                "target_pages": entry["target_pages"],
                "reference_pages": expected_pages,
                "target_correct": unique_target and entry["target_pages"][0] in expected_pages,
                "target_ambiguous": len(entry["target_pages"]) > 1,
            }
        )
    matched = len(matches)
    correct = sum(m["target_correct"] for m in matches)
    eligible = sum(bool(keys[u["unit"]]) for u in headings)
    return {
        "entries": len(entries),
        "reference_heading_units": len(headings),
        "heading_units_with_reference_title": eligible,
        "title_matches": matched,
        "title_precision": matched / len(entries) if entries else None,
        "title_recall": matched / len(headings) if headings else None,
        "title_and_target_matches": correct,
        "title_and_target_precision": correct / len(entries) if entries else None,
        "title_and_target_recall": correct / len(headings) if headings else None,
        "target_accuracy_given_title": correct / matched if matched else None,
        "unresolved_targets": sum(not e["target_pages"] for e in entries),
        "ambiguous_targets": sum(len(e["target_pages"]) > 1 for e in entries),
        "matches": sorted(matches, key=lambda m: m["entry_id"]),
    }


def evaluate_document(gold: DerivedGold, pages, evidence, reference_titles, *, similarity=90.0):
    if not pages or len({p.geometry.page for p in pages}) != len(pages):
        raise ValueError("Missing or duplicate pages in document evaluation")
    source = gold.manifest["provenance"]["pdf_sha256"]
    if any(p.source_sha256 != source for p in pages):
        raise ValueError("Mixed source pages in document evaluation")
    pdf_pages = {p.geometry.page: page_tokens(p) for p in pages}
    if set(pdf_pages) != {r["page"] for r in gold.pages}:
        raise ValueError("Incomplete or extra document pages")
    for unit in gold.units:
        for p, start, count in unit["pdf"]:
            if (
                p not in pdf_pages
                or start < 0
                or count < 1
                or start + count > len(pdf_pages[p].tokens)
            ):
                raise ValueError("Invalid derived-gold token run")
    known_lines = {(p.geometry.page, line.id) for p in pages for line in p.store.lines}
    for candidate in evidence["repetition"]["candidates"]:
        if not candidate["occurrences"]:
            raise ValueError("Empty repetition candidate")
        for row in candidate["occurrences"]:
            if (row["page"], row["line_id"]) not in known_lines:
                raise ValueError("Unknown repetition line reference")
    for row in gold.pages:
        page = pdf_pages.get(row["page"])
        if page is None or page.digest != row["token_digest"] or len(page.tokens) != row["tokens"]:
            raise ValueError("Document evaluation token references differ from derived gold")
    if gold.manifest["provenance"]["pdf_sha256"] != pages[0].source_sha256:
        raise ValueError("Derived gold describes another source")
    headings = [u for u in gold.units if u["kind"] == "heading"]
    navigation = {}
    all_entries = evidence["navigation"]["entries"]
    for kind in ("bookmark", "printed_toc"):
        entries = [e for e in all_entries if e["kind"] == kind]
        navigation[kind] = _navigation(entries, headings, reference_titles, pages, similarity)
    # Deduplicate the same title/destination supplied by bookmarks and printed navigation.
    unique = {}
    for entry in all_entries:
        targets = tuple(sorted(set(entry["target_pages"])))
        if targets:
            destination = ("pages", targets)
        elif entry.get("target_label"):
            destination = ("label", normalize_label(entry["target_label"]))
        else:
            # No destination evidence exists to justify merging separate entries.
            destination = ("unresolved_entry", entry["id"])
        key = title_key(resolve_title(entry, pages)), destination
        unique.setdefault(key, entry)
    navigation["combined_unique"] = _navigation(
        list(unique.values()), headings, reference_titles, pages, similarity
    )
    owners = defaultdict(set)
    for unit in gold.units:
        for p, start, count in unit["pdf"]:
            for ordinal in range(start, start + count):
                owners[p, ordinal].add(unit["kind"])
    line_tokens = defaultdict(set)
    for page in pdf_pages.values():
        for token in page.tokens:
            line_tokens[page.page, page.lines[token.line].id].add((page.page, token.ordinal))
    candidate_positions = set()
    candidate_rows = []
    for candidate in evidence["repetition"]["candidates"]:
        positions = set().union(
            *(line_tokens[r["page"], r["line_id"]] for r in candidate["occurrences"])
        )
        candidate_positions.update(positions)
        aligned = positions & owners.keys()
        kinds = Counter(kind for pos in aligned for kind in owners[pos])
        candidate_rows.append(
            {
                "candidate": candidate["id"],
                "band": candidate["band"],
                "confidence": candidate["confidence"],
                "pages": len(candidate["pages"]),
                "tokens": len(positions),
                "aligned": len(aligned),
                "not_aligned": len(positions - aligned),
                "aligned_unit_kinds": dict(kinds),
                "sample": candidate["occurrences"][0],
            }
        )
    aligned_positions = candidate_positions & owners.keys()
    cluster_of = {
        (r["page"], r["line_id"]): r["style_cluster_id"] for r in evidence["style"]["lines"]
    }
    style_counts = Counter()
    heading_style_units = Counter()
    by_heading = []
    for unit in headings:
        counts = Counter()
        for p, start, count in unit["pdf"]:
            for ordinal in range(start, start + count):
                page = pdf_pages[p]
                token = page.tokens[ordinal]
                cluster = cluster_of[p, page.lines[token.line].id]
                counts[cluster] += 1
        style_counts.update(counts)
        heading_style_units.update(counts.keys())
        by_heading.append({"unit": unit["unit"], "style_cluster_tokens": dict(counts)})
    return {
        "book": gold.book,
        "split": gold.split,
        "notes": gold.manifest["notes"],
        "overall": None,
        "reference_human_approved": False,
        "navigation": navigation,
        "title_similarity_threshold": similarity,
        "repetition": {
            "candidates": len(candidate_rows),
            "unique_candidate_tokens": len(candidate_positions),
            "aligned_to_reference": len(aligned_positions),
            "not_aligned_to_reference": len(candidate_positions - aligned_positions),
            "aligned_unit_kinds": dict(
                Counter(k for pos in aligned_positions for k in owners[pos])
            ),
            "candidate_details": candidate_rows,
        },
        "heading_styles": {
            "heading_units": len(headings),
            "clusters": [
                {
                    "style_cluster_id": cluster,
                    "aligned_heading_tokens": count,
                    "heading_units": heading_style_units[cluster],
                }
                for cluster, count in style_counts.most_common()
            ],
            "units": by_heading,
        },
        "limitations": [
            "Unaligned candidate tokens are not proof of furniture or true reference absence.",
            "Reference titles compare casefolded Unicode tokens by one-to-one fuzzy matching.",
            "Target correctness requires one resolved page within the unit's aligned page runs.",
            "Reference alignment and headings are provisional evidence.",
            "Style counts assign each heading token its containing line's dominant style cluster.",
        ],
    }
