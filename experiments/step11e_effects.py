"""Explain Step 11e paragraph boundaries and reading-order score changes."""

# ruff: noqa: E402
import hashlib
import io
import subprocess
import tarfile
from collections import defaultdict

from step11e_run import BASE, CACHE, CACHE9, CACHE11, OUT, ROOT, read, write

from book_core.cache_store import read_json
from book_core.caching import SCOPES, code_digest, scope_files
from book_core.evaluation.derived_harness import DerivedGold
from book_core.evaluation.furniture import token_lines
from book_core.evaluation.paragraphs import reference_tokens
from book_core.evaluation.reading_order import ReadingOrderOutput, page_order, reading_order_scores
from book_core.layout.models import PageLayout
from book_core.layout.pipeline import layout_fingerprint
from book_core.lists.cache import BookListsResult
from book_core.lists.cache import load_page as list_page
from book_core.lists.keys import book_fingerprint
from book_core.lists.models import TEXT_KINDS
from book_core.model.spans import ExtractedPage
from book_core.objects.analysis import verified_read
from book_core.paragraphs.anchors import move_anchors
from book_core.paragraphs.cache import BookParagraphResult
from book_core.paragraphs.cache import load_page as paragraph_page
from book_core.paragraphs.text import unit_text


def producer_scope_identity(original):
    """Record raw measurement bytes and the producer's canonical identity separately."""
    captured = {
        name: (ROOT / "backend/src/book_core" / name).read_bytes() for name in scope_files("layout")
    }
    raw_hashes = {name: hashlib.sha256(data).hexdigest() for name, data in captured.items()}
    assert all(
        hashlib.sha256((ROOT / "backend/src/book_core" / name).read_bytes()).hexdigest() == value
        for name, value in raw_hashes.items()
    )
    normalized, eol_only, product_changes = {}, [], []
    reconstructed = hashlib.sha256(b"layout")
    for name, raw in captured.items():
        canonical = raw.replace(b"\r\n", b"\n")
        normalized[name] = hashlib.sha256(canonical).hexdigest()
        reconstructed.update(b"\0" + name.encode("utf8") + b"\0")
        reconstructed.update(hashlib.sha256(canonical).digest())
        if raw != original[name]:
            if canonical == original[name].replace(b"\r\n", b"\n"):
                eol_only.append(name)
            else:
                product_changes.append(name)
    assert product_changes == ["layout/pipeline.py"]
    assert reconstructed.hexdigest() == code_digest("layout")
    baseline_revision = (
        subprocess.check_output(["git", "rev-parse", "90a544a"], cwd=ROOT).decode().strip()
    )
    return {
        "scope_files": raw_hashes,
        "scope_files_normalized_sha256": normalized,
        "scope_byte_identity": {
            "algorithm": (
                "Canonical bytes replace CRLF with LF only, exactly as "
                "book_core.cache_identity.producer_digest; raw scope_files hashes remain unchanged."
            ),
            "producer_digest_algorithm": (
                "SHA-256 seeded with UTF-8 scope name, then sorted file names delimited by NUL "
                "and each canonical file SHA-256 digest."
            ),
            "raw_scope_hashes_verified_before_derivation": True,
            "comparison_revision_at_audit": baseline_revision,
            "raw_vs_baseline_eol_only_files": eol_only,
            "raw_vs_baseline_product_change_files": product_changes,
            "pipeline_raw_sha256_required_to_match_commit": True,
            "canonical_layout_digest_reconstructed": reconstructed.hexdigest(),
        },
    }


