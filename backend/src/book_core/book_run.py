"""End-to-end Stage 1 runner: deterministic page work, resumable development caches.

Production uses an automatically cleaned temporary cache and publishes only final,
span-referencing units, book decisions and their source span stores. No adapter is run.
"""

import hashlib
import multiprocessing
import os
import queue
import shutil
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

from book_core.cache_admin import cache_lock, disk_check, register
from book_core.cache_store import read_json, read_model, validated_reads, write_json, write_model
from book_core.caching import code_digest
from book_core.characters.cache import analyze_book_characters
from book_core.characters.cache import load_page as character_page
from book_core.equations.cache import analyze_book_equations
from book_core.equations.cache import load_page as equation_page
from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.figures.cache import analyze_book_figures, image_path
from book_core.figures.cache import load_page as figure_page
from book_core.figures.settings import FigureSettings
from book_core.model.spans import ExtractedPage
from book_core.objects.analysis import (
    analyze_page,
    atomic_write,
    cached_repetition,
    fingerprints,
    verified_read,
)
from book_core.objects.models import NativeObjectPage
from book_core.paint.cache import paint_fingerprint
from book_core.process_metrics import ProcessMonitor
from book_core.run_context import source_session
from book_core.settings import Settings
from book_core.telemetry import available_memory, measure, memory

# Dense native vector pages can exceed 8 GB while being decoded and validated.
WORKER_MEMORY_BYTES = 12 * 1024**3


def final_producer_digest():
    return code_digest("final")


LOADED_FINAL_DIGEST = final_producer_digest()


_WORKER_JOB = None


def _announce(channel, snapshot, function, arguments):
    global _WORKER_JOB
    _WORKER_JOB = (snapshot, function, arguments)
    channel.put(os.getpid())


def _dispatch(number):
    snapshot, function, arguments = _WORKER_JOB
    return function(snapshot, number, *arguments)


def _worker_measurement(measured):
    measured["_worker"] = {
        "pid": os.getpid(),
        "cpu_seconds": time.process_time(),
        "peak_rss_bytes": memory()[1],
    }
    return measured


