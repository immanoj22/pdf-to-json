"""Record completed checks from their actual logs and frozen package verification."""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
from book_core.caching import code_digest

OUT = ROOT / "experiments/out/step17"


def receipt(name):
    path = OUT / name
    raw = path.read_bytes()
    text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
    return {"log": name, "sha256": hashlib.sha256(raw).hexdigest()}, text


def tests(name, expected):
    row, text = receipt(name)
    match = re.search(r"(?:^|\n)(\d+) passed(?:, \d+ warnings?)? in ([\d.]+)s", text)
    assert match and int(match[1]) == expected, f"Incomplete or failing test log: {name}"
    assert " FAILED " not in text and " ERROR " not in text
    return {**row, "passed": True, "count": int(match[1]), "seconds": float(match[2])}


def main():
    producer = code_digest("assembly")
    full = tests("final_full_suite_levels.log", 1183)
    closure = tests("cache_closure_after_cleanup.log", 62)
    ruff, text = receipt("final_ruff.log")
    assert text.strip() == "All checks passed!"
    path = OUT / "packaging/verification.json"
    wheel = json.loads(path.read_text("utf-8"))
    assert wheel["assembly_producer"] == producer
    for name, value in wheel["assets"].items():
        assert hashlib.sha256((ROOT / "backend/src" / name).read_bytes()).hexdigest() == value
    assert hashlib.sha256((path.parent / wheel["wheel"]).read_bytes()).hexdigest() == wheel["sha256"]
    result = {
        "full_suite": {**full, "assembly_producer": producer},
        "cache_closure_after_cleanup": closure,
        "ruff": {**ruff, "passed": True},
        "wheel_assets": {"passed": True, "verification": "packaging/verification.json",
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
    }
    (OUT / "final/validation_record.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
