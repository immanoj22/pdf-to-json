"""Read-only reference character counts and explicit source-witness contexts."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path  # noqa: E402

from book_core.cache_store import read_json  # noqa: E402
from book_core.model.spans import ExtractedPage  # noqa: E402
from book_core.reference.xml_reader import load_tree  # noqa: E402

OUT = ROOT / "experiments/out/step11d/diagnosis"
rows = {}
for key in ("spanish_xml", "immigrant_xml", "medical_xml"):
    data = reference_path(key).read_bytes()
    root, repairs = load_tree(data)
    text = "".join(root.itertext())
    rows[key] = {
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "character_counts": {
            f"U+{cp:04X}": text.count(chr(cp))
            for cp in (0x03B2, 0x01CA, 0x00BE, 0x25C6, 0x2666, 0x2022, 0x27A2)
        },
        "english_example_counts": {
            phrase: text.count(phrase)
            for phrase in (
                "LEARN THE EVENTS LESSONS",
                "INQUIRY ACTIVITY LESSONS",
                "Progressive Era Reforms",
            )
        },
        "in_memory_repairs": [{"kind": r.kind, "detail": r.detail} for r in repairs],
    }
    if key != "medical_xml":
        continue
    normalized = " ".join(text.split())
    archive = json.loads(
        (ROOT / "experiments/out/step11c/archive/medical_anatomy.json").read_text("utf8")
    )
    contexts = []
    # Explicit witness page arguments, not production heuristics.
    for number in (41, 55):
        page = ExtractedPage.model_validate(
            read_json(Path(archive["output"]) / f"page_{number:06d}.json.gz")["source"]
        )
        texts = [page.store.raw_line_text(line) for line in page.store.lines]
        for index, native in enumerate(texts):
            if "\u01ca" in native:
                phrase = native.replace("\u01ca", "").strip()
            elif "\u00be" in native:
                phrase = texts[index + 1].strip()
            else:
                continue
            position = normalized.casefold().find(phrase.casefold())
            contexts.append(
                {
                    "page": number,
                    "source_line_id": page.store.lines[index].id,
                    "native_text": native,
                    "reference_search": phrase,
                    "reference_context": (
                        normalized[max(0, position - 45) : position + len(phrase) + 80]
                        if position >= 0
                        else None
                    ),
                    "interpretation": (
                        "Content correspondence only; no repair inferred from reference text."
                    ),
                }
            )
    rows[key]["medical_marker_contexts"] = contexts
(OUT / "reference_content.json").write_text(
    json.dumps(rows, indent=2, ensure_ascii=False) + "\n", "utf8"
)
print({key: row["character_counts"] for key, row in rows.items()})
