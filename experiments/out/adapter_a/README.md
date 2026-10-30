# Adapter A run records

Produced by `python experiments/adapter_a_run.py` (one worker, books one after another).

| File | What |
|---|---|
| `runs.json` | Per book: DTD, house-rule and lossless results, review counts, run time, delivery tree hash |
| `compare_art_9789372025262.json` | Our ART delivery vs the real Jaypee delivery (element counts, per chapter, files, labels, page_info) |
| `compare_medical_anatomy.json` | Book 4 vs its (pre-v3) Jaypee reference |
| `ch2_side_by_side.md` | First 60 lines of our `ch2.xml` and the delivered one |
| `run.log` | One line per book |

## Inputs (read-only copies, manifest-verified)

Copied once into the git-ignored `.cache/adapter_inputs/<name>/` (book.json, manifest.json,
images/), so that Step 19's ongoing writes cannot change them. Every file matched its
manifest.

| Name | Source publication |
|---|---|
| art_9789372025262 | frontend job `89ae63f9…` output `book-d1024e8b…` (ART, 9789372025262) |
| iap_mec | frontend job `89ac48f3…` output `book-271abd1b…` |
| trichology | frontend job `0fd7f32e…` output `book-9e7bb503…` |
| art_therapy_index | `.cache/s19/pub/before/art_therapy_index/book-c2f87122…` |
| immigrant_children (book 2) | `.cache/s19/pub/before/immigrant_children/book-b089cf93…` |
| medical_anatomy (book 4) | `.cache/s19/pub/before/medical_anatomy/book-59f8b52d…` |
| statistics | `.cache/s19/pub/before/statistics/book-a22af573…` |

The Step 17b publications named in `docs/step17b_report.md` were made on the Windows machine
and are not on this PC. The Step 19 `before` set (27–28 Oct, not rewritten by Step 19) was
used in their place. No hold-out or sealed book was used.

Deliveries are written to `.cache/adapter_a/<name>/` (git-ignored).