def default_workers():
    return max(
        1, min(2, os.cpu_count() or 1, (available_memory() - 2 * 1024**3) // WORKER_MEMORY_BYTES)
    )


def _page_job(snapshot, number, root, repetition, device):
    """One page per future; return small measurements, never large evidence payloads."""
    from book_core.layout.pipeline import analyze_layout

    root = Path(root)
    measured = {}
    with source_session(snapshot.path, snapshot), validated_reads():
        extractor = PyMuPDFExtractor(device)
        native_key, _ = fingerprints(snapshot.digest, extractor, repetition)
        path = root / "native" / native_key / f"{number}.json"
        with measure(measured, "native"):
            if path.exists():
                native = verified_read(path, NativeObjectPage, native_key)
            else:
                native = extractor.extract_object_page(snapshot.path, number)
                if (
                    native.page.source_sha256 != snapshot.digest
                    or native.page.geometry.page != number
                ):
                    raise ValueError("Extractor returned another source/page")
                snapshot.check()
                atomic_write(path, native, native_key)
            text_path = root / "text" / native_key / f"{number}.json"
            if not text_path.exists():
                write_model(text_path, native.page, native_key)
        with measure(measured, "analysis"):
            analysis = analyze_page(
                snapshot.path, number, extractor, repetition, root, native=native
            )
        with measure(measured, "layout"):
            analyze_layout(snapshot.path, number, extractor, repetition, root, analysis=analysis)
    return _worker_measurement(measured)


def _order_job(snapshot, number, root, repetition, vocabulary, device):
    from book_core.caching import assert_producer_unchanged
    from book_core.layout.models import PageLayout
    from book_core.layout.pipeline import layout_fingerprint
    from book_core.reading_order.builder import build_reading_order
    from book_core.reading_order.cache import LOADED_CODE_DIGEST, order_fingerprint
    from book_core.reading_order.models import PageReadingOrder

    root, measured = Path(root), {}
    with source_session(snapshot.path, snapshot), measure(measured, "reading_order"):
        assert_producer_unchanged("reading_order", LOADED_CODE_DIGEST)
        extractor = PyMuPDFExtractor(device)
        native_key, analysis_key = fingerprints(snapshot.digest, extractor, repetition)
        layout_key = layout_fingerprint(analysis_key, extractor.device.resolved)
        key = order_fingerprint(layout_key, vocabulary)
        path = root / "reading_order" / key / f"{number}.json"
        if path.exists():
            verified_read(path, PageReadingOrder, key)
        else:
            page = read_model(
                root / "text" / native_key / f"{number}.json", ExtractedPage, native_key
            )
            layout = verified_read(
                root / "layout" / layout_key / f"{number}.json", PageLayout, layout_key
            )
            order = build_reading_order(layout, page.store, vocabulary, extractor.device.resolved)
            assert_producer_unchanged("reading_order", LOADED_CODE_DIGEST)
            atomic_write(path, order, key)
    return _worker_measurement(measured)


def _merge_measurements(target, row, worker_stats, phase):
    worker = row.pop("_worker")
    worker_stats[f"{phase}/{worker['pid']}"] = worker
    for stage, stats in row.items():
        values = target.setdefault(stage, {})
        for name, value in stats.items():
            if name == "peak_rss_bytes":
                values[name] = max(values.get(name, 0), value)
            else:
                values[name] = values.get(name, 0) + value


def _page_pool(
    function, snapshot, total, workers, arguments, measurements, progress, monitor, worker_stats
):
    if workers == 1:
        for number in range(1, total + 1):
            _merge_measurements(
                measurements,
                function(snapshot, number, *arguments),
                worker_stats,
                function.__name__,
            )
            if progress:
                progress(function.__name__, number, total)
        return
    # A bounded queue prevents whole-book page payloads/futures accumulating in RAM.
    context = multiprocessing.get_context("spawn")
    channel = context.Queue()
    try:
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=context,
            initializer=_announce,
            initargs=(channel, snapshot, function, arguments),
        ) as pool:
            pages = iter(range(1, total + 1))
            pending = {}
            for _ in range(min(total, 2 * workers)):
                number = next(pages)
                pending[pool.submit(_dispatch, number)] = number
            completed = 0
            while pending:
                while True:
                    try:
                        monitor.add(channel.get_nowait())
                    except queue.Empty:
                        break
                done, _ = wait(pending, timeout=0.05, return_when=FIRST_COMPLETED)
                for future in done:
                    pending.pop(future)
                    _merge_measurements(
                        measurements, future.result(), worker_stats, function.__name__
                    )
                    completed += 1
                    if progress:
                        progress(function.__name__, completed, total)
                    number = next(pages, None)
                    if number is not None:
                        pending[pool.submit(_dispatch, number)] = number
    finally:
        channel.close()
        channel.join_thread()


class CachedTextPages:
    """Extractor interface over validated native text, without loading visual evidence."""

    def __init__(self, extractor, root, key, count, digest):
        self.extractor, self.root, self.key = extractor, Path(root), key
        self.count, self.digest = count, digest

    @property
    def identity(self):
        return self.extractor.identity

    def extract_pages(self, source):
        if source_digest(Path(source)) != self.digest:
            raise ValueError("Cached text source mismatch")
        for number in range(1, self.count + 1):
            page = read_model(
                self.root / "text" / self.key / f"{number}.json", ExtractedPage, self.key
            )
            if page.source_sha256 != self.digest or page.geometry.page != number:
                raise ValueError("Cached text page identity mismatch")
            yield page


def _navigation_map(navigation):
    mapping = {}
    for entry in navigation.get("printed_entries", []):
        for line in entry["line_ids"]:
            mapping.setdefault(entry["source_page"], {})[line] = entry["id"]
    return mapping