def main():
    book = "spanish_us_history"
    gold = DerivedGold.load(ROOT / "backend/tests/gold_derived" / book)
    _, reference_owner = reference_tokens(gold)
    archive = read(ROOT / "experiments/out/step11c/archive" / f"{book}.json")
    versions = [read(BASE / f"{book}.json"), read(OUT / f"after/{book}.json")]
    results = []
    for version in versions:
        keys = version["keys"]
        paragraphs = verified_read(
            CACHE9 / "paragraphs/book" / f"{keys['paragraphs']}.json",
            BookParagraphResult,
            keys["paragraphs"],
        )
        lk = book_fingerprint(keys["lists"])
        lists = verified_read(CACHE11 / "lists/book" / f"{lk}.json", BookListsResult, lk)
        logical, descriptions, stages = {}, {}, {}
        views = {name: {} for name in ("step11", "step9", "nearest", "end")}
        for number in (324, 350, 361, 724):
            page = ExtractedPage.model_validate(
                read_json(ROOT / archive["output"] / f"page_{number:06d}.json.gz")["source"]
            )
            layout = verified_read(
                CACHE / "layout" / keys["layout"] / f"{number}.json", PageLayout, keys["layout"]
            )
            built = list_page(lists, number, CACHE11)
            step9 = paragraph_page(paragraphs, number, CACHE9)
            owners = token_lines(page, layout)
            unit_of = {lid: u for u in built.units for lid in u.line_ids}
            for ordinal, lid in enumerate(owners):
                unit = unit_of.get(lid)
                if unit is not None and unit.kind in TEXT_KINDS:
                    logical[(number, ordinal)] = unit.id
            views["step11"][number], _ = page_order(page, layout, built.order)
            views["step9"][number], _ = page_order(page, layout, step9.order)
            for rule in ("nearest", "end"):
                moved, _ = move_anchors(built.order, built.units, rule)
                views[rule][number], _ = page_order(page, layout, moved)
            for stage, value in (("paragraphs", step9), ("lists", built)):
                stages.setdefault(stage, {})[str(number)] = [
                    {
                        "id": u.id,
                        "kind": u.kind,
                        "stream_kind": u.stream_kind,
                        "line_ids": u.line_ids,
                        "text": unit_text(page.store, layout, u),
                        "boundary": u.boundary.model_dump(mode="json"),
                        "joins": [j.model_dump(mode="json") for j in u.joins],
                    }
                    for u in value.units
                ]
            descriptions.update({u["id"]: u for u in stages["lists"][str(number)]})
        ref_tokens, our_tokens = defaultdict(set), defaultdict(set)
        for token, uid in logical.items():
            if token in reference_owner:
                ref_tokens[reference_owner[token]].add(token)
                our_tokens[uid].add(token)
        refs = {}
        for uid, tokens in ref_tokens.items():
            pieces = {logical[t] for t in tokens}
            refs[uid] = {
                "exact": len(pieces) == 1 and our_tokens[next(iter(pieces))] == tokens,
                "pieces": sorted(pieces),
                "tokens": sorted(tokens),
            }
        results.append(
            {
                "references": refs,
                "units": descriptions,
                "stages": stages,
                "reading_order": {
                    name: reading_order_scores(gold, ReadingOrderOutput(name, book, {}, {}, pages))
                    for name, pages in views.items()
                },
            }
        )
    changed_refs = {}
    for uid in results[0]["references"]:
        a, b = [r["references"][uid] for r in results]
        if a["exact"] != b["exact"] or len(a["pieces"]) != len(b["pieces"]):
            changed_refs[uid] = {
                "reference": next(u for u in gold.units if u["unit"] == uid),
                "before": {**a, "paragraphs": [results[0]["units"][u] for u in a["pieces"]]},
                "after": {**b, "paragraphs": [results[1]["units"][u] for u in b["pieces"]]},
            }
    write("effects.json", {"changed_reference_units": changed_refs, "versions": results})
    current_key = layout_fingerprint(versions[1]["keys"]["analysis"], "cpu")
    assert current_key == versions[1]["keys"]["layout"] == read(OUT / "isolated.json")["layout_key"]
    archived = subprocess.check_output(
        ["git", "archive", "90a544a", "backend/src/book_core"], cwd=ROOT
    )
    with tarfile.open(fileobj=io.BytesIO(archived)) as archive:
        original = {
            member.name.removeprefix("backend/src/book_core/"): archive.extractfile(member).read()
            for member in archive.getmembers()
            if member.isfile()
        }
    scopes = {}
    for scope in SCOPES:
        digest = hashlib.sha256(scope.encode("utf8"))
        for name in scope_files(scope):
            digest.update(b"\0" + name.encode("utf8") + b"\0")
            digest.update(hashlib.sha256(original[name].replace(b"\r\n", b"\n")).digest())
        scopes[scope] = {"before": digest.hexdigest(), "after": code_digest(scope)}
    assert [name for name, row in scopes.items() if row["before"] != row["after"]] == ["layout"]
    write(
        "producer_identity.json",
        {
            "layout_producer_digest": code_digest("layout"),
            "layout_key": current_key,
            "spanish_metrics_keys": read(OUT / "metrics" / book / "summary.json")[
                "cache_key_inputs"
            ],
            "pipeline_sha256": hashlib.sha256(
                (ROOT / "backend/src/book_core/layout/pipeline.py").read_bytes()
            ).hexdigest(),
            **producer_scope_identity(original),
            "tests_enter_layout_producer": any(
                f.startswith("tests/") for f in scope_files("layout")
            ),
            "current_key_equals_isolated_and_spanish_run": True,
            "all_producer_scopes": scopes,
        },
    )
    print("Changed reference units:", list(changed_refs))
    for uid, row in changed_refs.items():
        print(uid)
        for side in ("before", "after"):
            print(side, [u["text"] for u in row[side]["paragraphs"]])


if __name__ == "__main__":
    main()
