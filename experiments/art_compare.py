"""Export one converted book with the code and profiles at SRC/PROFILES (DocBook + ePub, fixed
time), print a digest of every output file. Run twice (baseline and changed) and diff."""
import hashlib, json, sys
from pathlib import Path
src, profiles, book, out = sys.argv[1:5]
sys.path.insert(0, src)
from book_adapters.engine.epub_run import run_epub
from book_adapters.engine.profile_store import ProfileStore
from book_adapters.engine.run import run_book
out = Path(out); out.mkdir(parents=True, exist_ok=True)
settings = out / "s.yaml"
settings.write_text("isbn: '9780306406157'\ntitle: A Test Book\nedition: First Edition\nprofile: jaypee_v3\n"
                    "authorgroups:\n  - - firstname: Ann\n      surname: Author\n")
store = ProfileStore(Path(profiles), out / "store")
r = run_book(Path(book), out / "docbook", settings, None, store, allow_alt_text_placeholders=True)
e = run_epub(Path(book), out / "epub", settings, None, store, allow_alt_text_placeholders=True, modified="2026-11-04T00:00:00Z")
loss = r["checks"]["lossless"]; print("docbook", r["status"], "lossless", loss["missing"], loss["extra"], "dtd", (r["checks"].get("dtd") or {}).get("errors"))
print("epub lossless", e["checks"]["epub"]["lossless"]["missing"], e["checks"]["epub"]["lossless"]["extra"])
digest = {}
for sub in ("docbook", "epub"):
    for p in sorted((out / sub).rglob("*")):
        if p.is_file() and "report" not in p.parts and p.suffix not in (".epub", ".zip"):
            digest[p.relative_to(out).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
json.dump(digest, open(out / "digest.json", "w"), indent=0)
print("files", len(digest))
