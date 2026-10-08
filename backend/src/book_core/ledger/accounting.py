"""Validate occurrence identity, real node references, and retained token multisets."""

from collections import Counter

from book_core.extraction.fingerprints import stable_id
from book_core.ledger.records import (
    DiscardAssignment,
    DiscardRecord,
    LedgerReport,
    NodeAssignment,
    WordLedger,
)
from book_core.ledger.tokenization import TokenOccurrence, line_tokens, token_counter
from book_core.model.document import Document


def span_owners(document: Document) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = {}
    for node in document.iter_nodes():
        for ref in node.content:
            owners.setdefault(ref.span_id, set()).add(node.id)
    return owners


def candidate_owners(token: TokenOccurrence, owners: dict[str, set[str]]) -> set[str]:
    candidates = [owners.get(sid, set()) for sid in token.span_ids]
    return set.intersection(*candidates) if candidates else set()


def allocate(document: Document) -> WordLedger:
    """Use actual node content references; unowned/ambiguous tokens remain check failures."""
    owners = span_owners(document)
    frames = {page.page: page.content_bbox for page in document.metadata.pages}
    assignments: list[NodeAssignment | DiscardAssignment] = []
    discards: list[DiscardRecord] = []
    for line in document.span_store.lines:
        if not document.span_store.raw_line_text(line).strip():
            continue
        tokens = list(line_tokens(document.span_store, line))
        if not frames[line.page].contains_center(line.bbox):
            discard = DiscardRecord(
                id=stable_id(line.id, "trimbox_discard"),
                line_id=line.id,
                page=line.page,
                bbox=line.bbox,
                span_ids=line.span_ids,
            )
            discards.append(discard)
            assignments.extend(
                DiscardAssignment(token_id=token.id, discard_id=discard.id) for token in tokens
            )
        else:
            for token in tokens:
                candidates = candidate_owners(token, owners)
                if len(candidates) == 1:
                    assignments.append(NodeAssignment(token_id=token.id, node_id=candidates.pop()))
    return WordLedger(assignments=assignments, discards=discards)


def check(
    document: Document, ledger: WordLedger, expected_retained: Counter[str] | None = None
) -> LedgerReport:
    store = document.span_store
    frames = {page.page: page.content_bbox for page in document.metadata.pages}
    lines = {line.id: line for line in store.lines}
    tokens = {token.id: token for line in store.lines for token in line_tokens(store, line)}
    nonblank = [line for line in store.lines if store.raw_line_text(line).strip()]
    excluded = {line.id for line in nonblank if not frames[line.page].contains_center(line.bbox)}
    raw = Counter(token.value for token in tokens.values())
    retained = Counter(token.value for token in tokens.values() if token.line_id not in excluded)
    assigned = Counter()
    node_counter = Counter()
    assigned_by_node: dict[str, Counter[str]] = {}
    discard_counter = Counter()
    errors: list[str] = []
    owners = span_owners(document)
    for sid, candidates in owners.items():
        if len(candidates) > 1:
            errors.append(f"Span {sid} has multiple content owners")
    discard_ids = [record.id for record in ledger.discards]
    if len(discard_ids) != len(set(discard_ids)):
        errors.append("Duplicate discard identifier")
    discards = {record.id: record for record in ledger.discards}
    claimed_lines: set[str] = set()
    for discard in ledger.discards:
        if discard.line_id not in excluded:
            errors.append(f"Discard {discard.id} is not an explicit TrimBox exclusion")
            continue
        line = lines[discard.line_id]
        if (
            discard.span_ids != line.span_ids
            or discard.bbox != line.bbox
            or discard.page != line.page
            or discard.line_id in claimed_lines
        ):
            errors.append(f"Discard {discard.id} disagrees with source line evidence")
        claimed_lines.add(discard.line_id)
    if claimed_lines != excluded:
        errors.append("Explicit discard records do not cover excluded nonblank source lines")
    occurrence_counts = Counter(assignment.token_id for assignment in ledger.assignments)
    for tid in tokens:
        if occurrence_counts[tid] != 1:
            errors.append(f"Token {tid} has {occurrence_counts[tid]} assignments")
    unknown_count = 0
    for assignment in ledger.assignments:
        token = tokens.get(assignment.token_id)
        if token is None:
            unknown_count += 1
            errors.append(f"Unknown token {assignment.token_id}")
            continue
        assigned[token.value] += 1
        if isinstance(assignment, NodeAssignment):
            candidates = candidate_owners(token, owners)
            if candidates != {assignment.node_id} or token.line_id in excluded:
                errors.append(f"Token {token.id} does not belong to its declared node")
            if any(owners.get(sid) != {assignment.node_id} for sid in token.span_ids):
                errors.append(f"Token {token.id} has ambiguous span ownership")
            assigned_by_node.setdefault(assignment.node_id, Counter())[token.value] += 1
        else:
            discard = discards.get(assignment.discard_id)
            if discard is None or discard.line_id != token.line_id:
                errors.append(f"Token {token.id} does not belong to its declared discard")
            discard_counter[token.value] += 1
    for node in document.iter_nodes():
        realized = token_counter(store.resolve_content(node.content))
        node_counter.update(realized)
        if realized != assigned_by_node.get(node.id, Counter()):
            errors.append(f"Node {node.id} content tokens disagree with its ledger assignments")
    expected_missing = expected_extra = None
    if expected_retained is not None:
        expected_missing = sum((expected_retained - node_counter).values())
        expected_extra = sum((node_counter - expected_retained).values())
    return LedgerReport(
        source_line_count=len(nonblank),
        excluded_line_count=len(excluded),
        retained_line_count=len(nonblank) - len(excluded),
        source_token_count=sum(raw.values()),
        retained_token_count=sum(retained.values()),
        node_token_count=sum(node_counter.values()),
        discard_token_count=sum(discard_counter.values()),
        missing_token_count=sum((raw - assigned).values()),
        extra_token_count=sum((assigned - raw).values()) + unknown_count,
        retained_missing_token_count=sum((retained - node_counter).values()),
        retained_extra_token_count=sum((node_counter - retained).values()),
        expected_missing_token_count=expected_missing,
        expected_extra_token_count=expected_extra,
        ownership_errors=errors,
    )