def run_book(
    source,
    output_dir,
    cache_dir,
    *,
    mode="development",
    workers=None,
    settings=None,
    device="auto",
    evidence=None,
    vocabulary=None,
    cache_dirs=None,
    progress=None,
    estimated_bytes_per_page=12 * 1024**2,
    figure_settings=None,
    alt_text_generator=None,
    figure_evidence=None,
    model_cache_dir=None,
):
    """Run all implemented stages; optional read-only whole-book evidence may be supplied.

    cache_dirs is an integration hook for already established stage cache locations.
    All such locations must be inside cache_dir. No external reference is discovered here.
    """
    if mode not in {"development", "production"}:
        raise ValueError("Mode must be development or production")
    workers = default_workers() if workers is None else workers
    if workers < 1:
        raise ValueError("Worker count must be positive")
    if estimated_bytes_per_page <= 0:
        raise ValueError("Disk estimate must be positive")
    settings = settings or Settings()
    from book_core.figures.evidence import resolve

    figure_settings, evidence_warning = resolve(
        figure_settings or FigureSettings(), figure_evidence
    )
    if figure_settings.alt_text_drafts and alt_text_generator is None:
        from book_core.figures.alt_text import DraftGenerator

        alt_text_generator = DraftGenerator(device=device)
    figures = (figure_settings, alt_text_generator, figure_evidence, model_cache_dir, device)
    if final_producer_digest() != LOADED_FINAL_DIGEST:
        raise RuntimeError("Book runner producer changed; restart the worker")
    source, output_dir, cache_dir = (
        Path(source).resolve(),
        Path(output_dir).resolve(),
        Path(cache_dir).resolve(),
    )
    if mode == "production" and cache_dirs:
        raise ValueError("Production always uses its own temporary intermediate cache")
    output_dir.mkdir(parents=True, exist_ok=True)
    stats = {
        "mode": mode,
        "workers": workers,
        "stages": {},
        "worker_processes": {},
        "figure_model_evidence": figure_settings.model_evidence,
        "warnings": [evidence_warning] if evidence_warning else [],
    }
    with ProcessMonitor() as monitor, measure(stats, "total"), source_session(source) as snapshot:
        extractor = PyMuPDFExtractor(device)
        total = extractor.page_count(source)
        stats["pages"] = total
        # Temporary files go on the output volume, so estimate that volume as well.
        with cache_lock(cache_dir):
            estimate = total * estimated_bytes_per_page
            stats["disk"] = disk_check(cache_dir, estimate)
            if output_dir.anchor != cache_dir.anchor:
                disk_check(output_dir, estimate)
            if mode == "production":
                with tempfile.TemporaryDirectory(prefix="book-core-", dir=output_dir) as temporary:
                    _run(
                        snapshot,
                        extractor,
                        Path(temporary),
                        output_dir,
                        settings,
                        workers,
                        evidence,
                        vocabulary,
                        None,
                        figures,
                        stats,
                        progress,
                        monitor,
                        persistent=False,
                    )
            else:
                _run(
                    snapshot,
                    extractor,
                    cache_dir,
                    output_dir,
                    settings,
                    workers,
                    evidence,
                    vocabulary,
                    cache_dirs,
                    figures,
                    stats,
                    progress,
                    monitor,
                    persistent=True,
                )
    stats["peak_tree_rss_bytes"] = monitor.peak
    # Also retain a conservative bound for transients between the 20 ms samples.
    stats["peak_memory_upper_bound_bytes"] = stats["total"]["peak_rss_bytes"] + (
        workers if workers > 1 else 0
    ) * max(
        (
            r.get("peak_rss_bytes", 0)
            for name, r in stats["stages"].items()
            if name in {"native", "analysis", "layout", "reading_order"}
        ),
        default=0,
    )
    stats["source_hashes"] = stats["total"].get("source_hashes", 0) + sum(
        row.get("source_hashes", 0) for row in stats["stages"].values()
    )
    stats["source_reads"] = stats["total"].get("source_reads", 0) + sum(
        row.get("source_reads", 0) for row in stats["stages"].values()
    )
    stats["total_cpu_seconds"] = stats["total"]["cpu_seconds"] + (
        sum(worker["cpu_seconds"] for worker in stats["worker_processes"].values())
        if workers > 1
        else 0
    )
    return stats


