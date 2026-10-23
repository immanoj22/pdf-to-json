"""Restore pruned fixture-native dependencies under their verified current fingerprints.

No deletion and no reference/hold-out conversion. Only repository fixture PDFs whose
current native key occurs in the approved deletion subset can be restored here.
"""

import json
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
from book_core.cache_store import read_model, write_model
from book_core.extraction.fingerprints import source_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.objects.analysis import fingerprints
from book_core.objects.models import NativeObjectPage


def main():
    out = ROOT / "experiments/out/step17"
    audit = json.loads((out / "cache_prune_audit.json").read_text("utf-8"))
    selected = audit.get("approved", audit.get("selected"))
    if selected is None:
        raise ValueError(f"Unknown audit structure: {list(audit)}")
    native = {Path(row["path"]).name: row for row in selected
              if "/objects/native/" in row["path"].replace("\\", "/")}
    started = datetime.now(UTC).isoformat()
    clock = time.perf_counter()
    extractor = PyMuPDFExtractor("cpu")
    restored = []
    for folder in ("experiments/fixtures", "experiments/fixtures_unseen"):
        for source in sorted((ROOT / folder).glob("*.pdf")):
            digest = source_digest(source)
            key, _ = fingerprints(digest, extractor)
            row = native.get(key)
            if row is None:
                continue
            for item in row["files"]:
                path = (ROOT / item["path"]).resolve()
                path.relative_to((ROOT / ".cache/objects/native" / key).resolve())
                if path.exists():
                    continue
                number = int(path.stem)
                page = extractor.extract_object_page(source, number)
                write_model(path, page, key)
                read_model(path, NativeObjectPage, key)
                restored.append({"source": source.relative_to(ROOT).as_posix(),
                                 "path": path.relative_to(ROOT).as_posix(),
                                 "native_key": key, "bytes": path.stat().st_size,
                                 "page": number})
                print(restored[-1], flush=True)
    result = {"reason": "Retained derived fixture caches had indirect native dependencies "
                        "missed by the original cleanup audit",
              "plan_sha256": audit["plan_sha256"], "started_utc": started,
              "finished_utc": datetime.now(UTC).isoformat(),
              "elapsed_seconds": time.perf_counter() - clock,
              "restored_files": len(restored), "restored_bytes": sum(r["bytes"] for r in restored),
              "free_bytes_after": shutil.disk_usage(ROOT).free, "files": restored}
    (out / "cache_fixture_restoration_record.json").write_text(
        json.dumps(result, indent=1) + "\n", "utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items() if k != "files"}, indent=1))


if __name__ == "__main__":
    main()
