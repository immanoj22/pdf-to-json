"""Re-encode an exported image when the client profile asks for another format."""

from __future__ import annotations

import io


def convert_image(data, target_format):
    """The image bytes in ``target_format`` ("jpg" or "png"), deterministically encoded."""
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        out = io.BytesIO()
        if target_format == "jpg":
            image.convert("RGB").save(out, format="JPEG", quality=92, optimize=False)
        else:
            image.save(out, format="PNG", optimize=False)
        return out.getvalue()
