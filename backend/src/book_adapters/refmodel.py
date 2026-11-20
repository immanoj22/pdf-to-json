"""Training data for the trained reference parser, kept on this machine only.

One folder (``<app data>/reference_training``, excluded from git, never uploaded) holds
``samples.jsonl``: each reference a person corrected in the review and that is now read without a
flag, with its printed text, its fields and the **job id** (``delete_job`` removes a client's
samples). ``retrain`` writes AnyStyle's training XML from the samples and trains a new model
(``model.mod`` in the same folder), which the parser then uses (``BOOK_ANYSTYLE_MODEL``).

    python -m book_adapters references retrain --dir app_data/reference_training
    python -m book_adapters references delete-job --dir app_data/reference_training JOBID
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from xml.sax.saxutils import escape

from .formats import anystyle
from .formats.vancouver import Reference

SAMPLES = "samples.jsonl"
MODEL = "model.mod"


def fields_of(ref: Reference) -> dict:
    return {
        "author": [{"given": i or "", "family": s} for i, s in ref.authors],
        "title": ref.title, "container-title": ref.source, "date": ref.year, "volume": ref.volume,
        "issue": ref.issue, "pages": "-".join(p for p in (ref.first_page, ref.last_page) if p) or ref.article_number,
        "url": ref.url, "pmid": ref.pmid, "publisher": ref.publisher, "location": ref.place,
        "edition": ref.edition,
    }  # fmt: skip


def read(folder) -> list[dict]:
    path = Path(folder) / SAMPLES
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def record(folder, job_id: str, ref: Reference) -> bool:
    """Add one sample (a text already held for this job is kept once). Returns True if added."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if any(s["text"] == ref.full and s["job"] == job_id for s in read(folder)):
        return False
    row = {"job": job_id, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "text": ref.full, "fields": fields_of(ref)}
    with (folder / SAMPLES).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True


def delete_job(folder, job_id: str) -> int:
    """Remove every sample of one job (a client's data on request). Returns how many."""
    rows = read(folder)
    keep = [r for r in rows if r["job"] != job_id]
    path = Path(folder) / SAMPLES
    if rows:
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep), "utf-8")
    return len(rows) - len(keep)


def sequence(sample: dict) -> str | None:
    """AnyStyle's labelled sequence of one sample: every character of the printed text in a
    segment, each field's segment running to the next field. None when title or year cannot be
    placed in the text."""
    text, f = sample["text"], sample["fields"]
    spans = []
    def put(label, value):
        if value and (at := text.find(str(value))) >= 0:
            spans.append((at, at + len(str(value)), label))
    put("title", f.get("title")); put("container-title", f.get("container-title")); put("date", f.get("date"))
    put("volume", f.get("volume")); put("issue", f.get("issue"))
    first = (f.get("pages") or "").split("-")[0]
    put("pages", first); put("url", (f.get("url") or "").replace("http://dx.doi.org/", ""))
    put("publisher", f.get("publisher")); put("location", f.get("location")); put("edition", f.get("edition"))
    labels = {s[2] for s in spans}
    if not {"title", "date"} <= labels:
        return None
    spans.sort()
    clean, end = [], 0
    for s in spans:
        if s[0] >= end:
            clean.append(s)
            end = s[1]
    cuts = [(0 if i == 0 else a, label) for i, (a, _, label) in enumerate(clean)]
    if clean[0][0] > 0:  # what comes before the first field is the authors
        cuts = [(0, "author"), *[(a, label) for a, _, label in clean]]
    out = []
    for i, (a, label) in enumerate(cuts):
        b = cuts[i + 1][0] if i + 1 < len(cuts) else len(text)
        out.append(f"    <{label}>{escape(text[a:b].strip())}</{label}>")
    return "  <sequence>\n" + "\n".join(out) + "\n  </sequence>"


def training_xml(folder) -> tuple[str, int]:
    seqs = [s for s in (sequence(r) for r in read(folder)) if s]
    return '<?xml version="1.0" encoding="UTF-8"?>\n<dataset>\n' + "\n".join(seqs) + "\n</dataset>\n", len(seqs)


def retrain(folder) -> dict:
    """Train a new model on the samples (needs the parser command, see ``BOOK_ANYSTYLE_CMD``)."""
    cmd = anystyle.command()
    if not cmd:
        raise RuntimeError("The trained parser is not set up (BOOK_ANYSTYLE_CMD).")
    folder = Path(folder)
    xml, count = training_xml(folder)
    if not count:
        raise RuntimeError("There are no usable training samples yet.")
    data = folder / "training.xml"
    data.write_text(xml, "utf-8")
    model = folder / MODEL
    done = subprocess.run([*cmd, "train", str(data), str(model)], capture_output=True, text=True, check=False)
    if done.returncode != 0 or not model.is_file():
        raise RuntimeError(f"Training failed: {done.stderr[-400:]}")
    return {"samples": count, "model": str(model)}
