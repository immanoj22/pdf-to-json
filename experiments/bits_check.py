"""Export a published book as BITS (bits_base) and report what a BITS reader looks at.

Usage: PYTHONPATH=backend/src python experiments/bits_check.py PUBLICATION_DIR OUT_DIR ISBN TITLE
Read-only on the publication. Reports: disp-formula / inline-formula counts, the title of every
book-part, the reference entries (all, real, running-head fakes, duplicate ids, page ranges with a
space after the dash), section labels present, DTD errors and the lossless counts."""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from lxml import etree

from book_adapters.engine.profile_store import ProfileStore
from book_adapters.engine.formats_run import run_format

ROOT = Path(__file__).resolve().parents[1]


def text(el) -> str:
    return " ".join("".join(el.itertext()).split())


def main(pub: str, out: str, isbn: str, title: str) -> None:
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    settings = out_dir / f"{isbn}.yaml"
    settings.write_text(f"isbn: '{isbn}'\ntitle: {title}\nprofile: bits_base\n", "utf-8")
    store = ProfileStore(ROOT / "profiles", out_dir / "store")
    report = run_format("bits", pub, out_dir / "delivery", str(settings), "bits_base@1.0.0", store,
                        allow_alt_text_placeholders=True)
    main_file = next(f for f in (out_dir / "delivery").rglob("*.xml")
                     if etree.parse(str(f)).getroot().tag == "book")
    root = etree.parse(str(main_file), etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)).getroot()
    loss, dtd = report["checks"]["lossless"], report["checks"]["dtd"]
    print(f"file {main_file.name}: verdict {report.get('verdict')}")
    print(f"DTD errors {dtd['errors']} | lossless missing {loss['missing']} extra {loss['extra']} | split_words {loss.get('split_words', {}).get('split')}")
    print(f"disp-formula {len(root.findall('.//disp-formula'))} | inline-formula {len(root.findall('.//inline-formula'))}")
    for part in root.iter("book-part"):
        label = part.findtext("book-part-meta/title-group/label") or ""
        ttl = part.findtext("book-part-meta/title-group/title") or ""
        if part.get("book-part-type") in ("part", "chapter", None) and part.getparent().tag == "book-body":
            print(f"  book-part type={part.get('book-part-type')} label={label!r} title={ttl[:48]!r}")
    refs = root.findall(".//ref")
    ids = Counter(r.get("id") for r in refs)
    running = [r for r in refs if re.fullmatch(r"(?:[A-Z][\w-]*[ -]){1,6}[A-Z][\w-]*", text(r).strip()) and len(text(r)) < 60]
    ranges = [text(r) for r in refs if re.search(r"\d\s*[–-]\s+\d", text(r))]
    print(f"refs {len(refs)} | fake (short, no year) {sum(1 for r in refs if len(text(r)) < 70 and not re.search(r'(19|20)\d\d', text(r)))} | duplicate ids {sum(1 for v in ids.values() if v > 1)} | with a space after the dash {len(ranges)}")
    print(f"sections with a label starting 5.1 / 5.3: {[s.findtext('label') for s in root.iter('sec') if (s.findtext('label') or '').strip() in ('5.1', '5.3')]}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
