# Adapter B evidence

No book was converted. Inputs: the 8 Step 20 publications (read-only, paths in
`experiments/out/step20/final/performance/<book>.json`) and the owner's latest frontend
outputs of Dermatology, Methods in Cancer Biology and RSSDI Atlas (job folders in
`experiments/adapter_b_run.py`). Deliveries were written to the git-ignored
`.cache/adapter_b/<tag>/<book>/`.

| Path | What |
|---|---|
| `before/runs.json` | The unchanged adapter (`main` at 7d6d8c6a): the Step 20 gate rows for the 8 Step 20 books, plus the 3 frontend books run once with that code |
| `final/runs.json` | Adapter B on all 11 books: DTD, house rules, lossless, character changes, QC verdict, delivery and report hashes |
| `final_rerun/runs.json` | The same 11 runs again; `final/determinism.json` compares the hashes |
| `final/compare_art_lab.json` | ART delivery vs Jaypee's (`book-adapters compare … --book …`) |
| `final/metrics.json` | Before → after per book: index entries and page links, web/e-mail links, boxes, prefaces, soft hyphens left, house findings, order exceptions (`experiments/adapter_b_metrics.py`) |
| `profile_maker/generated_vs_v3.json` | Fields that differ between `jaypee_generated.yaml` (guideline only) and `jaypee_v3.yaml` (`experiments/adapter_b_profile_diff.py`) |
| `profile_maker/profile_test_*.json` | `book-adapters profile test` of both profiles against the ART delivery |

Commands:

```bash
PY=../pdf_book_converter/.venv/bin/python
$PY experiments/adapter_b_run.py --tag final --rerun
$PY experiments/adapter_b_metrics.py --tag final
$PY experiments/adapter_b_profile_diff.py profiles/jaypee/jaypee_generated.yaml profiles/jaypee/jaypee_v3.yaml
```
