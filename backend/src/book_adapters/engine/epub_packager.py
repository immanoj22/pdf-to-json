"""Pack ePub members into a .epub (a ZIP) whose bytes depend only on the files: ``mimetype``
first and stored uncompressed, then ``META-INF/container.xml``, then the rest sorted, with
fixed time stamps and permissions."""

from __future__ import annotations

import zipfile
from pathlib import Path


def write_epub(files: dict[str, bytes], path: Path) -> Path:
    path = Path(path)
    if path.exists():
        path.unlink()
    order = ["mimetype"]
    if "META-INF/container.xml" in files:
        order.append("META-INF/container.xml")
    order += sorted(k for k in files if k not in order)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in order:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, files[name])
    return path
