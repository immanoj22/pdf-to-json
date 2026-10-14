"""Optional English alt-text drafts (SmolVLM-256M-Instruct, Apache-2.0). Off by default.

The generator needs the optional ``models`` extra and is used only when the figure settings
turn it on. A draft is English, carries source ``model_draft`` and status ``needs_review``,
and is never presented as verified. The model revision is an immutable commit.
"""

from __future__ import annotations

import re
from pathlib import Path

from book_core.device import DevicePolicy, resolve_device, run_with_device
from book_core.figures.models import AltText

DEFAULT_MODEL = "HuggingFaceTB/SmolVLM-256M-Instruct"
DEFAULT_REVISION = "7e3e67edbbed1bf9888184d9df282b700a323964"
PROMPT = "Describe this image in one or two sentences for a reader who cannot see it."
MAX_NEW_TOKENS = 80


class DraftGenerator:
    """Lazy official Transformers path; a failed GPU operation is retried on CPU."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        revision: str = DEFAULT_REVISION,
        cache_dir: Path | None = None,
        device: DevicePolicy = "auto",
        local_files_only: bool = False,
    ):
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("A model revision must be an immutable 40-character commit")
        self.model_id, self.revision = model, revision
        self.cache_dir, self.local_files_only = cache_dir, local_files_only
        self._resolution = resolve_device(device)
        self._processor = self._model = None

    def identity(self):
        return {
            "model": self.model_id,
            "revision": self.revision,
            "device": self._resolution.resolved,
            "fallback_reason": self._resolution.fallback_reason,
        }

    def _load(self):
        try:
            from transformers import AutoModelForImageTextToText, AutoProcessor
        except ImportError as error:
            raise RuntimeError("Alt-text drafts require the optional [models] extra") from error
        options = {"revision": self.revision, "local_files_only": self.local_files_only}
        if self.cache_dir is not None:
            options["cache_dir"] = str(self.cache_dir)
        self._processor = AutoProcessor.from_pretrained(self.model_id, **options)
        self._model = AutoModelForImageTextToText.from_pretrained(self.model_id, **options)
        loaded = getattr(self._model.config, "_commit_hash", None)
        if loaded is not None and loaded != self.revision:
            raise RuntimeError("Loaded model revision differs from the requested revision")

    def _generate(self, rgb, device):
        import torch
        from PIL import Image

        if self._model is None:
            self._load()
        self._model.to(device).eval()
        messages = [
            {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": PROMPT}]}
        ]
        prompt = self._processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs = self._processor(text=prompt, images=[Image.fromarray(rgb)], return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.inference_mode():
            output = self._model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
        generated = output[:, inputs["input_ids"].shape[1] :]
        return self._processor.batch_decode(generated, skip_special_tokens=True)[0].strip()

    def describe(self, rgb) -> AltText:
        text, self._resolution = run_with_device(
            lambda device: self._generate(rgb, device), self._resolution
        )
        if not text:
            return AltText()
        return AltText(
            text=text,
            status="needs_review",
            source="model_draft",
            language="en",
            model=f"{self.model_id}@{self.revision}",
        )
