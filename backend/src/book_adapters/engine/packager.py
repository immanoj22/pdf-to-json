"""Write a delivery to disk: XML files and images (converted, scaled, named by the
profile). Output bytes depend only on the inputs, so runs are byte-identical."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image


def encode_image(source: Path, fmt: str, max_width: int | None, dpi: int, quality: int) -> bytes:
    with Image.open(source) as im:
        im.load()
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            background = Image.new("RGB", im.size, (255, 255, 255))
            background.paste(im, mask=im.split()[-1])
            im = background
        elif im.mode != "RGB":
            im = im.convert("RGB")
        if max_width and im.width > max_width:
            height = max(1, round(im.height * max_width / im.width))
            im = im.resize((max_width, height), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        if fmt == "jpg":
            im.save(
                out,
                "JPEG",
                quality=quality,
                optimize=False,
                progressive=False,
                dpi=(dpi, dpi),
                subsampling=0,
            )
        else:
            im.save(out, "PNG", optimize=False, dpi=(dpi, dpi))
        return out.getvalue()


def write_delivery(delivery, book, profile, out_dir: Path) -> Path:
    root = Path(out_dir) / delivery.root
    root.mkdir(parents=True, exist_ok=True)
    for rel, data in sorted(delivery.files.items()):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    images = root / profile.get("delivery.images_folder")
    big = profile.get("delivery.bigimages_folder")
    fmt = profile.get("images.format")
    for job in delivery.images:
        source = book.image_path(job.source)
        images.mkdir(parents=True, exist_ok=True)
        (images / job.name).write_bytes(
            encode_image(
                source,
                fmt,
                profile.get("images.max_width"),
                profile.get("images.dpi"),
                profile.get("images.quality"),
            )
        )
        if big and job.big:
            (root / big).mkdir(parents=True, exist_ok=True)
            (root / big / job.name).write_bytes(
                encode_image(
                    source,
                    fmt,
                    profile.get("images.big_max_width"),
                    profile.get("images.dpi"),
                    profile.get("images.quality"),
                )
            )
    return root


def write_zip(root: Path, zip_path: Path) -> Path:
    """Pack the delivery folder (as its top folder) into a ZIP whose bytes depend only on
    the files: sorted entries, fixed timestamps and permissions."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(
                f"{root.name}/{path.relative_to(root).as_posix()}", date_time=(1980, 1, 1, 0, 0, 0)
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    return zip_path
