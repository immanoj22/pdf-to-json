"""Image file names from page labels and reading positions; file-safe and unique per book."""

import unicodedata

import regex

UNSAFE = regex.compile(r"[^\p{L}\p{N}]+")
# Device names Windows reserves regardless of extension.
RESERVED = {"con", "prn", "aux", "nul", *{f"com{i}" for i in range(10)},
            *{f"lpt{i}" for i in range(10)}}  # fmt: skip
NO_LABEL = "no page label: named by the physical PDF page; review"
INFERRED = "page label inferred from the folio sequence, not printed"
COLLISION = "name already used in this book; a numeric suffix keeps it unique; review"


def safe_label(label):
    """Keep letters and digits of any script (``HT12`` stays ``HT12``); join others with -."""
    text = UNSAFE.sub("-", unicodedata.normalize("NFKC", label)).strip("-")
    return text or None


def _stem(pattern, **fields):
    stem = pattern.format(**fields)
    stem = regex.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", stem).rstrip(" .")
    if stem.split(".")[0].casefold() in RESERVED:
        stem = f"{stem}_"
    return stem


def assign_names(entries, settings):
    """``entries``: [(key, physical page, label, label source, reading index)] in book order.

    Returns {key: (stem, label, inferred, review reasons)}. Collisions are compared
    case-insensitively (Windows and macOS file systems) and resolved in book order.
    """
    used, result = set(), {}
    for key, index, label, source, n in entries:
        reasons = []
        label = safe_label(label) if label else None
        if label is None or source == "none":
            stem = _stem(settings.unlabelled_pattern, index=index, n=n, label="")
            reasons.append(NO_LABEL)
            label, source = None, "none"
        else:
            stem = _stem(settings.name_pattern, label=label, n=n, index=index)
            if source == "inferred":
                reasons.append(INFERRED)
        base, suffix = stem, 2
        while stem.casefold() in used:
            stem = f"{base}_{suffix}"
            suffix += 1
        if stem != base:
            reasons.append(COLLISION)
        used.add(stem.casefold())
        result[key] = (stem, label, source == "inferred", reasons)
    return result