def _run(
    snapshot,
    extractor,
    root,
    output_dir,
    settings,
    workers,
    evidence,
    vocabulary,
    cache_dirs,
    figures,
    stats,
    progress,
    monitor,
    *,
    persistent,
):
    from book_core.document_analysis.metadata import cached_metadata
    from book_core.document_analysis.navigation import analyze_navigation
    from book_core.document_analysis.vocabulary import build_vocabulary
    from book_core.furniture.cache import analyze_book_furniture
    from book_core.furniture.inputs import PageInputs
    from book_core.layout.models import PageLayout
    from book_core.lists.cache import analyze_book_lists
    from book_core.lists.cache import load_page as list_page
    from book_core.lists.keys import book_fingerprint as lists_key
    from book_core.paragraphs.cache import analyze_book_paragraphs
    from book_core.paragraphs.keys import book_fingerprint as paragraph_key
    from book_core.structure.cache import analyze_book_structure
    from book_core.structure.evidence import book_evidence
    from book_core.structure.keys import decision_fingerprint

    total, stages, source = stats["pages"], stats["stages"], snapshot.path
    dirs = {stage: root for stage in ("page", "furniture", "paragraphs", "structure", "lists")}
    dirs["metadata"] = root / "metadata"
    dirs["detections"] = root
    dirs.update({k: Path(v).resolve() for k, v in (cache_dirs or {}).items()})
    if any(path != root and root not in path.parents for path in dirs.values()):
        raise ValueError("Stage caches must be inside the run's cache root")
    with validated_reads():
        with measure(stages, "book_metadata"):
            repetition = cached_repetition(source, extractor, dirs["page"])
            metadata = cached_metadata(source, extractor, dirs["metadata"])
        _page_pool(
            _page_job,
            snapshot,
            total,
            workers,
            (dirs["page"], repetition, extractor.device.resolved),
            stages,
            progress,
            monitor,
            stats["worker_processes"],
        )
        native_key, analysis_key = fingerprints(snapshot.digest, extractor, repetition)
        text = CachedTextPages(extractor, dirs["page"], native_key, total, snapshot.digest)

        def pages():
            return text.extract_pages(source)

        with measure(stages, "book_evidence"):
            if evidence is not None:
                if evidence["provenance"]["source_sha256"] != snapshot.digest:
                    raise ValueError("Whole-book evidence belongs to another source")
                navigation = evidence["navigation"]
                if vocabulary is None:
                    vocabulary = evidence["vocabulary"]["casefold_frequencies"]
            else:
                native_pages = list(pages())
                navigation = analyze_navigation(native_pages, metadata)
                if vocabulary is None:
                    vocabulary = build_vocabulary(native_pages)["casefold_frequencies"]
                del native_pages
        _page_pool(
            _order_job,
            snapshot,
            total,
            workers,
            (dirs["page"], repetition, vocabulary, extractor.device.resolved),
            stages,
            progress,
            monitor,
            stats["worker_processes"],
        )
        inputs = PageInputs(source, extractor, repetition, dirs["page"], vocabulary)
        with measure(stages, "furniture"):
            furniture, furniture_key, _ = analyze_book_furniture(
                pages(), inputs, metadata, dirs["furniture"], settings=settings
            )
        with measure(stages, "paragraphs"):
            paragraphs, _ = analyze_book_paragraphs(
                pages,
                inputs,
                furniture,
                furniture_key,
                dirs["furniture"],
                _navigation_map(navigation),
                dirs["paragraphs"],
                settings=settings,
            )
        with measure(stages, "structure_evidence"):
            structured_evidence, evidence_key, _ = book_evidence(
                pages,
                inputs,
                furniture,
                furniture_key,
                dirs["furniture"],
                paragraphs,
                dirs["paragraphs"],
                navigation,
                dirs["structure"],
                settings=settings,
            )
        with measure(stages, "structure"):
            structure, _ = analyze_book_structure(
                structured_evidence,
                evidence_key,
                dirs["structure"],
                device=extractor.device.resolved,
            )
        with measure(stages, "lists"):
            lists, _ = analyze_book_lists(
                pages,
                inputs,
                paragraphs,
                dirs["paragraphs"],
                structure,
                furniture,
                dirs["lists"],
                settings=settings,
            )
        keys = {
            "native": native_key,
            "analysis": analysis_key,
            "paint": paint_fingerprint(analysis_key, extractor.device.resolved),
            "text": native_key,
            "layout": inputs.layout_key,
            "reading_order": inputs.order_key,
            "furniture": furniture_key,
            "paragraphs": paragraph_key(paragraphs.book.cache_key_inputs),
            "structure_evidence": evidence_key,
            "structure": decision_fingerprint(
                structure.cache_key_inputs["structure_producer_sha256"],
                evidence_key,
                structure.config,
                structure.structure_version,
            ),
            "lists": lists_key(lists.book.cache_key_inputs),
        }
        with measure(stages, "characters"):
            keys["characters"] = analyze_book_characters(
                source,
                pages,
                lambda page: inputs(page)[0],
                lambda number: list_page(lists, number, dirs["lists"]).units,
                keys["lists"],
                dirs["page"],
                total,
            )
        with measure(stages, "figures"):
            figure_settings, generator, evidence_of, model_cache, policy = figures
            if figure_settings.model_evidence == "on" and evidence_of is None:
                from book_core.detection.transformers import (
                    HeronDetector,
                    PPDocLayoutV3Detector,
                )
                from book_core.figures.evidence import DetectorFigures

                evidence_of = DetectorFigures(
                    source,
                    extractor,
                    [
                        HeronDetector(device=policy, cache_dir=model_cache),
                        PPDocLayoutV3Detector(device=policy, cache_dir=model_cache),
                    ],
                    dirs["detections"],
                )
            keys["figures"], figure_book = analyze_book_figures(
                source,
                pages,
                lambda page: inputs(page)[0],
                lambda number: list_page(lists, number, dirs["lists"]),
                _NativeObjects(dirs["page"], analysis_key),
                {m.page: (m.label, m.source) for m in furniture.book.markers},
                keys["lists"],
                dirs["page"],
                total,
                extractor,
                figure_settings,
                generator,
                evidence_of if figure_settings.model_evidence == "on" else None,
            )
        with measure(stages, "equations"):
            formulas = None
            if figure_settings.model_evidence == "on" and hasattr(evidence_of, "detectors"):
                from book_core.equations.evidence import DetectorFormulas

                formulas = DetectorFormulas(
                    source, extractor, list(evidence_of.detectors.values()), evidence_of.cache_dir
                )
            keys["equations"], equation_book = analyze_book_equations(
                source,
                pages,
                lambda page: inputs(page)[0],
                lambda number: list_page(lists, number, dirs["lists"]).units,
                _NativePages(dirs["page"], native_key),
                lambda number: character_page(dirs["page"], keys["characters"], number),
                {name: keys[name] for name in ("lists", "characters", "native")},
                dirs["page"],
                total,
                formulas,
            )
        snapshot.check()
        with measure(stages, "final_output"):

            def final_pages():
                for page in pages():
                    number = page.geometry.page
                    built = list_page(lists, number, dirs["lists"])
                    layout = verified_read(
                        dirs["page"] / "layout" / inputs.layout_key / f"{number}.json",
                        PageLayout,
                        inputs.layout_key,
                    )
                    unit_lines = {line for unit in built.units for line in unit.line_ids}
                    line_spans = {
                        line.id: line.span_ids for line in layout.lines if line.id in unit_lines
                    }
                    if set(line_spans) != unit_lines or any(
                        span not in page.store.spans
                        for spans in line_spans.values()
                        for span in spans
                    ):
                        raise ValueError("Final units have unresolved line/span references")
                    yield {
                        "format_version": 1,
                        "source": page.model_dump(mode="json"),
                        "units": built.model_dump(mode="json"),
                        "line_spans": line_spans,
                        "visibility_evidence": [
                            proof.model_dump(mode="json") for proof in layout.visibility_evidence
                        ],
                        "character_evidence": character_page(
                            dirs["page"], keys["characters"], number
                        ).model_dump(mode="json", exclude={"candidates"}),
                        "figures": figure_page(dirs["page"], keys["figures"], number).model_dump(
                            mode="json", exclude={"cache_key_inputs"}
                        ),
                        "equations": equation_page(
                            dirs["page"], keys["equations"], number
                        ).model_dump(mode="json", exclude={"cache_key_inputs"}),
                    }

            stats["output"] = str(
                _publish_final(
                    snapshot,
                    final_pages(),
                    {
                        "format_version": 1,
                        "source_sha256": snapshot.digest,
                        "furniture": furniture.book.model_dump(mode="json"),
                        "structure": structure.model_dump(mode="json"),
                        "lists": lists.model_dump(mode="json", exclude={"page_keys"}),
                        "figures": figure_book.model_dump(mode="json"),
                        "equations": equation_book.model_dump(mode="json"),
                    },
                    keys,
                    output_dir,
                    total,
                    {
                        name: image_path(dirs["page"], keys["figures"], name)
                        for name in _image_files(figure_book, dirs["page"], keys["figures"])
                    },
                )
            )
        _register_outputs(root, snapshot.digest, dirs, keys, stages, total, persistent=persistent)
        stats["cache_keys"] = keys


