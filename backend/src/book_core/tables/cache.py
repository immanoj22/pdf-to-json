"""Book-level table stage after MathML: page records, then continuations across pages.

Each page's evidence (``tables.evidence``) is analysed (``tables.page``) and turned into
records (``tables.records``); continuation needs the next page, so page records are written
once every page is analysed (a partial cache is recomputed). No earlier stage reads the
records: units, order and the ledger are unchanged in their caches; the final archive
publishes the records with the unit view (``tables.view``).
"""

import json
from collections import Counter
from pathlib import Path

from book_core.cache_store import read_model, write_model
from book_core.caching import assert_producer_unchanged, code_digest
from book_core.extraction.fingerprints import stable_id
from book_core.tables import detect, grid, page, records
from book_core.tables.evidence import page_evidence
from book_core.tables.models import BookTables, PageTables
from book_core.tables.settings import TableSettings

VERSION = "tables-1"
CONFIG = {
    "detect": {
        "touch": detect.TOUCH,
        "merge": detect.MERGE,
        "stack_overlap": detect.STACK_OVERLAP,
        "stack_gap": detect.STACK_GAP,
        "stack_rules": detect.STACK_RULES,
        "model_score": detect.MODEL_SCORE,
        "model_cover": detect.MODEL_COVER,
        "same_region": detect.SAME_REGION,
        "organizer_gap": detect.ORGANIZER_GAP,
    },
    "grid": {
        "word_gap": grid.WORD_GAP,
        "cross_share": grid.CROSS_SHARE,
        "rule_cover": grid.RULE_COVER,
        "dense_rules": grid.DENSE_RULES,
        "boxed_rules": grid.BOXED_RULES,
        "continue_gap": grid.CONTINUE_GAP,
        "segment_cover": grid.SEGMENT_COVER,
        "edge": grid.EDGE,
    },
    "page": {
        "margin": page.MARGIN,
        "paragraph_share": page.PARAGRAPH_SHARE,
        "entry_share": page.ENTRY_SHARE,
        "list_share": page.LIST_SHARE,
        "owning_models": page.OWNING_MODELS,
        "figure_share": page.FIGURE_SHARE,
        "label_share": page.LABEL_SHARE,
        "labelled_share": page.LABELLED_SHARE,
        "freeform_min": page.FREEFORM_MIN,
        "freeform_share": page.FREEFORM_SHARE,
    },
    "records": {
        "review_confidence": records.REVIEW_CONFIDENCE,
        "edge_share": records.EDGE_SHARE,
        "column_tolerance": records.COLUMN_TOLERANCE,
    },
}
LOADED_DIGEST = code_digest("tables")


def tables_fingerprint(keys, settings, model_identity=None):
    return stable_id(
        json.dumps(keys, sort_keys=True),
        json.dumps(model_identity or {}, sort_keys=True),
        code_digest("tables"),
        VERSION,
        json.dumps(CONFIG, sort_keys=True),
        settings.model_dump_json(),
    )


def analyze_book_tables(
    pages,
    layout_of,
    built_of,
    objects_of,
    figures_of,
    equations_of,
    keys,
    cache_dir,
    total,
    settings=None,
    models_of=None,
    navigation=None,
):
    """Table records for every page; returns (key, BookTables).

    ``navigation``: {page: printed navigation kind} from the structure stage (contents,
    index, glossary, ...); a table candidate on such a page is at most a possible table.

    ``objects_of(number)``: the page's native objects and compounds; ``figures_of`` the
    final figure records (after equation conversions); ``equations_of`` the equation
    records; ``models_of(number)``: {model: [(bbox, score, label)]} table boxes of the
    learned detectors, required exactly when the settings turn model evidence on.
    """
    settings = settings or TableSettings()
    assert_producer_unchanged("tables", LOADED_DIGEST)
    if settings.model_evidence == "auto":
        raise ValueError("Resolve model_evidence (tables.settings.resolve) before the stage")
    if (settings.model_evidence == "on") != (models_of is not None):
        raise ValueError("Table-model evidence must be supplied exactly when it is on")
    identity = getattr(models_of, "identity", None) if models_of is not None else None
    key = tables_fingerprint(
        {**keys, "navigation": json.dumps(sorted((navigation or {}).items()))}, settings, identity
    )
    directory = Path(cache_dir) / "tables" / key
    paths = {n: directory / f"{n}.json" for n in range(1, total + 1)}
    book_path = directory / "book.json"
    if book_path.exists() and all(p.exists() for p in paths.values()):
        return key, read_model(book_path, BookTables, key)
    drafts, contents, digest = {}, {}, None
    for item in pages():
        number = item.geometry.page
        digest = item.source_sha256
        layout = layout_of(item)
        built = built_of(number)
        evidence = page_evidence(
            layout,
            item.store,
            objects_of(number),
            built,
            figures_of(number),
            equations_of(number),
            models_of(number) if models_of is not None else None,
            (navigation or {}).get(number),
        )
        accepted, rejected = page.analyze(evidence)
        found, possible, refused, notes = records.records(
            accepted, rejected, evidence, built.order, digest, number
        )
        drafts[number] = (found, possible, refused, notes)
        contents[number] = layout.content_bbox
    if sorted(drafts) != list(paths):
        raise ValueError("Table records have incomplete page coverage")
    linked, continuations = records.link({n: d[0] for n, d in drafts.items()}, contents)
    rejected_kinds, note_kinds, review, by_page = Counter(), Counter(), Counter(), {}
    total_tables = total_possible = 0
    for number in sorted(drafts):
        _, possible, refused, notes = drafts[number]
        tables = linked[number]
        total_tables += len(tables)
        total_possible += len(possible)
        if tables:
            by_page[str(number)] = len(tables)
        rejected_kinds.update(r.kind for r in refused)
        note_kinds.update(n.kind for n in notes)
        for table in tables:
            for flag in table.review_flags:
                review[flag.split(";")[0]] += 1
        assert_producer_unchanged("tables", LOADED_DIGEST)
        write_model(
            paths[number],
            PageTables(
                source_sha256=digest,
                page=number,
                version=VERSION,
                tables=tables,
                possible_tables=possible,
                rejected=refused,
                figure_notes=notes,
                cache_key_inputs={"tables_key": key},
            ),
            key,
        )
    book = BookTables(
        source_sha256=digest,
        pages=total,
        version=VERSION,
        config=CONFIG,
        settings=settings.model_dump(mode="json"),
        models=identity or {},
        tables=total_tables,
        possible_tables=total_possible,
        by_page=by_page,
        rejected=dict(rejected_kinds),
        continuations=continuations,
        figure_notes=dict(note_kinds),
        review=dict(review),
        cache_key_inputs={"tables_key": key, **{k: str(v) for k, v in keys.items()}},
    )
    write_model(book_path, book, key)
    return key, book


def load_page(cache_dir, key, number):
    return read_model(Path(cache_dir) / "tables" / key / f"{number}.json", PageTables, key)


def load_book(cache_dir, key):
    return read_model(Path(cache_dir) / "tables" / key / "book.json", BookTables, key)
