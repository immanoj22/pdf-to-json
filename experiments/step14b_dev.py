"""Step 14b development scoring: the table stage pipeline on per-page evidence, vs gold.

Runs what the stage runs on every development page (``step14b_bundles``): page analysis,
records (cells, roles, content, header references), title/note candidates over the final
unit view, continuation, then the book-level title/note links. Scores text-owning tables
against the table gold (``evaluation.table_scoring``): detection, structure and full TEDS,
adjacency, header rows, header association, and title/note links (a link is correct when
it holds at least half of the reference title's or note's tokens on that page).

Usage: python step14b_dev.py [--book NAME] [--label try1]
"""

# ruff: noqa: E402
import argparse
import sys
import time
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_common as c14b
from step7_layouts import CACHE

from book_core.evaluation import table_scoring
from book_core.ledger.tokenization import TOKEN_PATTERN
from book_core.tables import captions, opinion, records
from book_core.tables.page import analyze
from book_core.tables.view import unit_view

SUMMARY = ("reference_segments", "our_tables", "matched", "detection_precision",
           "detection_recall", "teds_structure_mean", "teds_full_mean", "adjacency_f1",
           "header_rows_exact", "header_token_accuracy", "header_association")  # fmt: skip
DIGEST = "0" * 64


@lru_cache
def figure_labels(book):
    from book_core.figures.cache import load_book

    data = load_book(CACHE, common.keys(book)["figures"]).model_dump()

    def find(value):
        if isinstance(value, dict):
            if "caption_labels" in value:
                return value["caption_labels"]
            for item in value.values():
                found = find(item)
                if found is not None:
                    return found
        return None

    return tuple(find(data) or ())


def _tokens(text):
    return len(TOKEN_PATTERN.findall(unicodedata.normalize("NFKC", text)))


def record_grid(number, table, owners, span_text, line_tokens):
    """Scoring grid of a record: each cell's (page, ordinal) tokens; split spans share
    their tokens in character order."""
    queue = {}
    for index, cell in enumerate(table.cells):
        for ref in cell.span_refs:
            text = span_text[ref.span_id]
            part = text if ref.start is None else text[ref.start : ref.end]
            queue.setdefault(ref.span_id, []).append((ref.start or 0, index, _tokens(part)))
    order = {
        sid: [i for _, i, n in sorted(parts) for _ in range(n)] for sid, parts in queue.items()
    }
    tokens = {i: set() for i in range(len(table.cells))}
    whole = {lid: i for i, c in enumerate(table.cells) for lid in c.line_ids}
    for ordinal, (lid, spans) in enumerate(owners):
        if lid in whole:
            tokens[whole[lid]].add((number, ordinal))
            continue
        sid = next((s for s in spans if s in order), None)
        if sid is None:
            continue
        seq = order[sid]
        index = seq.pop(0) if len(seq) > 1 else (seq[0] if seq else None)
        if index is not None:
            tokens[index].add((number, ordinal))
    ids = {c.id: i for i, c in enumerate(table.cells)}
    heads = {
        i: [ids[h] for h in c.header_cell_ids if table.cells[ids[h]].role == "column_header"]
        for i, c in enumerate(table.cells)
    }
    return {
        "cells": [
            (c.row, c.column, c.row_span, c.column_span, c.header, frozenset(tokens[i]))
            for i, c in enumerate(table.cells)
        ],
        "header_rows": table.header_rows,
        "column_headers": heads,
    }


MODELS = ROOT / ".cache/huggingface"
READINGS = ROOT / ".cache/models"


@lru_cache
def reader(book):
    """The stage's TableFormer reader (production crops, cached readings)."""
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.tables.recognizers import ReadingCache, TableFormerStructure

    cache = ReadingCache(TableFormerStructure(device="cpu", cache_dir=MODELS), READINGS)
    return opinion.TableReader(common.source(book), PyMuPDFExtractor("cpu"), cache)


