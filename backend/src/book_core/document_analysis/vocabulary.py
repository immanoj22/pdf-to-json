"""Whole-book lexical frequencies and conservative native-adjacency join evidence.

These observations neither join words nor alter source text. Native consecutive lines
can belong to different columns or regions. An independent spelling match elsewhere
supports a spelling, not paragraph continuity or semantic reading order.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from book_core.ledger.tokenization import TOKEN_PATTERN, line_tokens
from book_core.model.spans import ExtractedPage

_LINE_BREAK_HYPHENS = frozenset("-\u00ad\u2010\u2011")


def build_vocabulary(
    pages: list[ExtractedPage], native_blocks: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Count NFKC benchmark tokens and record line-boundary spelling candidates.

    Tokens use the unchanged ledger rule (Unicode letters, marks and numbers).
    Casefolded and case-sensitive frequencies support joined spelling evidence.
    CJK word segmentation is deferred; no physical direction or order is inferred.
    Explicit TrimBox exclusions are respected without making discard decisions.
    """
    if len({page.source_sha256 for page in pages}) > 1:
        raise ValueError("Document evidence must describe one source")
    if len({page.geometry.page for page in pages}) != len(pages):
        raise ValueError("Duplicate extracted page in document evidence")
    block_membership: dict[tuple[int, str], str] = {}
    for ordinal, block in enumerate(native_blocks or []):
        block_id = str(block.get("block", ordinal))
        for line_id in block["line_ids"]:
            key = (block["page"], line_id)
            if key in block_membership:
                raise ValueError("Native line belongs to multiple block records")
            block_membership[key] = block_id
    exact: Counter[str] = Counter()
    folded: Counter[str] = Counter()
    native_lines = []
    for page in pages:
        previous = None
        for line in page.store.lines:
            raw = page.store.raw_line_text(line)
            # A discarded line breaks native adjacency; do not join across it.
            if not raw.strip() or not page.geometry.content_bbox.contains_center(line.bbox):
                previous = None
                continue
            tokens = list(line_tokens(page.store, line))
            exact.update(token.value for token in tokens)
            folded.update(token.value.casefold() for token in tokens)
            current = (page, line, raw, tokens)
            if previous is not None:
                previous_block = block_membership.get((page.geometry.page, previous[1].id))
                current_block = block_membership.get((page.geometry.page, line.id))
                if native_blocks is None or (
                    previous_block is not None and previous_block == current_block
                ):
                    native_lines.append((previous, current, current_block))
            previous = current

    joins = []
    for previous, current, block_id in native_lines:
        page, left_line, left_raw, left_tokens = previous
        _, right_line, right_raw, right_tokens = current
        trailing = left_raw.rstrip()
        if not left_tokens or not right_tokens or trailing[-1:] not in _LINE_BREAK_HYPHENS:
            continue
        # A separated dash or initial punctuation does not establish lexical adjacency.
        left = left_tokens[-1]
        right = right_tokens[0]
        left_match = list(TOKEN_PATTERN.finditer(trailing[:-1]))
        right_match = TOKEN_PATTERN.match(right_raw.lstrip())
        if not left_match or left_match[-1].end() != len(trailing) - 1 or right_match is None:
            continue
        if not any(character.isalpha() for character in left.value) or not any(
            character.isalpha() for character in right.value
        ):
            continue
        joined = left.value + right.value
        elsewhere = folded[joined.casefold()]
        joins.append(
            {
                "page": page.geometry.page,
                "left_line_id": left_line.id,
                "right_line_id": right_line.id,
                "left_token_id": left.id,
                "right_token_id": right.id,
                "span_ids": list(dict.fromkeys((*left.span_ids, *right.span_ids))),
                "left_fragment": left.value,
                "right_fragment": right.value,
                "joined": joined,
                "hyphen": trailing[-1],
                "elsewhere_occurrences": elsewhere,
                "elsewhere_exact_occurrences": exact[joined],
                "joined_occurs_elsewhere": bool(elsewhere),
                "confidence": (0.7 if block_id is not None else 0.5) if elsewhere else 0.1,
                "confidence_interpretation": "heuristic_spelling_support_not_probability",
                "adjacency": "same_native_block" if block_id is not None else "native_lines",
                "native_block_id": block_id,
                "method": "native_adjacency_and_independent_spelling",
                "continuity_decided": False,
            }
        )
    return {
        "method": "book-vocabulary-native-evidence-v1",
        "normalization": "NFKC",
        "token_rule": r"[\p{L}\p{M}\p{N}]+",
        "total_tokens": sum(exact.values()),
        "unique_tokens": len(exact),
        "frequencies": dict(sorted(exact.items())),
        "casefold_frequencies": dict(sorted(folded.items())),
        "hyphen_joins": joins,
        "native_blocks_supplied": native_blocks is not None,
        "limitations": [
            "Native block/line adjacency is extraction evidence, not semantic reading order.",
            "No joins are proposed across page boundaries or explicit TrimBox exclusions.",
            "A spelling occurrence does not prove paragraph continuity.",
            "CJK without spaces retains the current benchmark token rule.",
        ],
    }
