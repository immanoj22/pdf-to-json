"""Generate the Step 6 review report from completed, immutable experiment artifacts.

This script performs no extraction, inference, alignment or hold-out rerun. It refuses
incomplete gates and copies the unchanged full-book gate output only after JUnit passes.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from reference_paths import PROJECT_ROOT

from book_core.document_analysis.cache import load_artifact
from book_core.extraction.cache import payload_digest

OUT = PROJECT_ROOT / "experiments/out/step6"
REPORT = PROJECT_ROOT / "docs/step6_report.md"
BOOKS = (
    ("spanish_us_history", "Book 1: Spanish US history", "development"),
    ("immigrant_children", "Book 2: Immigrant Children", "hold-out; identity by text only"),
    ("art_therapy_index", "Book 3: art-therapy index", "hold-out; anecdotal"),
)


def read(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"Required final artifact is absent: {path.relative_to(PROJECT_ROOT)}")
    return json.loads(path.read_text("utf-8"))


def escape(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def table(headers, rows) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines.extend("| " + " | ".join(escape(value) for value in row) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def link(path: str, label="artifact") -> str:
    return f"[{label}](../{path})"


def percent(value) -> str:
    return "n/a" if value is None else f"{100 * value:.2f}%"


def count(value) -> str:
    return f"{value:,}"


def mapping(values: dict, limit=10) -> str:
    pairs = sorted(values.items(), key=lambda row: (-row[1], str(row[0])))
    result = "; ".join(f"{key}: {count(value)}" for key, value in pairs[:limit]) or "none"
    return result + (f"; +{len(pairs) - limit} other kinds" if len(pairs) > limit else "")


def style_descriptor(row: dict | None) -> str:
    if not row:
        return "none"
    flags = [name for name in ("bold", "italic") if row[name]]
    return (
        f"{row['font_family']}; {row['size']:g} pt; "
        f"{', '.join(flags) or 'regular'}; #{row['color']:06x}; {row['caps']}"
    )


def junit_gate() -> tuple[int, float]:
    path = OUT / "pytest.xml"
    if not path.is_file():
        raise ValueError("Final experiments/out/step6/pytest.xml is required")
    cases = list(ET.parse(path).getroot().iter("testcase"))
    if not cases or any(
        child.tag in {"failure", "error", "skipped"} for case in cases for child in case
    ):
        raise ValueError("JUnit is empty or has failing/skipped tests; report generation refused")
    if not any(case.get("name") == "test_full_available_book" for case in cases):
        raise ValueError("The unchanged full-book testcase must pass in this final run")
    return len(cases), sum(float(case.get("time", 0)) for case in cases)


def verify_holdouts(summaries: dict) -> list[dict]:
    path = OUT / "holdout_runs.jsonl"
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]
    result = []
    for book, _, _ in BOOKS[1:]:
        started = [row for row in rows if row["book"] == book and row["action"] == "started"]
        completed = [row for row in rows if row["book"] == book and row["action"] == "completed"]
        if len(started) != 1 or len(completed) != 1:
            raise ValueError(f"Expected one completed final hold-out run for {book}")
        first, final = started[0], completed[0]
        summary = summaries[book]
        if (
            first["run_id"] != final["run_id"]
            or first["producer_sha256"] != summary["producer_sha256"]
            or final["artifact_key"] != summary["artifact_key"]
            or final["artifact_payload_sha256"] != summary["artifact_payload_sha256"]
        ):
            raise ValueError("Hold-out run provenance does not match its final artifact")
        result.append(final)
    if len({row["evaluation_producer_sha256"] for row in result}) != 1:
        raise ValueError("Hold-out evaluation producer changed between final runs")
    return result


def native_sample(source_sha256: str, sample: dict) -> str:
    """Resolve an illustrative source line from the active project's verified page cache."""
    directory = PROJECT_ROOT / ".cache/step6/native"
    for manifest_path in sorted(directory.glob("*/manifest.json")):
        manifest = read(manifest_path)
        if manifest["source_sha256"] != source_sha256:
            continue
        page_path = manifest_path.parent / f"page_{sample['page']:06d}.json"
        entry = read(page_path)
        payload = entry["payload"]
        if payload_digest(payload) != entry["payload_sha256"]:
            raise ValueError("Native page cache checksum differs")
        expected = manifest["page_hashes"][sample["page"] - 1]
        if expected != entry["payload_sha256"] or payload["source_sha256"] != source_sha256:
            raise ValueError("Native page cache manifest differs")
        store = payload["store"]
        line = next((row for row in store["lines"] if row["id"] == sample["line_id"]), None)
        if line is not None:
            text = " ".join(
                "".join(store["spans"][sid]["raw_text"] for sid in line["span_ids"]).split()
            )
            return text[:117] + ("..." if len(text) > 117 else "")
    raise ValueError("Illustrative repetition line is absent from the active native page cache")


