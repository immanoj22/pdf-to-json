"""Inspect exact new dependency wheels in memory for license closure; never install."""

from __future__ import annotations

import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step6b/transitive_audit.json"
PACKAGES = ["scipy", "joblib", "threadpoolctl", "narwhals", "cloudpickle"]


def main():
    rows = []
    for name in PACKAGES:
        primary = f"https://pypi.org/pypi/{name}/json"
        data = json.load(urllib.request.urlopen(primary, timeout=45))
        wheel = next(
            (
                x
                for x in data["urls"]
                if "cp314-cp314-win_amd64" in x["filename"] or "py3-none-any" in x["filename"]
            ),
            None,
        )
        row = {
            "package": name,
            "version": data["info"]["version"],
            "primary_url": primary,
            "requires_dist": data["info"].get("requires_dist"),
            "wheel": {k: wheel[k] for k in ["filename", "size", "url"]} if wheel else None,
            "pypi_license_expression": data["info"].get("license_expression"),
        }
        if wheel:
            body = urllib.request.urlopen(wheel["url"], timeout=60).read()
            assert hashlib.sha256(body).hexdigest() == wheel["digests"]["sha256"]
            archive = zipfile.ZipFile(io.BytesIO(body))
            names = [
                n
                for n in archive.namelist()
                if not n.endswith("/") and ("license" in n.lower() or "copying" in n.lower())
            ]
            row["wheel"]["sha256"] = hashlib.sha256(body).hexdigest()
            row["license_files"] = []
            for name in names:
                license_body = archive.read(name)
                text = license_body.decode("utf8", errors="replace")
                # One short excerpt per primary file; term flags and hashes preserve the audit.
                terms = [
                    p
                    for p in [
                        "GCC runtime library",
                        "GPL-3.0",
                        "LGPL-2.1",
                        "GNU GENERAL",
                        "OpenBLAS",
                        "BSD",
                        "MIT License",
                        "Apache",
                    ]
                    if p in text
                ]
                row["license_files"].append(
                    {
                        "name": name,
                        "sha256": hashlib.sha256(license_body).hexdigest(),
                        "detected_terms": terms,
                        "snippet": " ".join(text.split()[:25]),
                    }
                )
            row["bundled_binaries"] = [n for n in archive.namelist() if n.lower().endswith(".dll")]
            row["selection"] = (
                "excluded from optional candidate workflows: Windows wheel "
                "bundles GPL-3.0-or-later WITH GCC-exception-3.1 runtime"
                if row["package"] == "scipy"
                else "permissive; not installed"
            )
        rows.append(row)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", "utf8", newline="\n")
    print(OUT.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
