"""The case-sensitive NFKC Unicode multiset benchmark and occurrence provenance."""

import unicodedata
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass

import regex

from book_core.extraction.fingerprints import stable_id
from book_core.model.spans import SourceLine, SpanStore

TOKEN_PATTERN = regex.compile(r"[\p{L}\p{M}\p{N}]+")


def token_counter(text: str) -> Counter[str]:
    return Counter(TOKEN_PATTERN.findall(unicodedata.normalize("NFKC", text)))


@dataclass(frozen=True)
class TokenOccurrence:
    id: str
    line_id: str
    value: str
    span_ids: tuple[str, ...]


def line_tokens(store: SpanStore, line: SourceLine) -> Iterator[TokenOccurrence]:
    raw = store.raw_line_text(line)
    normalized = unicodedata.normalize("NFKC", raw)
    raw_owners = [sid for sid in line.span_ids for _ in store.spans[sid].raw_text]
    fragments: list[str] = []
    normalized_owners: list[tuple[str, ...]] = []
    for cluster in regex.finditer(r"\X", raw):
        fragment = unicodedata.normalize("NFKC", cluster.group())
        owners = tuple(dict.fromkeys(raw_owners[cluster.start() : cluster.end()]))
        fragments.append(fragment)
        normalized_owners.extend([owners] * len(fragment))
    if "".join(fragments) != normalized:
        # Conservative provenance when compatibility normalization crosses grapheme boundaries.
        # One shared owner is required; no fine-grained ownership is invented.
        normalized_owners = [tuple(line.span_ids)] * len(normalized)
    for ordinal, match in enumerate(TOKEN_PATTERN.finditer(normalized)):
        owners = tuple(
            dict.fromkeys(
                sid
                for cluster_owners in normalized_owners[match.start() : match.end()]
                for sid in cluster_owners
            )
        )
        yield TokenOccurrence(
            id=stable_id(line.id, "token", ordinal),
            line_id=line.id,
            value=match.group(),
            span_ids=owners,
        )