def profile_table(summaries: dict) -> str:
    rows = []
    for book, name, split in BOOKS:
        row = summaries[book]
        toc_pages = [str(page["page"]) for page in row["toc_pages"]]
        shown = ", ".join(toc_pages[:16]) + (" ..." if len(toc_pages) > 16 else "")
        rows.extend(
            [
                (name, "Split", split),
                (
                    name,
                    "Pages / retained tokens",
                    f"{count(row['pages'])} / {count(row['retained_tokens'])}",
                ),
                (name, "Modal body-style candidate", style_descriptor(row["body_style"])),
                (name, "Body-style character share", percent(row["body_style_confidence"])),
                (
                    name,
                    "Style keys / size clusters / style clusters",
                    f"{row['style_keys']} / {row['size_clusters']} / {row['style_clusters']}",
                ),
                (
                    name,
                    "Bookmarks / printed entries / PDF labels",
                    f"{row['bookmarks']} / {row['printed_entries']} / {row['pdf_page_labels']}",
                ),
                (name, "Printed TOC candidate pages", f"{len(toc_pages)}: {shown or 'none'}"),
                (
                    name,
                    "Geometry-only ambiguous TOC pages",
                    sum(
                        bool(page.get("features", {}).get("geometry_only_ambiguous"))
                        for page in row["toc_pages"]
                    ),
                ),
                (
                    name,
                    "Native blocks / model mixed-segment evidence",
                    f"{count(row['language_blocks'])} / {count(row['mixed_language_blocks'])}",
                ),
                (name, "Block language evidence", mapping(row["languages"])),
                (
                    name,
                    "Vocabulary / native-adjacent join hypotheses / attested",
                    f"{count(row['vocabulary_size'])} / {count(row['hyphen_joins'])} / "
                    f"{count(row['attested_hyphen_joins'])}",
                ),
                (
                    name,
                    "Device / wall seconds",
                    f"{row['resolved_device']} / {row['seconds']:,.2f}",
                ),
                (
                    name,
                    "Book artifact cache hit / native hits / native misses",
                    f"{row['artifact_cache_hit']} / {row['native_cache_hits']} / "
                    f"{row['native_cache_misses']}",
                ),
                (name, "Cached book artifact", link(row["artifact"], row["artifact_key"][:16])),
            ]
        )
    return table(("Book", "Evidence", "Observed"), rows)


