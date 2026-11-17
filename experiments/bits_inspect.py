"""Inspect a BITS delivery folder: parts, math, sections, references (read-only).
Usage: python experiments/bits_inspect.py DELIVERY_DIR"""
import collections
import glob
import re
import sys

from lxml import etree

f = [p for p in glob.glob(sys.argv[1] + "/**/*.xml", recursive=True) if etree.parse(p).getroot().tag == "book"][0]
root = etree.parse(f, etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)).getroot()
t = lambda e: " ".join("".join(e.itertext()).split())  # noqa: E731
print(f.split("/")[-1], "tags:", dict(collections.Counter(e.tag.split("}")[-1] for e in root.iter()).most_common(12)))
print("disp-formula", len(root.findall(".//disp-formula")), "| inline-formula", len(root.findall(".//inline-formula")),
      "| math elements", sum(1 for e in root.iter() if isinstance(e.tag, str) and e.tag.split("}")[-1] == "math"))
for p in root.iter("book-part"):
    ttl = p.find("book-part-meta/title-group/title")
    print("book-part", p.get("book-part-type"), p.get("id"), "label =", p.findtext("book-part-meta/title-group/label"),
          "title =", repr(t(ttl)[:50]) if ttl is not None else None, "| secs", len(p.findall(".//sec")))
secs = [(s.findtext("label"), t(s.find("title"))[:42]) for s in root.iter("sec")
        if s.find("title") is not None and re.match(r"5\.\d$", s.findtext("label") or "")]
print("sec labels 5.N:", secs)
refs = root.findall(".//ref")
print("refs", len(refs), "| mixed-citation", len(root.findall(".//mixed-citation")), "| element-citation", len(root.findall(".//element-citation")))
ids = collections.Counter(r.get("id") for r in refs)
print("duplicate ref ids:", [k for k, v in ids.items() if v > 1][:5])
fake = [(r.get("id"), t(r)[:60]) for r in refs if len(t(r)) < 80 and not re.search(r"(19|20)\d\d", t(r))]
print("fake-looking refs:", len(fake), fake[:3])
rng = [t(r)[:90] for r in refs if re.search(r"\d\s*[–-]\s+\d", t(r))]
print("page ranges with a space after the dash:", len(rng), rng[:2])
print("ref labels:", [r.findtext("label") for r in refs[:3]], "...")
