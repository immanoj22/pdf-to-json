"""Batched formula reading (experiment, not wired into the pipeline): the same readings as one
image at a time, in fewer model calls. Measured on CPU it is no faster (392 vs 373 equations
an hour, batch 1 vs 8, identical readings); a GPU may differ, so it stays here for that test.

``recognition.py`` reads one image per call and its source digest is part of every cached
reading's key, so the batched path lives here and leaves that file (and every cached reading)
as it is. A batch is decoded together with greedy decoding. The processor resizes every image to
one shape, so a batch needs no padded input. A batch whose decoded length reaches the token
limit is read image by image, so truncation decisions are the single-image ones.

``read_many`` returns the records ``RecognitionCache.read`` returns, in order, and writes the
same cache files: a reading made in a batch and one made alone are interchangeable.
"""

import hashlib
import io

from book_core.cache_store import read_json, write_json
from book_core.device import run_with_device


def _infer_many(recognizer, pngs, device):
    import torch
    from PIL import Image

    if recognizer._model is None:
        recognizer._load()
    recognizer._model.to(device)
    images = []
    for png in pngs:
        with Image.open(io.BytesIO(png)) as image_file:
            images.append(image_file.convert("RGB"))
    inputs = recognizer._processor(images=images, return_tensors="pt").to(device)
    with torch.inference_mode():
        generated = recognizer._model.generate(
            **inputs, max_new_tokens=recognizer.max_new_tokens, do_sample=False
        )
    if int(generated.shape[-1]) >= recognizer.max_new_tokens:
        return [recognizer._infer(png, device) for png in pngs]
    texts = recognizer._processor.post_process(generated, skip_special_tokens=True)
    return [(text, False) for text in texts]


def recognize_many(recognizer, pngs):
    """[(LaTeX, truncated)] for a list of PNG images, in order (PP-FormulaNet)."""
    with recognizer._lock:

        def operation(device):
            if device == "cpu" and recognizer._last == "cuda":
                recognizer._model = recognizer._processor = None
            recognizer._last = device
            return _infer_many(recognizer, pngs, device)

        result, resolution = run_with_device(operation, recognizer.device)
        recognizer._device = resolution
        return result


def _peek(cache, digest):
    """The cached record of an image digest (``RecognitionCache.read``'s file), or None."""
    path = cache.root / cache.key()[:20] / f"{digest[:40]}.json"
    if path.exists():
        record = read_json(path)
        if record.get("image_sha256") == digest and record.get("key") == cache.key():
            return {**record, "cached": True}
    return None


def _store(cache, digest, latex, truncated):
    record = {
        "key": cache.key(),
        "image_sha256": digest,
        "latex": latex,
        "truncated": truncated,
        "identity": cache.recognizer.identity,
    }
    write_json(cache.root / cache.key()[:20] / f"{digest[:40]}.json", record)
    return {**record, "cached": False}


def read_many(cache, pngs, batch=1):
    """Readings of ``pngs`` in order. Uncached images are recognized ``batch`` at a time (one at
    a time when ``batch`` is 1 or the recognizer has no batched path); duplicate images are read
    once."""
    digests = [hashlib.sha256(png).hexdigest() for png in pngs]
    found = {}
    for digest in dict.fromkeys(digests):
        record = _peek(cache, digest)
        if record is not None:
            found[digest] = record
    missing = {}
    for digest, png in zip(digests, pngs, strict=True):
        if digest not in found:
            missing.setdefault(digest, png)
    pending = list(missing.items())
    size = max(1, int(batch))
    for start in range(0, len(pending), size):
        chunk = pending[start : start + size]
        if size > 1 and len(chunk) > 1 and hasattr(cache.recognizer, "_infer"):
            results = recognize_many(cache.recognizer, [png for _, png in chunk])
        else:
            results = [cache.recognizer.recognize(png) for _, png in chunk]
        for (digest, _), (latex, truncated) in zip(chunk, results, strict=True):
            found[digest] = _store(cache, digest, latex, truncated)
    return [found[digest] for digest in digests]
