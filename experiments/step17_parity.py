"""Step 17 parity: the stage outputs of the final runs equal the development paths.

- **Continuity**: ``link_book`` on inputs rebuilt from the final archive with the display
  equation units (``step17_continuity_dev.inputs``) equals the archive's continuity record
  (the Step 15 comparison: chains, candidates, dropped links).
- **Tables**: the Step 15 table parity on the final archives (``step15_parity.tables``).
- **Assembly**: the development assembly (``step17_assemble_dev``) of the final archive gives
  the published ``book.json``, compared after removing the fields that name the run
  (``metadata.converter``, ``metadata.settings_sha256``, ``metadata.content_sha256``,
  ``metadata.run``): every other byte equal.

Usage: python step17_parity.py [--book NAME] [--skip-tables]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from book_core.assembly.assemble import assemble
from book_core.assembly.profile import load_profile
from book_core.cache_store import read_json
from book_core.continuity.cache import link_book

import step14a_common as common
import step15_parity as parity
import step17_assemble_dev as adev
import step17_continuity_dev as cdev

FINAL = ROOT / "experiments/out/step17/final"
RUN_FIELDS = ("converter", "settings_sha256", "content_sha256", "run")


def continuity(book):
    run = common.read(FINAL / "performance" / f"{book}.json")["run"]
    archive = read_json(Path(run["output"]) / "book.json.gz")["continuity"]
    cdev.CAPTURE = FINAL
    pages, headings, lists, paragraphs, total, _ = cdev.inputs(book, True)
    found = link_book(pages, headings, lists, paragraphs, cdev.dev.vocabulary(book), total,
                      archive["source_sha256"])  # fmt: skip
    ours = sorted(parity._chain(c.model_dump(mode="json")) for c in found["chains"])
    theirs = sorted(parity._chain(c) for c in archive["chains"])
    same = (ours == theirs and len(found["candidates"]) == len(archive["candidates"])
            and len(found["dropped_links"]) == len(archive["dropped_links"]))  # fmt: skip
    return {"chains": len(theirs), "identical": same}


def assembly(book):
    run = common.read(FINAL / "performance" / f"{book}.json")["run"]
    published = json.loads((Path(run["book_json"]) / "book.json").read_text("utf-8"))
    native, evidence = adev.providers(book, run)
    profile = load_profile()
    data, _ = assemble(Path(run["output"]), native_page=native, evidence_page=evidence,
                       profile=profile, converter={"name": "book_core", "version": "dev",
                                                   "producer": "0" * 64},
                       settings_sha256="0" * 64,
                       run_date=published["metadata"]["run"]["date"])  # fmt: skip
    dev = data.model_dump(mode="json", by_alias=True)
    for row in (dev, published):
        for key in RUN_FIELDS:
            row["metadata"].pop(key, None)
    same = json.dumps(dev, sort_keys=True) == json.dumps(published, sort_keys=True)
    differ = [k for k in published if dev.get(k) != published.get(k)]
    return {"identical": same, "differing_sections": differ}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--skip-tables", action="store_true")
    args = parser.parse_args()
    parity.FINAL = FINAL
    bad = 0
    for name in [args.book] if args.book else common.BOOK_ORDER:
        row = {"continuity": continuity(name), "assembly": assembly(name)}
        if not args.skip_tables:
            row["tables"] = parity.tables(name)
            bad += bool(row["tables"]["differ"])
        bad += (not row["continuity"]["identical"]) + (not row["assembly"]["identical"])
        common.write(FINAL / "parity" / f"{name}.json", row)
        print(name, row["continuity"], row["assembly"],
              row.get("tables", {}).get("differ", [])[:3], flush=True)  # fmt: skip
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