def _image_files(book, root, key):
    """Exported image files of the book, in name order (spreads share one file)."""
    names = set()
    for number in range(1, book.pages + 1):
        for record in figure_page(root, key, number).figures:
            if record.image is not None:
                names.add(record.image.file_name)
    return sorted(names)


class _NativePages:
    """The cached native object page of one page number."""

    def __init__(self, root, key):
        self.root, self.key = Path(root), key

    def __call__(self, number):
        return verified_read(
            self.root / "native" / self.key / f"{number}.json", NativeObjectPage, self.key
        )


class _NativeObjects:
    """(id, kind, bbox) of named native objects from the cached object analysis (one page)."""

    def __init__(self, root, key):
        self.root, self.key, self.page, self.objects = Path(root), key, None, {}

    def __call__(self, number, ids):
        from book_core.objects.models import ObjectAnalysis

        if number != self.page:
            analysis = verified_read(
                self.root / "analysis" / self.key / f"{number}.json", ObjectAnalysis, self.key
            )
            self.objects = {o.id: (o.id, o.kind, o.bbox) for o in analysis.all_objects()}
            self.page = number
            del analysis
        return [self.objects[i] for i in ids if i in self.objects]


def _publish_final(snapshot, page_payloads, book_payload, keys, output_dir, total, images=None):
    """Atomically publish an independently resolvable final archive."""
    final_key = stable_id(
        "final-book-3",
        LOADED_FINAL_DIGEST,
        snapshot.digest,
        keys["lists"],
        keys["characters"],
        keys["figures"],
        keys["equations"],
    )
    destination = output_dir / final_key
    with tempfile.TemporaryDirectory(prefix=".final-", dir=output_dir) as temporary:
        pending = Path(temporary) / "book"
        pending.mkdir()
        seen = set()
        for payload in page_payloads:
            page = payload["source"]
            number = page["geometry"]["page"]
            if (
                page["source_sha256"] != snapshot.digest
                or number in seen
                or not 1 <= number <= total
            ):
                raise ValueError("Final archive source/page identity mismatch")
            seen.add(number)
            write_json(pending / f"page_{number:06d}.json.gz", payload)
        if len(seen) != total:
            raise ValueError("Final archive has incomplete page coverage")
        write_json(pending / "book.json.gz", book_payload)
        if images:
            (pending / "images").mkdir()
            for name, path in sorted(images.items()):
                shutil.copyfile(path, pending / "images" / name)
        manifest = {
            "format_version": 2,
            "complete": True,
            "source_sha256": snapshot.digest,
            "pages": total,
            "keys": keys,
            "files": {
                p.relative_to(pending).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(pending.rglob("*"))
                if p.is_file()
            },
        }
        write_json(pending / "manifest.json.gz", manifest)
        snapshot.check()
        if final_producer_digest() != LOADED_FINAL_DIGEST:
            raise RuntimeError("Book runner producer changed; restart the worker")
        if destination.exists():
            prior = read_json(destination / "manifest.json.gz")
            if prior != manifest or any(
                hashlib.sha256((destination / name).read_bytes()).hexdigest() != checksum
                for name, checksum in manifest["files"].items()
            ):
                raise ValueError("Existing final output differs or is corrupt")
        else:
            os.replace(pending, destination)
    return destination