def book_evaluation(book: str, name: str, summary: dict, evaluation: dict) -> str:
    artifact = load_artifact(PROJECT_ROOT / summary["artifact"])
    if payload_digest(artifact) != summary["artifact_payload_sha256"]:
        raise ValueError("Book summary payload digest differs")
    if artifact["provenance"]["producer_sha256"] != summary["producer_sha256"]:
        raise ValueError("Book summary producer digest differs")
    if evaluation["reference_human_approved"] or evaluation["overall"] is not None:
        raise ValueError("Unexpected gold status or aggregate evaluation score")
    parts = [
        f"### {name}\n",
        f"Frozen title similarity threshold: {evaluation['title_similarity_threshold']:.1f}/100.\n",
    ]
    if book == "spanish_us_history":
        matched = evaluation["navigation"]["bookmark"]["title_matches"]
        parts.append(
            "Book 1's native bookmark titles are production file identifiers, yielding "
            f"{matched} reference heading-title matches. Their native PDF destinations remain "
            "evidence; no book-specific title decoding was attempted.\n"
        )
    if book == "immigrant_children":
        precision = evaluation["navigation"]["printed_toc"]["title_precision"]
        parts.append(
            "Most Book 2 printed candidates are index rows with valid PDF labels. Its "
            f"{percent(precision)} printed title precision shows that valid labels alone do "
            "not distinguish a table of contents from an index. No post-hold-out tuning "
            "was performed.\n"
        )
    nav_rows = []
    for kind, label in (
        ("bookmark", "Bookmarks"),
        ("printed_toc", "Printed TOC"),
        ("combined_unique", "Combined unique"),
    ):
        row = evaluation["navigation"][kind]
        nav_rows.append(
            (
                label,
                row["entries"],
                row["reference_heading_units"],
                row["title_matches"],
                f"{percent(row['title_precision'])} / {percent(row['title_recall'])}",
                row["title_and_target_matches"],
                f"{percent(row['title_and_target_precision'])} / "
                f"{percent(row['title_and_target_recall'])}",
                f"{row['unresolved_targets']} / {row['ambiguous_targets']}",
            )
        )
    parts.append(
        table(
            (
                "Navigation",
                "Entries",
                "Ref. headings",
                "Title matches",
                "Title precision / recall",
                "Title + target matches",
                "Title + target precision / recall",
                "Unresolved / ambiguous",
            ),
            nav_rows,
        )
    )
    repetition = evaluation["repetition"]
    parts.append(
        table(
            ("Repetition evidence", "Count"),
            [
                ("Candidates", repetition["candidates"]),
                ("Unique retained candidate tokens", count(repetition["unique_candidate_tokens"])),
                (
                    "Not aligned to a reference unit (absence proxy)",
                    count(repetition["not_aligned_to_reference"]),
                ),
                (
                    "Aligned to reference units (potential false candidates)",
                    count(repetition["aligned_to_reference"]),
                ),
                ("Aligned unit kinds", mapping(repetition["aligned_unit_kinds"])),
                (
                    "Position bands",
                    mapping(
                        dict(Counter(row["band"] for row in artifact["repetition"]["candidates"]))
                    ),
                ),
                (
                    "Physical-page periodicity",
                    mapping(
                        dict(
                            Counter(
                                row["periodicity"] for row in artifact["repetition"]["candidates"]
                            )
                        )
                    ),
                ),
            ],
        )
    )
    candidates = sorted(
        repetition["candidate_details"], key=lambda row: (-row["aligned"], row["candidate"])
    )
    examples = []
    for row in [candidate for candidate in candidates if candidate["aligned"]][:3]:
        examples.append(
            (
                native_sample(summary["source_sha256"], row["sample"]),
                row["band"],
                row["pages"],
                f"{row['confidence']:.3f}",
                f"{count(row['aligned'])} / {count(row['tokens'])}",
                mapping(row["aligned_unit_kinds"]),
            )
        )
    if examples:
        parts.append(
            "Largest reference-aligned candidate groups; the source line is illustrative, not "
            "a furniture decision.\n"
        )
        parts.append(
            table(
                (
                    "Source line sample",
                    "Band",
                    "Pages",
                    "Confidence",
                    "Aligned / candidate tokens",
                    "Reference kinds",
                ),
                examples,
            )
        )
    styles = artifact["style"]["styles"]
    cluster_styles = {}
    for style in styles:
        cluster_styles.setdefault(style["style_cluster_id"], []).append(style)
    heading_styles = evaluation["heading_styles"]
    total = sum(row["aligned_heading_tokens"] for row in heading_styles["clusters"])
    style_rows = []
    for row in heading_styles["clusters"][:8]:
        members = cluster_styles[row["style_cluster_id"]]
        sizes = sorted({member["size"] for member in members})
        descriptor = style_descriptor(members[0])
        if len(sizes) > 1:
            descriptor += f"; cluster sizes {sizes[0]:g}-{sizes[-1]:g} pt"
        style_rows.append(
            (
                row["style_cluster_id"][:12],
                descriptor,
                row["heading_units"],
                count(row["aligned_heading_tokens"]),
                percent(row["aligned_heading_tokens"] / total if total else None),
            )
        )
    parts.append(
        f"Reference heading units: **{heading_styles['heading_units']}**. Top eight observed "
        f"clusters follow; these are distributions, with no classifier or heading level.\n"
    )
    parts.append(
        table(
            (
                "Style cluster",
                "Observed style",
                "Heading units touching cluster",
                "Heading tokens",
                "Token share",
            ),
            style_rows,
        )
    )
    if not style_rows:
        parts.append("No aligned heading tokens support a style distribution.\n")
    parts.append(
        f"Full per-book metrics: "
        f"{link(f'experiments/out/step6/{book}/evaluation.json', 'evaluation')}.\n"
    )
    return "\n".join(parts)


