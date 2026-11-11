"""Step 21 item 7: question-entry census of a book.json, and a seeded hand-check sample.

Counts question sets and entries, entries whose options are complete and in letter order
(a, b, c, d ...), entries with an answer part whose key is one of the option letters, and
answer lines left inside an option (an option text holding a printed answer line). The
sample prints N seeded entries (stem, options in order, key, start of the explanation) for
the hand check.

Usage: python step21_questions.py BOOK_JSON [--sample 40] [--seed step21:questions] [--out F]
"""

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src")]

from book_core.lists.lines import answer_key


def walk(units):
    for unit in units:
        yield unit
        for key in ("items", "children"):
            yield from walk(unit.get(key) or [])


def text(unit):
    return ((unit.get("content") or {}).get("text") or "").replace("\n", " ").strip()


def entry_view(entry):
    question = next(p for p in entry["children"] if p["type"] == "question")
    answer = next((p for p in entry["children"] if p["type"] == "answer"), None)
    first = question["children"][0]
    stem = first["items"][-1] if first.get("items") else first  # a numbered list item or a unit
    options = next((c for c in question["children"][1:] if c["type"] == "list"), None)
    items = options["items"] if options else []
    letters = [((i.get("marker") or {}).get("text") or "").strip(" .)(").casefold() for i in items]
    values = [(i.get("marker") or {}).get("value") for i in items]
    explanation = [text(u) for u in (answer["children"][1:] if answer else []) if text(u)]
    return {
        "page": entry["pages"][0],
        "number": entry.get("number"),
        "stem": text(stem)[:160],
        "options": [f"{letter}. {text(i)[:80]}" for letter, i in zip(letters, items, strict=True)],
        "in_order": values == sorted(values) and values == list(range(1, len(values) + 1)),
        "key": answer["key"] if answer else None,
        "key_in_options": bool(answer) and answer["key"] in letters,
        "answer_line": text(answer["children"][0])[:120] if answer else None,
        "explanation": " / ".join(explanation)[:200],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_json")
    parser.add_argument("--sample", type=int, default=40)
    parser.add_argument("--seed", default="step21:questions")
    parser.add_argument("--out")
    args = parser.parse_args()
    book = json.loads(Path(args.book_json).read_text("utf-8"))
    units = list(walk(book["content"]))
    sets = [u for u in units if u["type"] == "question_set"]
    entries = [entry_view(u) for u in units if u["type"] == "question_entry"]
    glued = 0
    for unit in units:  # option texts holding a printed answer line, anywhere in the book
        if unit["type"] == "list_item":
            lines = ((unit.get("content") or {}).get("text") or "").split("\n")
            glued += any(answer_key(line) for line in lines[1:])
    summary = {
        "pages": len(book["pages"]),
        "question_sets": len(sets),
        "entries": len(entries),
        "with_options": sum(bool(e["options"]) for e in entries),
        "options_complete_in_order": sum(bool(e["options"]) and e["in_order"] for e in entries),
        "with_answer": sum(e["key"] is not None for e in entries),
        "key_in_options": sum(e["key_in_options"] for e in entries),
        "items_with_answer_line_inside": glued,
        "review_items": len(book["review"]["items"]),
    }
    rows = random.Random(args.seed).sample(entries, min(args.sample, len(entries)))
    rows.sort(key=lambda e: (e["page"], e["number"] or 0))
    result = {"summary": summary, "sample": rows}
    text_out = json.dumps(result, indent=1, ensure_ascii=False)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text_out + "\n", "utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