def pipeline(book, second=True):
    """({page: text-owning records with titles/notes}, {page: possible}, owners, spans,
    caption statistics, rejected kinds). ``second``: apply the TableFormer uses."""
    pages, possible, owners, spans, cands, figure_units, contents = {}, {}, {}, {}, {}, {}, {}
    rejected = Counter()
    for number, pg in c14b.pages(book):
        ev, built = pg["evidence"], pg["built"]
        accepted, refused = analyze(ev)
        found, maybe, refused_records, _ = records.records(
            accepted, refused, ev, built.order, DIGEST, number
        )
        rejected.update(r.kind for r in refused_records)
        pages[number], possible[number] = found, maybe
        final_units, _, _ = unit_view(built.units, found)
        cands[number] = captions.candidates(ev, found, final_units)
        figure_units[number] = captions.figure_claims(ev, found)
        contents[number] = ev.content
        owners[number] = pg["tokens"]
        spans[number] = {
            r.span_id: ev.spans[r.span_id].text
            for t in found for c in t.cells for r in c.span_refs
        }  # fmt: skip
    linked, continuations = records.link(pages, contents)
    titled, stats = captions.link(linked, cands, figure_units, figure_labels(book))
    stats["continuations"] = continuations
    if second:
        counts = Counter()
        for number in sorted(titled):
            readings = reader(book)(number, titled[number])
            out = []
            for table in titled[number]:
                update, found = opinion.apply(table, *readings[table.id])
                counts.update(found)
                out.append(captions._validated(table, update) if update else table)
            titled[number] = out
        stats["structure_reader"] = dict(counts)
    return titled, possible, owners, spans, stats, rejected


def _text_tokens(number, line_ids, owners):
    lines = set(line_ids)
    return {(number, i) for i, (lid, _) in enumerate(owners) if lid in lines}


def score_texts(gold_rows, matches, ours_records, owners):
    """Title and note links on matched tables: correct, wrong (gold has one, ours misses
    it), unverified (gold has none), and reference titles/notes found (recall)."""
    by_key = {(t["table"], p): t for t in gold_rows for p in t["pages"]}
    out = Counter()
    for gkey, okey, _ in matches:
        gold = by_key[tuple(gkey)]
        page = gkey[1]
        record = ours_records[tuple(okey)]
        for role, ours in (("title", [record.title] if record.title else []),
                           ("note", record.notes)):  # fmt: skip
            part = "title" if role == "title" else "notes"
            truth = {(p, o) for p, o in gold[part]["tokens"] if p == page}
            linked = set()
            for text in ours:
                linked |= _text_tokens(page, text.line_ids, owners[page])
            if truth:
                out[f"{role}_reference"] += 1
                hit = bool(linked) and len(truth & linked) >= 0.5 * len(truth)
                out[f"{role}_found"] += hit
            for text in ours:
                tokens = _text_tokens(page, text.line_ids, owners[page])
                if not truth:
                    out[f"{role}_links_unverified"] += 1
                elif tokens & truth:
                    out[f"{role}_links_correct"] += 1
                else:
                    out[f"{role}_links_wrong"] += 1
    return dict(out)


def run(book, label):
    started = time.perf_counter()
    titled, possible, owners, spans, stats, rejected = pipeline(book)
    ours, recs = {}, {}
    for number, tables in titled.items():
        for index, table in enumerate(tables):
            ours[(number, index)] = record_grid(number, table, owners[number], spans[number], None)
            recs[(number, index)] = table
    gold_rows = common.gold_tables(book)
    gold = table_scoring.gold_segments(gold_rows)
    result = table_scoring.score(gold, ours)
    per = []
    for gkey, okey, _ in result["matches"]:
        g, o, t = gold[tuple(gkey)], ours[tuple(okey)], recs[tuple(okey)]
        per.append({
            "table": gkey[0], "page": gkey[1], "gold": [g["rows"], g["columns"], g["header_rows"]],
            "ours": [len(t.rows), len(t.columns), t.header_rows], "method": t.structure_method,
            "rotation": t.rotation, "teds": round(table_scoring.teds(g, o), 4),
            "teds_full": round(table_scoring.teds(g, o, content=True), 4),
            "adjacency": table_scoring.adjacency(g, o), "problems": g["problems"],
            "title": t.title is not None, "notes": len(t.notes),
        })  # fmt: skip
    result["matched_detail"] = per
    result["texts"] = score_texts(gold_rows, result["matches"], recs, owners)
    result["captions"] = stats
    result["roles"] = dict(Counter(c.role for t in recs.values() for c in t.cells))
    result["content"] = dict(Counter(i.kind for t in recs.values() for c in t.cells
                                     for i in c.content))  # fmt: skip
    result["row_header_tables"] = sum(t.row_header_columns > 0 for t in recs.values())
    result["possible_tables"] = sum(len(v) for v in possible.values())
    result["rejected"] = dict(rejected)
    result["seconds"] = round(time.perf_counter() - started, 1)
    common.write(c14b.OUT / "dev" / label / f"{book}.json", result)
    print(book, {k: result[k] for k in SUMMARY}, flush=True)
    print(book, "texts", result["texts"], "captions", stats, flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--label", default="try")
    args = parser.parse_args()
    for name in [args.book] if args.book else common.BOOK_ORDER:
        if name != "art_therapy_index":
            run(name, args.label)
