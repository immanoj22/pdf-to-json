"""Compare each Step 16 final archive with the Step 15 archive, file by file (sha256)."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S15 = json.loads(
    (ROOT / "experiments/out/step15/final/final_outputs.json").read_text("utf-8")
)


def digests(root):
    root = Path(root)
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def main(books):
    report = {}
    for book in books:
        run = json.loads(
            (ROOT / f"experiments/out/step16/final/performance/{book}.json").read_text(
                "utf-8"
            )
        )["run"]
        new_root = Path(run["output"])
        old_root = Path(S15[book]["output"])
        old, new = digests(old_root), digests(new_root)
        differing = sorted(k for k in old.keys() & new.keys() if old[k] != new[k])
        report[book] = {
            "step15_archive": str(old_root),
            "step16_archive": str(new_root),
            "files_step15": len(old),
            "files_step16": len(new),
            "only_in_step15": sorted(old.keys() - new.keys()),
            "only_in_step16": sorted(new.keys() - old.keys()),
            "differing_files": differing,
            "byte_identical": old == new,
        }
        print(book, report[book]["byte_identical"], len(differing), flush=True)
    out = ROOT / "experiments/out/step16/final/archive_identity.json"
    out.write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(
        sys.argv[1:]
        or [
            "art_therapy_index",
            "immigrant_children",
            "medical_anatomy",
            "spanish_us_history",
            "statistics",
        ]
    )
