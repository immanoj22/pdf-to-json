"""Before/after record of the double-claim correctness fix (not tuning).

"Before" counts come from the pre-fix cached alignments (double_claim_fix_before.json and the
saved alignment_summary_before_fix.json files); "after" is recounted from the current cached
alignment of each book.
"""

import json
from collections import defaultdict

from step5_run import BOOKS, CACHE, OUT


def double_claims(payload: dict) -> tuple[int, int]:
    claim = defaultdict(set)
    for i, (page, ordinal) in enumerate(
        zip(payload["xml_page"], payload["xml_ordinal"], strict=True)
    ):
        if page >= 0:
            claim[(page, ordinal)].add(i)
    for x, page, ordinal in payload["extra_links"]:
        claim[(page, ordinal)].add(x)
    duplicated = {
        key: owners
        for key, owners in claim.items()
        if len(owners) > 1 and not all(payload["xml_method"][i] == "split" for i in owners)
    }
    return len(duplicated), len(set().union(*duplicated.values())) if duplicated else 0


def current_payload(summary: dict) -> dict:
    """Newest post-fix cached alignment (it records refused links) for this book."""
    paths = sorted((CACHE / "alignment").glob("*.json"), key=lambda p: p.stat().st_mtime)
    for path in reversed(paths):
        payload = json.loads(json.loads(path.read_text("utf-8"))["payload"])
        if (
            "refused_links" in payload
            and len(payload["pages"]) == summary["pdf_pages"]
            and len(payload["xml_page"]) == summary["xml_tokens"]
        ):
            return payload
    raise FileNotFoundError("No post-fix alignment cached for this book")


def main():
    before = json.loads((OUT / "double_claim_fix_before.json").read_text("utf-8"))
    rows = {}
    for book in BOOKS:
        old = json.loads((OUT / book / "alignment_summary_before_fix.json").read_text("utf-8"))
        new = json.loads((OUT / book / "alignment_summary.json").read_text("utf-8"))
        pdf_tokens, xml_tokens = double_claims(current_payload(new))
        rows[book] = {
            "split": BOOKS[book]["split"],
            "double_claimed_pdf_tokens": {
                "before": before["double_claimed_pdf_tokens_before"][book]["pdf_tokens"],
                "after": pdf_tokens,
            },
            "xml_tokens_involved": {
                "before": before["double_claimed_pdf_tokens_before"][book]["xml_tokens_involved"],
                "after": xml_tokens,
            },
            "refused_links_after": new["refused_links"],
            **{
                key: {"before": old[key], "after": new[key]}
                for key in (
                    "pdf_aligned",
                    "xml_aligned",
                    "pdf_aligned_fraction",
                    "xml_aligned_fraction",
                )
            },
            "producer": {
                "before": old["alignment_producer_sha256"],
                "after": new["alignment_producer_sha256"],
            },
        }
    report = {"fix": before["fix"], "classification": "correctness fix, not tuning", "books": rows}
    (OUT / "double_claim_fix.json").write_text(json.dumps(report, indent=1) + "\n", "utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
