"""HeadingClassifier slot: a learned heading/not-heading decision over rule candidates.

The rules (``headings``, ``styled``) propose every visually distinct title and a verdict
(heading, display title or label). The optional classifier makes the final call from numeric,
gold-free features of each candidate:

- the rule evidence (score, verdict, protections);
- style relative to the body (size ratio and step, weight, capitals, colour contrast);
- layout (stream kind, first unit of its stream, lines, tokens, isolation);
- text cues (numbering kind, sentence terminal, question mark, digits);
- navigation (contents link), zone and section-opener page;
- whole-book consistency of its style group: how many candidates share it, the share that is
  numbered or contents-linked, how often it occurs per numbered section, and its prominence
  relative to the contents-linked headings.

It implements the ``accuracy.interfaces.HeadingClassifier`` protocol: features travel in
``HeadingInput.features`` (numbers only, never text) and the answer is a
``HeadingResult`` with a heading likelihood. The model is a LightGBM booster trained only on
book 1 derived gold (``experiments/step10_classifier.py``); its bytes are digested into the
provider identity and into the structure decision key. LightGBM is the optional
``classical-ml`` extra: without it, or without a model file, the rules decide.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from pathlib import Path

from book_core.accuracy.cache import accuracy_fingerprint, request_digest
from book_core.accuracy.models import (
    DeviceResolution,
    ExtensionMetadata,
    HeadingInput,
    HeadingResult,
    SourceRegion,
)
from book_core.model.common import Provenance

FEATURES = (
    "rule_score", "rule_heading", "rule_label", "rule_display", "protected",
    "size_ratio", "size_step", "bold", "upper", "color_contrast",
    "stream_main", "stream_box", "stream_figure", "first_in_stream", "units", "tokens",
    "numbered", "numbering_keyword", "numbering_letter", "contents_linked", "feature",
    "recurring_title", "repeated_pages", "attached", "zone_front", "zone_rear", "opener_page",
    "navigation_page", "terminal", "question", "digit_share", "gap_before", "gap_after",
    "group_size_log", "group_spine_share", "group_per_section", "group_sections",
    "prominence_over_linked", "page_rank",
)  # fmt: skip
STREAM_BOX = frozenset({"sidebar", "callout", "card", "note"})
MODELS = Path(__file__).resolve().parents[3] / "heading_models"
DEFAULT_MODEL = MODELS / "heading_classifier_book1.txt"


def load_default(path=DEFAULT_MODEL):
    """The saved classifier with the threshold recorded in its manifest, or None when the
    optional extra or the model file is missing (the rules then decide)."""
    import json

    path = Path(path)
    manifest = path.with_suffix(".json")
    if not path.exists() or not manifest.exists():
        return None
    try:
        import lightgbm  # noqa: F401
    except ImportError:
        return None
    threshold = json.loads(manifest.read_text("utf-8"))["threshold"]
    return LightGBMHeadingClassifier(path, threshold=threshold)


def group_statistics(items):
    """Whole-book statistics of each style group among the candidates (gold-free)."""
    size = Counter(i["style_group"] for i in items)
    spine = Counter(i["style_group"] for i in items if i["spine"])
    segment, per = 0, defaultdict(Counter)
    for item in items:
        if item["spine"] and item["prominence"][0] >= 1:
            segment += 1
        per[item["style_group"]][segment] += 1
    stats = {}
    for group, count in size.items():
        sections = per[group]
        stats[group] = {
            "size": count,
            "spine_share": spine[group] / count,
            "per_section": sum(sections.values()) / max(len(sections), 1),
            "sections": len(sections),
        }
    return stats


def item_features(item, body, zone_of, openers, navigation, stats, top_linked, page_rank):
    unit = item["first_unit"]
    group = stats[item["style_group"]]
    text = item["text"]
    digits = sum(c.isdigit() for c in text)
    letters = sum(c.isalpha() for c in text)
    zone = zone_of.get(item["page"], "body")
    marker = item["numbering"] or {}
    ratio = unit["size"] / max(body["size"], 0.1)
    return {
        "rule_score": item["score"],
        "rule_heading": float(item.get("rule_role") is None),
        "rule_label": float(item.get("rule_role") == "label"),
        "rule_display": float(item.get("rule_role") == "display_title"),
        "protected": float(bool(item.get("protected"))),
        "size_ratio": round(ratio, 4),
        "size_step": item["prominence"][0],
        "bold": float(item["prominence"][1]),
        "upper": float(item["prominence"][2]),
        "color_contrast": float(unit["color"] != body["color"]),
        "stream_main": float(item["stream"] == "main"),
        "stream_box": float(item["stream"] in STREAM_BOX),
        "stream_figure": float(item["stream"] in {"figure", "table"}),
        "first_in_stream": float(item["position"] == 0),
        "units": len(item["units"]),
        "tokens": item["tokens"],
        "numbered": float(item["numbered"]),
        "numbering_keyword": float(marker.get("kind") == "keyword"),
        "numbering_letter": float(marker.get("kind") == "letter"),
        "contents_linked": float(item["toc_level"] is not None),
        "feature": float(bool(item.get("feature"))),
        "recurring_title": float(bool(item.get("recurring_title"))),
        "repeated_pages": item["repeated"],
        "attached": float(item["attached"]),
        "zone_front": float(zone == "front"),
        "zone_rear": float(zone == "rear"),
        "opener_page": float(item["page"] in openers),
        "navigation_page": float(item["page"] in navigation),
        "terminal": float(unit["ending"] == "terminal"),
        "question": float(text.rstrip().endswith(("?", "？", "؟"))),
        "digit_share": round(digits / max(digits + letters, 1), 4),
        "gap_before": unit.get("gap_before") if unit.get("gap_before") is not None else -1.0,
        "gap_after": unit.get("gap_after") if unit.get("gap_after") is not None else -1.0,
        "group_size_log": round(math.log1p(group["size"]), 4),
        "group_spine_share": round(group["spine_share"], 4),
        "group_per_section": round(group["per_section"], 4),
        "group_sections": group["sections"],
        "prominence_over_linked": (item["prominence"][0] - top_linked[0])
        if top_linked is not None
        else 0,
        "page_rank": page_rank,
    }


class LightGBMHeadingClassifier:
    """HeadingClassifier provider over a saved LightGBM booster (CPU)."""

    name = "lightgbm-heading-classifier"

    def __init__(self, model_path, threshold=0.5, producer_sha256=None):
        import lightgbm

        self.path = Path(model_path)
        data = self.path.read_bytes().replace(b"\r\n", b"\n")
        self.booster = lightgbm.Booster(model_str=data.decode("utf-8"))
        if list(self.booster.feature_name()) != list(FEATURES):
            raise ValueError("Heading classifier features differ from this producer")
        self.threshold = threshold
        self._metadata = ExtensionMetadata(
            name=self.name,
            version="1",
            configuration={"threshold": threshold, "features": list(FEATURES)},
            producer_source_sha256=producer_sha256 or hashlib.sha256(b"structure").hexdigest(),
            model_sha256=hashlib.sha256(data).hexdigest(),
            dependency_versions={"lightgbm": lightgbm.__version__},
            device=DeviceResolution(requested="cpu", resolved="cpu"),
        )

    @property
    def metadata(self):
        return self._metadata

    def identity(self):
        return {"name": self.name, "model_sha256": self._metadata.model_sha256,
                "threshold": self.threshold}  # fmt: skip

    def likelihoods(self, rows):
        import numpy as np

        matrix = np.array([[float(row[name]) for name in FEATURES] for row in rows])
        return [float(p) for p in self.booster.predict(matrix)] if len(rows) else []

    def classify(self, request: HeadingInput) -> HeadingResult:
        row = {name: request.features[name] for name in FEATURES}
        likelihood = self.likelihoods([row])[0]
        return HeadingResult(
            source_sha256=request.source_sha256,
            request_sha256=request_digest(request),
            cache_key=accuracy_fingerprint(request, self),
            metadata=self.metadata,
            status="evidence",
            reason="lightgbm_heading_likelihood",
            confidence=round(abs(likelihood - 0.5) * 2, 6),
            label="heading" if likelihood >= self.threshold else "not_heading",
            heading_likelihood=round(likelihood, 6),
            provenance=Provenance(
                source_sha256=request.source_sha256, engine=self.name, engine_version="1",
                method="derived", resolved_device="cpu", execution_device="cpu",
            ),
        )  # fmt: skip


def heading_request(source_sha256, item, features):
    return HeadingInput(
        source_sha256=source_sha256,
        regions=[SourceRegion(id=item["id"], page=item["page"])],
        features=features,
        candidate_region_id=item["id"],
    )


def train(rows, labels, seed=0):
    """A LightGBM booster over FEATURES (deterministic, CPU)."""
    import lightgbm
    import numpy as np

    data = lightgbm.Dataset(
        np.array([[float(row[name]) for name in FEATURES] for row in rows]),
        label=np.asarray(labels),
        feature_name=list(FEATURES), free_raw_data=False,
    )  # fmt: skip
    params = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 15,
              "min_data_in_leaf": 10, "feature_fraction": 0.9, "bagging_fraction": 0.9,
              "bagging_freq": 1, "seed": seed, "deterministic": True, "force_row_wise": True,
              "num_threads": 1, "verbose": -1}  # fmt: skip
    return lightgbm.train(params, data, num_boost_round=200)