def _register_outputs(root, book, dirs, keys, stages, total, *, persistent):
    from book_core.cache_identity import producer_digest
    from book_core.caching import code_digest, coverage_files

    for stage, key in keys.items():
        if stage in {
            "native",
            "analysis",
            "paint",
            "characters",
            "figures",
            "equations",
            "layout",
            "reading_order",
            "text",
        }:
            paths = list((dirs["page"] / stage / key).glob("*.json"))
            if stage == "figures":
                paths += list((dirs["page"] / stage / key / "images").glob("*"))
        elif stage == "structure_evidence":
            paths = [dirs["structure"] / "structure/evidence" / f"{key}.json.gz"]
        else:
            stage_root = dirs[stage] / stage
            paths = [stage_root / "book" / f"{key}.json"]
            paths += list((stage_root / "page" / key).glob("*.json"))
            paths += list((stage_root / "definitions" / key).glob("*.json"))
        sizes = [p.stat().st_size for p in paths if p.exists()]
        stages.setdefault(stage, {}).update(
            cache_bytes=sum(sizes), cache_files=len(sizes), cache_bytes_per_page=sum(sizes) / total
        )
        if persistent:
            scope = "extraction" if stage in {"native", "text"} else stage
            # Effective producer closure, excluding configurations, identifies supersession.
            from book_core.caching import PACKAGE

            producing_files = [p for p in coverage_files(scope) if p != "caching.py"]
            producer = stable_id(
                code_digest(scope), producer_digest(scope, producing_files, PACKAGE)
            )
            register(root, book, stage, key, paths, producer=producer)