def language_comparison(comparison: dict, dependencies: dict) -> str:
    parts = ["## Language libraries and licenses\n"]
    parts.append(
        table(
            ("Package", "Pin", "Scope", "License", "Recorded installed bytes, excluding bytecode"),
            [
                (
                    row["name"],
                    row["version"],
                    row["scope"],
                    f"[{row['license']}]({row['upstream_license']})",
                    count(row["installed_recorded_bytes"]),
                )
                for row in dependencies["packages"]
            ],
        )
    )
    parts.append(
        table(
            (
                "Book",
                "Library",
                "Top-1 / language-bearing sample",
                "Accepted correct / emitted",
                "Warm ms / block",
            ),
            [
                (
                    "Book 1" if row["book"] == "spanish_us_history" else "Book 2",
                    row["library"],
                    f"{row['top1_correct']} / {row['language_bearing_samples']}",
                    f"{row['accepted_correct']} / {row['accepted_evidence']}"
                    if row["accepted_evidence"] is not None
                    else "no abstention wrapper",
                    f"{row['warm_milliseconds_per_block']:.4f}",
                )
                for row in comparison["metrics"]
            ],
        )
    )
    parts.append(
        "Lingua 2.2.0 is selected behind `LanguageDetector` for native mixed-language segments, "
        "with all supported languages by default. The small monolingual sample favors langid on "
        "book 1; both score 11/11 on book 2. Each book also contains one manually annotated "
        "nonlinguistic block, excluded from Top-1 accuracy. Lingua confidently calls the "
        "personal-name-only index English: a documented false result, not corrected after "
        "hold-out sampling.\n"
    )
    sizes = comparison["libraries"]
    parts.append(
        f"Comparison-time on-disk sizes, including generated bytecode: Lingua "
        f"{sizes['lingua-language-detector']['installed_bytes'] / 1048576:.2f} MiB, "
        f"langid {sizes['langid']['installed_bytes'] / 1048576:.2f} MiB; langid reuses "
        f"existing NumPy. "
        "Warm timing averages five repetitions and includes Lingua segmentation. Constructor "
        "timing "
        "excludes lazy inference/model loading. Scores are library evidence, not calibrated "
        "correctness probabilities. No GPL/AGPL language or repetition candidate was installed.\n"
    )
    parts.append(
        "The 24 source-native blocks were selected deterministically and annotated before "
        "predictions. "
        "Bilingual, Arabic, Hebrew and unspaced Japanese behavior is synthetic-test coverage. "
        "See the [annotated sample](../experiments/step6_language_sample.json), "
        "[measured comparison](../experiments/out/step6/language_comparison.json), "
        "[dependency audit](../experiments/out/step6/dependencies.json) and "
        "[dependency decisions](dependencies.md).\n"
    )
    return "\n".join(parts)


