"""Reproducible synthetic OCR scans; references and Step 15 caches are read-only.

Select first with ``--select``. Run an explicit engine configuration with ``--config``.
Every selected page is evaluated under every named degradation. The raster-only
input has no text layer, and known figure regions are blanked in raster and truth.
The main recognition score aligns lines geometrically to native line evidence;
raw emission-order scores are also retained and do not claim semantic order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

from book_core.cache_store import read_json, write_json

BOOKS = {
    "spanish_us_history": "spanish_pdf",
    "immigrant_children": "small_pdf",
    "medical_anatomy": "medical_pdf",
    "statistics": "statistics_pdf",
}
CAPTURE = ROOT / "experiments/out/step15/final"
OUT = ROOT / "experiments/out/step16/benchmark"
DEGRADATIONS = (
    "clean",
    "200dpi",
    "skew-2",
    "skew+2",
    "noise",
    "blur",
    "jpeg50",
    "rotate90",
    "rotate180",
)
SEED = 1600


def write_plain(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def archive_root(book):
    return Path(
        json.loads((CAPTURE / f"performance/{book}.json").read_text("utf-8"))["run"][
            "output"
        ]
    )


def payload(book, number):
    return read_json(archive_root(book) / f"page_{number:06d}.json.gz")


def features(data):
    units = data["units"]["units"]
    kinds = {unit["kind"] for unit in units}
    result = []
    if data["tables"]["tables"]:
        result.append("table")
    if "list_item" in kinds:
        result.append("list")
    if any(
        edge["kind"] in {"next_lane_in_band", "continues_across_column"}
        for edge in data["units"]["order"]["edges"]
    ):
        result.append("multiple_columns")
    if data["equations"].get("units"):
        result.append("equation")
    if "index_entry" in kinds:
        result.append("index")
    return result


def select(count=30):
    manifest = {
        "seed": SEED,
        "pages_per_book": count,
        "degradations": DEGRADATIONS,
        "books": {},
    }
    for book, source_key in BOOKS.items():
        rows = []
        for path in sorted(archive_root(book).glob("page_*.json.gz")):
            data = read_json(path)
            spans = data["source"]["store"]["spans"]
            if not any(span["raw_text"].strip() for span in spans.values()):
                continue
            rows.append(
                {
                    "page": data["source"]["geometry"]["page"],
                    "features": features(data),
                    "source_sha256": data["source"]["source_sha256"],
                    "native_characters": sum(
                        len(span["raw_text"]) for span in spans.values()
                    ),
                    "figure_regions": len(data["figures"]["figures"]),
                    "minimum_font_size": min(
                        (
                            span["size"]
                            for span in spans.values()
                            if span["raw_text"].strip()
                        ),
                        default=0,
                    ),
                }
            )
        rng = random.Random(f"{SEED}:{book}")
        chosen = {}
        categories = ("table", "list", "multiple_columns", "equation", "index")
        for category in categories:
            candidates = [row for row in rows if category in row["features"]]
            if candidates:
                row = rng.choice(candidates)
                chosen[row["page"]] = row
        candidates = [row for row in rows if row["page"] not in chosen]
        for row in rng.sample(candidates, min(count - len(chosen), len(candidates))):
            chosen[row["page"]] = row
        selected = sorted(chosen.values(), key=lambda row: row["page"])
        manifest["books"][book] = {
            "source_key": source_key,
            "archive": str(archive_root(book)),
            "selected": selected,
            "available_features": dict(
                Counter(feature for row in rows for feature in row["features"])
            ),
            "selected_features": dict(
                Counter(feature for row in selected for feature in row["features"])
            ),
            "unavailable_features": [
                category
                for category in categories
                if not any(category in row["features"] for row in rows)
            ],
        }
        print(f"{book}: selected {len(selected)} pages", flush=True)
    write_plain(OUT / "sample_manifest.json", manifest)
    return manifest


def box_values(box):
    return tuple(box[key] for key in ("x0", "y0", "x1", "y1"))


def overlap(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )


def native_truth(data):
    """Mask whole intersected spans too, avoiding truncated figure-adjacent glyphs."""
    store = data["source"]["store"]
    masks = [box_values(figure["bbox"]) for figure in data["figures"]["figures"]]
    excluded = {
        sid
        for sid, span in store["spans"].items()
        if any(overlap(box_values(span["bbox"]), box) > 0 for box in masks)
    }
    masks += [box_values(store["spans"][sid]["bbox"]) for sid in sorted(excluded)]
    lines = []
    for line in store["lines"]:
        spans = [store["spans"][sid] for sid in line["span_ids"] if sid not in excluded]
        text = "".join(span["raw_text"] for span in spans)
        if text.strip():
            boxes = [box_values(span["bbox"]) for span in spans]
            lines.append(
                {
                    "id": line["id"],
                    "text": text,
                    "bbox": (
                        min(box[0] for box in boxes),
                        min(box[1] for box in boxes),
                        max(box[2] for box in boxes),
                        max(box[3] for box in boxes),
                    ),
                }
            )
    return lines, masks, sorted(excluded)


def render_case(book, number, degradation):
    import cv2
    import numpy as np
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.ocr.geometry import (
        ImageTransform,
        apply_transform,
        decode_image,
        encode_image,
        rotation_transform,
    )
    from reference_paths import reference_path

    dpi = 200 if degradation == "200dpi" else 400 if degradation == "400dpi" else 300
    raster = PyMuPDFExtractor(device="cpu").render_page(
        reference_path(BOOKS[book]), number, dpi
    )
    image = decode_image(raster.png)
    lines, masks, excluded = native_truth(payload(book, number))
    for x0, y0, x1, y1 in masks:
        left, right = (
            int(np.floor(x0 * raster.width / raster.page_width)),
            int(np.ceil(x1 * raster.width / raster.page_width)),
        )
        top, bottom = (
            int(np.floor(y0 * raster.height / raster.page_height)),
            int(np.ceil(y1 * raster.height / raster.page_height)),
        )
        image[
            max(0, top) : min(raster.height, bottom),
            max(0, left) : min(raster.width, right),
        ] = 255
    transform = ImageTransform.identity(raster.width, raster.height)
    rng = np.random.default_rng(
        int(
            hashlib.sha256(
                f"{SEED}:{book}:{number}:{degradation}".encode()
            ).hexdigest()[:16],
            16,
        )
    )
    if degradation.startswith("rotate"):
        transform = rotation_transform(
            raster.width, raster.height, int(degradation.removeprefix("rotate"))
        )
        image = apply_transform(image, transform)
    elif degradation.startswith("skew"):
        angle = float(degradation.removeprefix("skew"))
        matrix = cv2.getRotationMatrix2D(
            (raster.width / 2, raster.height / 2), angle, 1
        )
        corners = (
            np.array(
                [
                    [0, 0, 1],
                    [raster.width, 0, 1],
                    [raster.width, raster.height, 1],
                    [0, raster.height, 1],
                ]
            )
            @ matrix.T
        )
        low, high = corners.min(axis=0), corners.max(axis=0)
        matrix[:, 2] -= low
        transform = ImageTransform(
            raster.width,
            raster.height,
            int(np.ceil(high[0] - low[0])),
            int(np.ceil(high[1] - low[1])),
            tuple(matrix.reshape(-1)),
            deskew_degrees=angle,
        )
        image = apply_transform(image, transform)
    elif degradation == "noise":
        image = np.clip(
            image.astype(np.float32) + rng.normal(0, 12, image.shape), 0, 255
        ).astype(np.uint8)
    elif degradation == "blur":
        image = cv2.GaussianBlur(image, (5, 5), 1.2)
    elif degradation == "jpeg50":
        _, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 50])
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    elif degradation not in {"clean", "200dpi", "400dpi"}:
        raise ValueError(f"Unknown degradation: {degradation}")
    return encode_image(image), raster, transform, lines, excluded


def make_engines(config):
    from book_core.ocr.engines import PpOcrV5Engine, PpRecognitionModel, TesseractEngine

    primary = TesseractEngine(
        Path(config["tesseract_executable"]), Path(config["tessdata"])
    )
    secondary = None
    if config.get("pp_recognizers"):
        models = tuple(
            PpRecognitionModel(
                Path(row["path"]), row["revision"], tuple(row["languages"]), row["name"]
            )
            for row in config["pp_recognizers"]
        )
        secondary = PpOcrV5Engine(
            Path(config["pp_detector"]),
            config["pp_detector_revision"],
            models,
            device=config.get("device", "auto"),
        )
    return primary, secondary


def measured_read(engine, image, **kwargs):
    import subprocess
    import time
    from unittest.mock import patch

    from book_core.process_metrics import ProcessMonitor

    original = subprocess.Popen
    with ProcessMonitor() as monitor:

        def spawned(*args, **options):
            process = original(*args, **options)
            monitor.add(process.pid)
            return process

        start = time.perf_counter()
        with patch("subprocess.Popen", spawned):
            reading = engine.read(image, **kwargs)
        elapsed = time.perf_counter() - start
    return reading, {
        "wall_seconds": elapsed,
        "peak_process_tree_rss_bytes": monitor.peak,
        "memory_method": "20ms sampled current reader process plus launched child processes",
    }


def score(reading, lines, raster, degradation_transform):
    from book_core.ocr.evaluation import aggregate, error_counts, word_errors, words
    from book_core.ocr.geometry import source_pixel_box

    assigned = defaultdict(list)
    extras = []
    for word in reading.words:
        source = source_pixel_box(reading.transform, word.pixel_bbox)
        original = source_pixel_box(
            degradation_transform, (source.x0, source.y0, source.x1, source.y1)
        )
        box = (
            original.x0 * raster.page_width / raster.width,
            original.y0 * raster.page_height / raster.height,
            original.x1 * raster.page_width / raster.width,
            original.y1 * raster.page_height / raster.height,
        )
        overlaps = [
            (overlap(box, line["bbox"]), index) for index, line in enumerate(lines)
        ]
        area, index = max(overlaps, default=(0, -1))
        if area:
            assigned[index].append(word)
        else:
            extras.append(word)
    rows, observations = [], []
    for index, line in enumerate(lines):
        emitted = assigned[index]
        text = " ".join(word.text for word in emitted)
        rows.append(error_counts(line["text"], text))
        tokens = [
            (token, word.confidence) for word in emitted for token in words(word.text)
        ]
        labels, _deleted = word_errors(
            words(line["text"]), [token for token, _ in tokens]
        )
        observations.extend(
            {"score": confidence, "wrong": wrong}
            for (_, confidence), wrong in zip(tokens, labels, strict=True)
        )
    if extras:
        rows.append(error_counts("", " ".join(word.text for word in extras)))
        observations.extend(
            {"score": word.confidence, "wrong": True} for word in extras
        )
    return {
        "geometry_aligned": aggregate(rows),
        "raw_emission_order": error_counts(
            "\n".join(line["text"] for line in lines),
            " ".join(word.text for word in reading.words),
        ),
        "observations": observations,
        "unmatched_items": len(extras),
        "alignment": (
            "maximum overlapping native line; engine item order kept within each line; "
            "unmatched emitted items count as insertions"
        ),
    }


def producer_digest():
    digest = hashlib.sha256()
    for path in (
        Path(__file__),
        *(
            ROOT / "backend/src/book_core/ocr" / name
            for name in ("engines.py", "geometry.py", "languages.py", "evaluation.py")
        ),
    ):
        digest.update(
            path.name.encode() + b"\0" + path.read_bytes().replace(b"\r\n", b"\n")
        )
    return digest.hexdigest()


def run_case(book, number, degradation, config, primary, secondary):
    from book_core.ocr.engines import compare_readings
    from book_core.ocr.languages import map_languages

    languages = config["book_languages"][book]
    frozen_producer = producer_digest()
    image, raster, transform, lines, excluded = render_case(book, number, degradation)
    if config.get("preprocess", "none") != "none":
        import cv2
        from book_core.ocr.geometry import decode_image, encode_image

        prepared = decode_image(image)
        mode = config["preprocess"]
        if mode == "binarize":
            gray = cv2.cvtColor(prepared, cv2.COLOR_BGR2GRAY)
            _, prepared = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
            )
        elif mode == "denoise":
            prepared = cv2.fastNlMeansDenoisingColored(prepared, None, 3, 3, 7, 21)
        elif mode == "contrast":
            lab = cv2.cvtColor(prepared, cv2.COLOR_BGR2LAB)
            lab[:, :, 0] = cv2.createCLAHE(clipLimit=2, tileGridSize=(8, 8)).apply(
                lab[:, :, 0]
            )
            prepared = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            raise ValueError(f"Unknown preprocessing experiment: {mode}")
        image = encode_image(prepared)
    identity = {
        "producer": frozen_producer,
        "book": book,
        "page": number,
        "degradation": degradation,
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "primary": primary.identity,
        "packs": primary.model_fingerprints((*map_languages(languages), "osd")),
        "secondary": secondary.identity if secondary else None,
        "languages": languages,
        "deskew": config.get("deskew", False),
        "preprocess": config.get("preprocess", "none"),
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    destination = OUT / "cases" / book / f"{number:06d}_{degradation}_{key}.json.gz"
    if destination.exists():
        return read_json(destination)
    result, timing = measured_read(
        primary, image, languages=languages, deskew=config.get("deskew", False)
    )
    readings = {"tesseract": result}
    timings = {"tesseract": timing}
    if secondary and secondary.supports(languages):
        other, timing = measured_read(
            secondary, image, languages=languages, transform=result.transform
        )
        readings["pp_ocrv5"] = other
        timings["pp_ocrv5"] = timing
        readings["combined"] = compare_readings(result, other)
        chosen = []
        for word in readings["combined"].words:
            alternatives = word.alternatives
            if (
                len(alternatives) == 1
                and alternatives[0].text
                and alternatives[0].confidence
                > (
                    word.raw_confidence
                    if word.raw_confidence is not None
                    else word.confidence
                )
            ):
                chosen.append(replace(word, text=alternatives[0].text))
            else:
                chosen.append(word)
        readings["confidence_selection_experiment"] = replace(
            readings["combined"],
            words=tuple(chosen),
            warnings=(
                *readings["combined"].warnings,
                "experiment only: incomparable reader scores choose alternative when higher",
            ),
        )
    record = {
        "key": key,
        "identity": identity,
        "figure_masked_span_ids": excluded,
        "native_truth": lines,
        "degradation_transform": asdict(transform),
        "raster_geometry": {
            "width": raster.width,
            "height": raster.height,
            "page_width": raster.page_width,
            "page_height": raster.page_height,
        },
        "readings": {name: asdict(reading) for name, reading in readings.items()},
        "scores": {
            name: score(reading, lines, raster, transform)
            for name, reading in readings.items()
        },
        "timing": timings,
        "orientation_expected": (360 - int(degradation.removeprefix("rotate"))) % 360
        if degradation.startswith("rotate")
        else 0,
        "orientation_observed": result.orientation.rotation_clockwise,
    }
    if producer_digest() != frozen_producer:
        raise RuntimeError(
            "OCR benchmark producer changed during a case; result not cached"
        )
    write_json(destination, record)
    record["artifact"] = str(destination)
    cer = record["scores"]["tesseract"]["geometry_aligned"]["cer"]
    print(
        f"{book} {number} {degradation}: CER {cer}",
        flush=True,
    )
    return record


def summarise(records):
    from book_core.ocr.evaluation import aggregate

    groups = defaultdict(list)
    for record in records:
        for reader, score_row in record["scores"].items():
            groups[
                (record["identity"]["book"], record["identity"]["degradation"], reader)
            ].append(score_row["geometry_aligned"])
    result = {
        "completed_cases": len(records),
        "groups": [
            {
                "book": book,
                "degradation": degradation,
                "reader": reader,
                "pages": len(rows),
                **aggregate(rows),
            }
            for (book, degradation, reader), rows in sorted(groups.items())
        ],
        "orientation": {
            "correct": sum(
                row["orientation_expected"] == row["orientation_observed"]
                for row in records
            ),
            "checked": len(records),
            "rotated_correct": sum(
                row["orientation_expected"] == row["orientation_observed"]
                for row in records
                if row["identity"]["degradation"].startswith("rotate")
            ),
            "rotated_checked": sum(
                row["identity"]["degradation"].startswith("rotate") for row in records
            ),
        },
    }
    write_plain(OUT / "summary.json", result)
    return result


def overlays(records, count=20):
    import cv2
    import numpy as np
    from book_core.ocr.geometry import (
        ImageTransform,
        apply_transform,
        decode_image,
        encode_image,
    )

    candidates = sorted(records, key=lambda row: row["key"])
    chosen = random.Random(SEED + 1).sample(candidates, min(count, len(candidates)))
    manifest = []
    for index, row in enumerate(chosen):
        identity = row["identity"]
        image, _, _, _, _ = render_case(
            identity["book"], identity["page"], identity["degradation"]
        )
        reading = row["readings"]["tesseract"]
        array = apply_transform(
            decode_image(image), ImageTransform(**reading["transform"])
        )
        for word in reading["words"]:
            x0, y0, x1, y1 = (round(value) for value in word["pixel_bbox"])
            confidence = word["confidence"]
            colour = (0, int(255 * confidence), int(255 * (1 - confidence)))
            cv2.rectangle(array, (x0, y0), (x1, y1), colour, 2)
        label = (
            f"{identity['book']} page {identity['page']} / {identity['degradation']}"
        )
        header = np.full((75, array.shape[1], 3), 255, dtype=np.uint8)
        cv2.putText(
            header, label, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2
        )
        cv2.putText(
            header,
            "Word confidence: red=0 green=1; scores are uncalibrated",
            (15, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            1,
        )
        path = (
            OUT
            / "overlays"
            / f"{index + 1:02d}_{identity['book']}_{identity['page']}_{identity['degradation']}.png"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encode_image(np.vstack((header, array))))
        manifest.append(
            {
                "image": str(path),
                "case_key": row["key"],
                "book": identity["book"],
                "page": identity["page"],
                "degradation": identity["degradation"],
                "cer": row["scores"]["tesseract"]["geometry_aligned"]["cer"],
            }
        )
    write_plain(OUT / "overlays/manifest.json", {"seed": SEED + 1, "pages": manifest})


_WORKER = None


def init_worker(config):
    global _WORKER
    _WORKER = (config, *make_engines(config), producer_digest())


def worker(case):
    config, primary, secondary, producer = _WORKER
    if producer_digest() != producer:
        raise RuntimeError(
            "OCR benchmark producing files changed after worker initialization"
        )
    return run_case(*case, config, primary, secondary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--select", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--book", choices=BOOKS, action="append")
    parser.add_argument(
        "--degradation", choices=(*DEGRADATIONS, "400dpi"), action="append"
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--page", type=int, action="append")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--overlays", action="store_true")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="skip book/page/degradation cases cached under an earlier producer; use only "
        "after a sample re-run proves that producer change left the readings identical",
    )
    args = parser.parse_args()
    if args.select:
        select()
        return
    if args.config is None:
        parser.error("--config is required for OCR; --select performs no OCR")
    config = json.loads(args.config.read_text("utf-8"))
    manifest = json.loads((OUT / "sample_manifest.json").read_text("utf-8"))
    if args.workers < 1:
        parser.error("--workers must be positive")
    cases = []
    for book in args.book or BOOKS:
        selected = manifest["books"][book]["selected"]
        if args.page:
            selected = [row for row in selected if row["page"] in args.page]
        if args.limit is not None:
            selected = random.Random(f"{SEED}:subset:{book}").sample(
                selected, min(args.limit, len(selected))
            )
        for row in selected:
            for degradation in args.degradation or DEGRADATIONS:
                prefix = f"{row['page']:06d}_{degradation}_"
                if args.missing_only and any(
                    (read_json(path)["identity"]["secondary"] is None)
                    == (not config.get("pp_recognizers"))
                    for path in (OUT / "cases" / book).glob(prefix + "*")
                ):
                    continue
                cases.append((book, row["page"], degradation))
    records = []
    if args.workers == 1:
        init_worker(config)
        for case in cases:
            records.append(worker(case))
            summarise(records)
    else:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        with ProcessPoolExecutor(
            max_workers=args.workers, initializer=init_worker, initargs=(config,)
        ) as pool:
            futures = [pool.submit(worker, case) for case in cases]
            for future in as_completed(futures):
                records.append(future.result())
                summarise(records)
    run_key = hashlib.sha256(
        json.dumps(
            {"config": config, "cases": cases, "producer": producer_digest()},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    write_plain(
        OUT / "runs" / f"{run_key}.json",
        {
            "config": config,
            "cases": cases,
            "summary": summarise(records),
            "case_keys": sorted(row["key"] for row in records),
        },
    )
    if args.overlays:
        overlays(records)


if __name__ == "__main__":
    main()
