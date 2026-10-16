"""Formula image recognition behind an interface, with a per-image cache.

``FormulaRecognizer`` reads LaTeX from a rendered equation image. The installed
implementation is PP-FormulaNet-L (Apache-2.0, optional ``models`` extra) through the
official Transformers path; heavy imports happen only when it runs. A failed GPU operation
is retried in full on CPU. Results are cached per image: the key holds the image digest,
the model repository and immutable revision, the generation settings, the dependency
versions, the resolved device and this module's code, so a changed render, model or code
never reads an old reading back.
"""

import hashlib
import importlib.metadata as metadata
import io
import json
import re
from pathlib import Path
from threading import RLock

from book_core.cache_store import read_json, write_json
from book_core.caching import code_digest
from book_core.device import resolve_device, run_with_device

CACHE_VERSION = "formula-reading-1"
DEPENDENCIES = ("torch", "transformers", "pillow", "tokenizers", "safetensors")


def _versions():
    found = {}
    for package in DEPENDENCIES:
        try:
            found[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            found[package] = "not-installed"
    return found


VERSIONS = _versions()  # read once per process (package metadata lookups are slow)


class PPFormulaNet:
    """PP-FormulaNet-L (PaddlePaddle, Apache-2.0 code and weights)."""

    name = "pp_formulanet_l"
    repo_id = "PaddlePaddle/PP-FormulaNet-L_safetensors"
    default_revision = "69869f2891cc61347d230ef234bcc8b8d297c43a"
    max_new_tokens = 512

    def __init__(self, *, device="auto", revision=None, cache_dir=None, local_files_only=False):
        self.revision = revision or self.default_revision
        if not re.fullmatch(r"[0-9a-f]{40}", self.revision):
            raise ValueError("A model revision must be an immutable 40-character commit")
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("Unknown device policy")
        self.cache_dir = cache_dir
        self.local_files_only = local_files_only
        self._requested = device
        self._device = None
        self._model = self._processor = None
        self._last = None
        self._lock = RLock()

    @property
    def device(self):
        if self._device is None:
            self._device = resolve_device(self._requested)
        return self._device

    @property
    def identity(self):
        return {
            "recognizer": self.name,
            "repo_id": self.repo_id,
            "revision": self.revision,
            "max_new_tokens": self.max_new_tokens,
            "decoding": "greedy",
            "dependencies": VERSIONS,
            "device": self.device.resolved,
        }

    def _load(self):
        try:
            import torch
            from transformers import AutoModelForImageTextToText, AutoProcessor
        except ImportError as error:
            raise RuntimeError(
                "Formula recognition requires the optional [models] extra"
            ) from error
        options = {"revision": self.revision, "local_files_only": self.local_files_only}
        if self.cache_dir is not None:
            options["cache_dir"] = str(self.cache_dir)
        processor = AutoProcessor.from_pretrained(self.repo_id, **options)
        model = AutoModelForImageTextToText.from_pretrained(
            self.repo_id, dtype=torch.float32, **options
        )
        resolved = getattr(model.config, "_commit_hash", None)
        if resolved is not None and resolved != self.revision:
            raise RuntimeError("Loaded model revision differs from the requested revision")
        model.generation_config.max_length = None
        self._processor, self._model = processor, model.eval()

    def _infer(self, png, device):
        import torch
        from PIL import Image

        if self._model is None:
            self._load()
        self._model.to(device)
        with Image.open(io.BytesIO(png)) as image_file:
            image = image_file.convert("RGB")
        inputs = self._processor(images=image, return_tensors="pt").to(device)
        with torch.inference_mode():
            generated = self._model.generate(
                **inputs, max_new_tokens=self.max_new_tokens, do_sample=False
            )
        text = self._processor.post_process(generated, skip_special_tokens=True)[0]
        truncated = int(generated.shape[-1]) >= self.max_new_tokens
        return text, truncated

    def recognize(self, png):
        """(LaTeX, truncated) for one PNG image."""
        with self._lock:

            def operation(device):
                if device == "cpu" and self._last == "cuda":
                    self._model = self._processor = None
                self._last = device
                return self._infer(png, device)

            result, resolution = run_with_device(operation, self.device)
            self._device = resolution
            return result


class RecognitionCache:
    """Cached readings of one recognizer, keyed by image digest."""

    def __init__(self, recognizer, cache_dir):
        self.recognizer = recognizer
        self.root = Path(cache_dir) / "formula_readings"
        self.producer = code_digest("formula")

    def key(self):
        identity = {
            **self.recognizer.identity,
            "cache_version": CACHE_VERSION,
            "producer_sha256": self.producer,
        }
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def read(self, png):
        """{"latex", "truncated", "image_sha256", "cached"} for one image."""
        digest = hashlib.sha256(png).hexdigest()
        path = self.root / self.key() / digest[:2] / f"{digest}.json"
        if path.exists():
            record = read_json(path)
            if record.get("image_sha256") == digest and record.get("key") == self.key():
                return {**record, "cached": True}
        latex, truncated = self.recognizer.recognize(png)
        record = {
            "key": self.key(),
            "image_sha256": digest,
            "latex": latex,
            "truncated": truncated,
            "identity": self.recognizer.identity,
        }
        write_json(path, record)
        return {**record, "cached": False}