def main() -> None:
    passed, test_seconds = junit_gate()
    crosscheck = read(OUT / "original_source_crosscheck.json")
    if (crosscheck["pages"], crosscheck["missing"], crosscheck["extra"]) != (24, 0, 0):
        raise ValueError("The unchanged 24-page source cross-check did not pass")
    integrity = read(OUT / "gold_integrity.json")
    if integrity["modified_gold"] or any(
        row["checksums"] != "verified" for row in integrity["derived_gold"]
    ):
        raise ValueError("Derived-gold integrity did not pass")
    full_path = PROJECT_ROOT / "experiments/out/step4a/full_book.json"
    full = read(full_path)
    if (
        not full["passing"]
        or full["node_token_count"] != 495751
        or any(
            full[key] != 0
            for key in (
                "missing_token_count",
                "extra_token_count",
                "expected_missing_token_count",
                "expected_extra_token_count",
            )
        )
    ):
        raise ValueError("The unchanged full-book gate did not pass")
    ruff_log = (OUT / "ruff.log").read_text("utf-8")
    if "All checks passed!" not in ruff_log or not any(
        marker in ruff_log for marker in ("already formatted", "left unchanged")
    ):
        raise ValueError("Final Ruff check and format evidence is required")
    summaries = {book: read(OUT / book / "summary.json") for book, _, _ in BOOKS}
    evaluations = {book: read(OUT / book / "evaluation.json") for book, _, _ in BOOKS}
    if len({row["producer_sha256"] for row in summaries.values()}) != 1:
        raise ValueError("Document producer changed between development and hold-out runs")
    if summaries[BOOKS[0][0]]["retained_tokens"] != 495751:
        raise ValueError("Book 1 evidence does not preserve the full-book retained-token gate")
    holdouts = verify_holdouts(summaries)
    comparison = read(OUT / "language_comparison.json")
    dependencies = read(OUT / "dependencies.json")
    if dependencies["new_copyleft_candidates"]:
        raise ValueError("Unexpected new copyleft candidate in dependency audit")
    sample_log = OUT / "language_sample_runs.jsonl"
    if not sample_log.is_file() or not (PROJECT_ROOT / "docs/dependencies.md").is_file():
        raise ValueError("Language sample log and dependency documentation are required")
    overlays = summaries[BOOKS[0][0]]["overlays"]
    if (
        len(overlays) != 5
        or len(set(overlays)) != 5
        or any(not (PROJECT_ROOT / path).is_file() for path in overlays)
    ):
        raise ValueError("Exactly five completed book 1 overlays are required")
    parts = [
        "# Step 6: document-wide evidence\n",
        "Whole-book typography, navigation, repetition, native-block language and vocabulary "
        "evidence "
        "is cached for later stages. Confidence is evidence, not a role decision. No heading "
        "levels, "
        "furniture removal, paragraph boundaries, reading order or zones are decided here. "
        "The text ledger and gold are untouched; old projects remain read-only.\n",
        "## Gates and provenance\n",
        table(
            ("Gate", "Result", "Evidence"),
            [
                (
                    "Earlier and new tests",
                    f"{passed} passed; 0 failed / 0 skipped; testcase time {test_seconds:,.2f} s",
                    "[JUnit](../experiments/out/step6/pytest.xml)",
                ),
                (
                    "24 measured pages vs original sources",
                    "0 missing / 0 extra on all 24",
                    "[source "
                    "cross-check](../experiments/out/step6/original_source_crosscheck.json)",
                ),
                (
                    "Full book",
                    f"{count(full['node_token_count'])} retained tokens; 0 missing / 0 extra",
                    "[unchanged full-book gate](../experiments/out/step6/full_book.json)",
                ),
                (
                    "Ruff check / format",
                    "pass, run from backend/",
                    "[log](../experiments/out/step6/ruff.log)",
                ),
                (
                    "Derived-gold checksums after LF renormalization",
                    "all three books verify; no gold edits",
                    "[integrity](../experiments/out/step6/gold_integrity.json)",
                ),
                (
                    "Scope",
                    "Step 6 only; semantic decisions deferred",
                    "[confirmed decisions](decisions.md)",
                ),
            ],
        ),
        "`.gitattributes` now has `* text=auto eol=lf`; both hand-made gold and derived "
        "gold are protected by `-text` exceptions, preserving their exact bytes. "
        "Reference units are provisional (`human_approved: false`). Book 2 has identity by "
        "text only; "
        "book 3 is anecdotal, and its low-confidence page markers remain excluded from gates. "
        "Metrics below are per book, with no overall score.\n",
        "The book cache key covers PDF hash, complete page/metadata/block digests, extractor "
        "identity, producer source digest, runtime/library versions, configuration and the actual "
        "bundled language-model binary hash. Per-page native caching remains source-hashed and "
        "atomic. "
        "Changed producer code requires a worker restart.\n",
        "## Whole-book profiles\n",
        profile_table(summaries),
        "The body-style candidate is the character-weighted mode, with rounded size, normalized "
        "family, native bold/italic flags, color and caps. All extracted lines retain style "
        "evidence; "
        "no font-size-only heading classifier is introduced. Vocabulary retains the unchanged "
        "NFKC Unicode token rule and TrimBox retention. Native-adjacent spelling attestations do "
        "not establish paragraph continuity or reading order.\n",
        "Reported whole-book wall times include cache effects, evaluation and optional overlays.\n",
        "Scope: style and native-block language profiles include all extracted lines/blocks, "
        "including explicit TrimBox-excluded extraction evidence. Vocabulary, repetition and "
        "derived-gold evaluation use retained content. Overlays show all native styles, "
        "including prepress text outside the content frame; Step 6 makes no semantic "
        "retention decision.\n",
        "Language distributions and mixed-segment counts are unvalidated model evidence, "
        "not proven monolingual or bilingual truth. Caps-sensitive style keys can split "
        "typography into many clusters; the cluster count is descriptive.\n",
        "## Evaluation against provisional derived gold\n",
        "Titles use one-to-one fuzzy matching of casefolded Unicode tokens at the frozen "
        "similarity "
        "threshold. Target success requires one resolved physical page in the matched heading's "
        "aligned token runs. Precision divides by entries; recall divides by reference heading "
        "units. "
        "Combined navigation deduplicates identical titles with equal resolved target pages "
        "or equal unresolved printed labels; destination-free entries remain separate. "
        "Unresolved labels stay unresolved; no page offset is guessed. When PDF labels are "
        "absent, printed targets remain unresolved while bookmark destinations remain usable. "
        "Navigation/title precision is an evidence diagnostic, not heading classification.\n",
    ]
    for book, name, _ in BOOKS:
        parts.append(book_evaluation(book, name, summaries[book], evaluations[book]))
    parts.extend(
        [
            "Unaligned repetition tokens are an absence proxy, not proof of reference absence or "
            "furniture. Reference-aligned tokens show potential false candidates and remain "
            "retained. "
            "Unit-kind counts may overlap for shared tokens; heading units can touch multiple "
            "style "
            "clusters. Heading-style statistics assign each token its containing line's "
            "dominant style cluster and lose within-line mixtures; full style distributions "
            "remain retained in the cached artifact. Physical PDF parity is separate from "
            "printed label parity.\n",
            language_comparison(comparison, dependencies),
            "## Five review overlays\n",
            "`S` labels the style cluster; red frames mark repetition candidates; blue frames "
            "and `T>` "
            "show printed navigation links. Sidecars preserve full IDs and incoming links. "
            "All five overlays were visually reviewed; map overlays are dense. Empty `T>` "
            "means the printed target is unresolved; its original locator label remains in "
            "the navigation artifact.\n",
            table(
                ("Overlay", "Sidecar"),
                [
                    (
                        link(path, Path(path).stem),
                        link(
                            str(Path(path).with_suffix(".json")).replace("\\", "/"), "line evidence"
                        ),
                    )
                    for path in overlays
                ],
            ),
            "## Hold-out discipline\n",
            table(
                ("Book", "Final whole-book runs", "Frozen producer", "Artifact key"),
                [
                    (
                        "Book 2" if row["book"] == "immigrant_children" else "Book 3",
                        "1 started / 1 completed",
                        row["producer_sha256"][:16],
                        row["artifact_key"][:16],
                    )
                    for row in holdouts
                ],
            ),
            "Book 1 was the development source. Books 2 and 3 each ran once after freezing; the "
            "[hold-out log](../experiments/out/step6/holdout_runs.jsonl) records hashes and "
            "configuration. "
            "The explicitly requested book 2 library sample is separately recorded in the "
            "[language sample log](../experiments/out/step6/language_sample_runs.jsonl); it "
            "performed no "
            "whole-book evidence analysis or derived-gold evaluation.\n",
            "## Limitations and decisions for review\n",
            "- Navigation is partial evidence: complex wraps, nonstandard locators and "
            "repeated table/index "
            "structures may be missed or falsely proposed. Geometry-only TOC evidence can "
            "flag index/table pages and is explicitly ambiguous. Review per-book precision/recall "
            "and unresolved targets before later stages consume this evidence. No thresholds "
            "were tuned on "
            "the hold-outs.\n"
            "- Repeated edge text can be real content. The K1 science-fixture `Energy` label "
            "is outside "
            "these three approved reference pairs, so no measured K1 result is claimed. "
            "Synthetic repeated "
            "content/table-label cases remain candidates, illustrating why Step 8 must decide "
            "furniture.\n"
            "- Style clusters describe typography; reference headings can share body styles, "
            "and the mode "
            "can include retained furniture or production text. Cluster shares are not heading "
            "probabilities. Caps and other style attributes can produce numerous small clusters; "
            "no semantic grouping is inferred.\n"
            "- Language scores can be confidently wrong on names; the annotated sample is "
            "small and has "
            "no naturally bilingual block. Whole-book mixed-segment counts are unvalidated "
            "model outputs, not bilingual truth. Confirm whether Lingua's roughly 291 MiB "
            "footprint "
            "and mixed-language "
            "segments justify the measured speed/size tradeoff. Changing engines later "
            "requires an explicit, "
            "logged cache/evaluation change.\n"
            "- Native order is preserved as extraction evidence. Hyphen hypotheses only "
            "describe that "
            "sequence; no joins cross pages, and CJK word segmentation remains deferred.\n"
            "- Review the evidence artifact shape and unresolved/ambiguous navigation policy "
            "before "
            "authorizing subsequent stages. This gate makes no heading, furniture or zone "
            "decision.\n",
            "## Reproduce\n",
            "From the project root (hold-out commands are for a fresh run; the runner refuses "
            "a second "
            "started run in the existing log):\n",
            "```powershell\n"
            ".venv/Scripts/python.exe experiments/step6_integrity.py\n"
            ".venv/Scripts/python.exe experiments/step6_dependencies.py\n"
            ".venv/Scripts/python.exe experiments/step6_source_crosscheck.py\n"
            ".venv/Scripts/python.exe experiments/step6_run.py --book spanish_us_history "
            "--overlays\n"
            ".venv/Scripts/python.exe experiments/step6_run.py --book immigrant_children "
            "--holdout\n"
            ".venv/Scripts/python.exe experiments/step6_run.py --book art_therapy_index --holdout\n"
            ".venv/Scripts/python.exe experiments/step6_report.py\n"
            "```\n",
            "Overlay an existing cached book artifact using explicit source, page and output "
            "arguments (from the project environment):\n",
            "```powershell\n"
            "python -m book_core overlay SOURCE.pdf --page PAGE --out OUTPUT.png "
            "--document-artifact BOOK_CACHE.json\n"
            "```\n",
            "Tests and Ruff must run from `backend/`; report generation follows their final "
            "completed logs. "
            "From `backend/`:\n",
            "```powershell\n"
            "../.venv/Scripts/python.exe -m pytest "
            "--junitxml=../experiments/out/step6/pytest.xml\n"
            "../.venv/Scripts/python.exe -m ruff check .\n"
            "../.venv/Scripts/python.exe -m ruff format --check .\n"
            "```\n",
            "The language comparison uses the committed annotations with "
            "`python experiments/step6_language_compare.py --compare`, recording any "
            "sample-only rerun. "
            "See [dependencies](dependencies.md) for installation pins and licenses.\n",
            "**Step 6 stops here for owner review. Step 7 has not started.**\n",
        ]
    )
    (OUT / "full_book.json").write_bytes(full_path.read_bytes())
    REPORT.write_text("\n".join(parts).rstrip() + "\n", "utf-8", newline="\n")
    print(
        f"Wrote {REPORT.relative_to(PROJECT_ROOT)} from completed artifacts; no analysis was rerun."
    )


if __name__ == "__main__":
    main()
