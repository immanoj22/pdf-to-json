"""Region identities are unique on a page and deterministic, even without evidence.

Reproduces the Step 18 hold-out failure cause: table candidates whose lines all belong to
other owners (labels inside scatter plots) and that carry no objects had one identity, the
hash of empty evidence, so two of them on a page collided in layout validation.
"""

import json
import pickle
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from book_core.book_run import StageFailure, failure_record, stage
from book_core.extraction.fingerprints import stable_id
from book_core.layout.models import PageLayout, Scope, VisualBlock, VisualLine
from book_core.layout.pipeline import build_regions
from book_core.layout.regions import RegionIds
from book_core.model.common import BBox, Provenance


def line(name, x, y, size=10):
    return VisualLine(
        id=name,
        span_ids=[name],
        source_line_ids=[name],
        bbox=BBox(x0=x, y0=y, x1=x + 120, y1=y + size),
        baseline_start=(x, y + size),
        baseline_end=(x + 120, y + size),
        direction=(1, 0),
        rotation=0,
        writing_mode="horizontal",
        font_size=size,
        visible=True,
        inside_content=True,
    )


def block(name, kind, box, objects=()):
    return VisualBlock(
        id=name,
        kind=kind,
        bbox=BBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3]),
        object_ids=list(objects),
        confidence=0.7,
        reasons=["test"],
    )


def page_regions(page_id):
    """Four empty-evidence table candidates (two of them identical), two plots, body text."""
    plots = [
        block("plot-a", "figure", (40, 40, 280, 300)),
        block("plot-b", "figure", (300, 40, 560, 300)),
    ]
    tables = [
        block("grid-a", "table", (60, 60, 260, 280)),
        block("grid-b", "table", (320, 60, 540, 280)),
        block("grid-c", "table", (60, 60, 260, 280)),
        block("grid-d", "table", (60, 320, 260, 340)),
    ]
    body = line("body", 40, 400)
    labels = [line(f"tick-{n}", 70, 70 + 20 * n, size=6) for n in range(3)]
    lines = [body, *labels]
    scope = Scope(id=page_id, kind="page", bbox=BBox(x0=0, y0=0, x1=600, y1=800))
    owner = {item.id: ("figure", "plot-a") for item in labels}
    owner[body.id] = ("scope", None)
    blocks = [*plots, *tables]
    store = SimpleNamespace(
        spans={
            item.id: SimpleNamespace(
                raw_text=item.id, font="test", size=item.font_size, color=0, flags=0
            )
            for item in lines
        }
    )
    return build_regions(
        lines,
        blocks,
        owner,
        [scope],
        {None: scope.id},
        {b.id: scope.id for b in blocks},
        [],
        {},
        store,
        scope.bbox,
        scope,
    )


def test_empty_evidence_candidates_are_unique_and_deterministic():
    regions = page_regions("page-scope-1")
    tables = [r for r in regions if (r.proposed_type or r.type) == "table_candidate"]
    assert len(tables) == 4
    assert all(not r.line_ids and not r.object_ids for r in tables)
    ids = [r.id for r in regions]
    assert len(ids) == len(set(ids))
    # The former identity: one hash for every empty-evidence region, on every page.
    assert stable_id("region", "|") not in ids
    assert ids == [r.id for r in page_regions("page-scope-1")]
    # The same empty candidate on another page (another page scope) has another identity.
    other = page_regions("page-scope-2")
    assert not {r.id for r in tables} & {r.id for r in other if not r.line_ids}


def test_regions_with_unique_evidence_keep_their_identity():
    regions = page_regions("page-scope-1")
    plot = next(r for r in regions if r.type == "figure" and r.line_ids)
    body = next(r for r in regions if r.line_ids == ["body"])
    for region in (plot, body):
        key = [*sorted(region.line_ids), "|", *sorted(region.object_ids)]
        assert region.id == stable_id("region", *key)


def test_repeated_evidence_gets_a_geometry_identity_and_ordinal():
    ids = RegionIds("page")
    box = BBox(x0=1, y0=2, x1=3, y1=4)
    first = ids.assign("table_candidate", "scope", box, ["a"], ["o"])
    second = ids.assign("callout", "scope", box, ["a"], ["o"])
    third = ids.assign("callout", "scope", box, ["a"], ["o"])
    assert first == stable_id("region", "a", "|", "o")
    assert len({first, second, third}) == 3


def provenance():
    return Provenance(
        source_sha256="0" * 64,
        engine="test",
        engine_version="1",
        method="derived",
        resolved_device="cpu",
        execution_device="cpu",
    )


def test_duplicate_regions_fail_with_the_colliding_items():
    region = page_regions("page-scope-1")[0].model_dump()
    with pytest.raises(ValidationError) as caught:
        PageLayout.model_validate(
            {
                "source_sha256": "0" * 64,
                "page": 348,
                "layout_version": "test",
                "content_bbox": {"x0": 0, "y0": 0, "x1": 600, "y1": 800},
                "lines": [],
                "scopes": [{"id": "page-scope-1", "kind": "page",
                            "bbox": {"x0": 0, "y0": 0, "x1": 600, "y1": 800}}],
                "regions": [region, region],
                "provenance": provenance().model_dump(),
            }
        )  # fmt: skip
    message = str(caught.value)
    assert "Duplicate region on page 348" in message
    assert region["id"] in message and '"bbox"' in message and '"scope_id"' in message


def test_a_failed_page_stage_leaves_a_clear_failure_record(tmp_path):
    with pytest.raises(StageFailure) as caught, failure_record(tmp_path):
        with stage({}, "layout", 348):
            BBox.model_validate({"x0": 2, "y0": 0, "x1": 1, "y1": 1})
    failure = caught.value
    assert (failure.stage, failure.page, failure.error_type) == (
        "layout",
        348,
        "ValidationError",
    )
    assert pickle.loads(pickle.dumps(failure)).details == failure.details
    (path,) = (tmp_path / "failures").iterdir()
    record = json.loads(path.read_text("utf-8"))
    assert record["stage"] == "layout" and record["page"] == 348
    assert record["details"] and record["traceback"]


def test_a_failure_outside_any_stage_is_still_recorded(tmp_path):
    with pytest.raises(OSError), failure_record(tmp_path):
        raise OSError("disk")
    (path,) = (tmp_path / "failures").iterdir()
    record = json.loads(path.read_text("utf-8"))
    assert record["stage"] is None and record["error_type"] == "OSError"


def test_a_terminated_run_leaves_a_clear_stop_record(tmp_path):
    import os
    import signal

    with pytest.raises(SystemExit), failure_record(tmp_path):
        os.kill(os.getpid(), signal.SIGTERM)
    (path,) = (tmp_path / "failures").iterdir()
    record = json.loads(path.read_text("utf-8"))
    assert record["error_type"] == "SystemExit" and "signal" in record["message"]
    assert signal.getsignal(signal.SIGTERM) is not None  # the previous handler is restored


def test_run_clocks_separate_machine_sleep_where_measurable():
    from book_core.book_run import clocks

    awake, booted = clocks()
    assert awake > 0 and (booted is None or booted >= awake - 1)
