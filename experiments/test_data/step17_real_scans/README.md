# Step 17 real scanned pages

Frozen downloaded inputs: 54 Wikisource pages (15 Arabic, 18 Greek, 21 Chinese), separate
from the earlier Step 16 set. Chinese includes simplified/traditional horizontal print,
traditional vertical print and vertical handwriting. Greek includes monotonic and
polytonic text, tables and two-column pages. Multiple pages can come from the same work;
these are not 54 independent books.

Each directory contains the raster `page.jpg`, the revision's transcription in HTML,
wikitext and text, and `source.json`. The source record preserves the Wikisource revision,
human proofreading level (3 or 4), Commons image identity, public-domain licence metadata
and source URLs. Downloaded source records retain their original
`downloaded_pending_manual_text_qa` status: this experiment uses the public proofreading
evidence and does not claim an additional independent full-page transcription audit.

Treat these files as read-only benchmark inputs. Do not correct ground truth to agree
with an OCR result. The collection used `step16_real_data.py` with the Step 17 candidate
manifests. `step17_real_eval.py` reuses `step16_real_eval.truth` to derive evaluation text;
the exact derived truths and observations are under `experiments/out/step17/real_eval`.
`step17_real_summary.py` records evaluation ordering separately from OCR emission order.
`step17_primary_policy.py` replays the eligibility rule from captured geometry without
running OCR again when the image hash and captured reading match.
