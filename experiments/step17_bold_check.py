"""Step 17 Part 2: bold tokens of ours that the reference does not mark (body text), checked
against the printed page.

The assembly runs with the span recorder (``step17_styling_eval``); body-text tokens that we
mark bold and the reference does not are drawn with a fixed seed (``1703``), grouped by the
unit holding them (one token per unit), and rendered with the token's span outlined, for a
hand verdict in ``styling/bold_check.json`` (``bold`` printed bold / ``not_bold``).

Usage: python step17_bold_check.py --book medical_anatomy [--n 24]
"""

import argparse
import json
import random
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import regex
from book_core.cache_store import read_json
from book_core.ledger.tokenization import TOKEN_PATTERN
from book_core.model.spans import ExtractedPage

import step17_styling_eval as ev
from reference_paths import reference_path
from step13_books import BOOKS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--n", type=int, default=24)
    args = parser.parse_args()
    marks, _, archive, pages = ev.record_spans(args.book)
    doc = ev.reference(args.book)
    aligned = ev.alignment(doc.sha256)
    ref, heading = ev.reference_kinds(doc)
    ref_of = {}
    for index in range(len(doc.tokens)):
        p = aligned["xml_page"][index]
        if p >= 0:
            ref_of[(aligned["pages"][p], aligned["xml_ordinal"][index])] = (
                ref[index],
                heading[index],
            )
    candidates = []
    for number in range(1, pages + 1):
        page = ExtractedPage.model_validate(read_json(archive / f"page_{number:06d}.json.gz")[
            "source"])  # fmt: skip
        ordinal = 0
        for line in page.store.lines:
            raw = page.store.raw_line_text(line)
            if not raw.strip() or not page.geometry.content_bbox.contains_center(
                line.bbox
            ):
                continue
            owners = [
                sid for sid in line.span_ids for _ in page.store.spans[sid].raw_text
            ]
            positions = [
                k
                for sid in line.span_ids
                for k in range(len(page.store.spans[sid].raw_text))
            ]
            norm_owner, norm_pos = [], []
            for cluster in regex.finditer(r"\X", raw):
                fragment = unicodedata.normalize("NFKC", cluster.group())
                norm_owner += [owners[cluster.start()]] * len(fragment)
                norm_pos += [positions[cluster.start()]] * len(fragment)
            normalized = "".join(unicodedata.normalize("NFKC", c.group())
                                 for c in regex.finditer(r"\X", raw))  # fmt: skip
            for match in TOKEN_PATTERN.finditer(normalized):
                key = (number, ordinal)
                ordinal += 1
                sid = norm_owner[match.start()]
                ours = Counter(
                    k
                    for j in range(match.start(), match.end())
                    for k in marks.get(norm_owner[j], {}).get(norm_pos[j], ())
                )
                bold = ours["bold"] * 2 > match.end() - match.start()
                reference = ref_of.get(key)
                if (
                    bold
                    and reference
                    and "bold" not in reference[0]
                    and not reference[1]
                ):
                    candidates.append((number, sid, match.group(),
                                       page.store.spans[sid].bbox.model_dump()))  # fmt: skip
    seen, picked = set(), []
    for item in random.Random(1703).sample(candidates, len(candidates)):
        if item[1] in seen:
            continue
        seen.add(item[1])
        picked.append(item)
        if len(picked) == args.n:
            break
    import pymupdf
    from PIL import Image, ImageDraw

    tiles = []
    with pymupdf.open(reference_path(BOOKS[args.book][0])) as document:
        for n, (number, _, text, box) in enumerate(picked, start=1):
            page = document[number - 1]
            clip = pymupdf.Rect(
                box["x0"] - 80, box["y0"] - 12, box["x1"] + 80, box["y1"] + 12
            )
            clip &= page.rect
            pixmap = page.get_pixmap(dpi=144, clip=clip)
            image = Image.frombytes(
                "RGB", (pixmap.width, pixmap.height), pixmap.samples
            )
            s = 2
            ImageDraw.Draw(image).rectangle(
                [(box["x0"] - clip.x0) * s - 2, (box["y0"] - clip.y0) * s - 2,
                 (box["x1"] - clip.x0) * s + 2, (box["y1"] - clip.y0) * s + 2],
                outline=(220, 0, 0), width=2)  # fmt: skip
            image.thumbnail((1000, 160))
            canvas = Image.new("RGB", (1000, image.height + 20), "white")
            ImageDraw.Draw(canvas).text(
                (4, 2), f"#{n} p{number} token {text!r}", fill=(0, 0, 160)
            )
            canvas.paste(image, (0, 20))
            tiles.append(canvas)
    for k in range(0, len(tiles), 8):
        group = tiles[k : k + 8]
        out = Image.new("RGB", (1000, sum(t.height for t in group)), "white")
        y = 0
        for t in group:
            out.paste(t, (0, y))
            y += t.height
        out.save(ev.OUT / f"bold_check_{args.book}_{k // 8 + 1}.png")
    (ev.OUT / f"bold_check_{args.book}_sample.json").write_text(json.dumps(
        {"candidates": len(candidates), "picked": [list(p[:3]) for p in picked]},
        ensure_ascii=False, indent=1) + "\n", "utf-8", newline="\n")  # fmt: skip
    print(
        len(candidates),
        "bold tokens not marked by the reference (body)",
        len(picked),
        "drawn",
    )


if __name__ == "__main__":
    main()
