"""Compare two converter outputs (final archive + publication) by content.

Usage: same_output.py <archive A> <publication A> <archive B> <publication B>
Every page file, the book record and every image of the archive, and the publication's
book.json and images, must be equal; only the stored cache keys (``cache_key_inputs``,
``cache_keys``, ``final_key``, ``key``, ``evidence_key`` and the run's producer digests) may
differ, since the producing code differs."""
import gzip, hashlib, json, sys
from pathlib import Path

KEYS = {"cache_key_inputs", "cache_keys", "final_key", "key", "evidence_key", "producers",
        "tables_key", "continuity_key", "lists_key", "characters_key", "native_key", "figures_key",
        "equations_key", "producer", "settings_sha256"}


def load(path):
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    if path.name.endswith((".json", ".json.gz")):
        return strip(json.loads(raw))
    return hashlib.sha256(raw).hexdigest()


def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in KEYS}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def files(root):
    return {p.relative_to(root).as_posix(): p for p in Path(root).rglob("*") if p.is_file()}


bad = 0
for a, b in ((sys.argv[1], sys.argv[3]), (sys.argv[2], sys.argv[4])):
    fa, fb = files(a), files(b)
    skip = {"manifest.json", "manifest.json.gz"}  # file digests and keys of the run
    names = sorted((set(fa) | set(fb)) - skip)
    for name in names:
        if name not in fa or name not in fb:
            print("only in one:", name); bad += 1; continue
        if load(fa[name]) != load(fb[name]):
            print("differs:", name); bad += 1
    print(f"{Path(a).name[:12]}…: {len(names)} files compared")
print("SAME CONTENT" if not bad else f"{bad} DIFFERENCES")
sys.exit(1 if bad else 0)
