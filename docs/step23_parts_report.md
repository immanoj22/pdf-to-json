# Step 23 — Book parts without a long rerun

## Measured before (main 276717c2)

PULSE (120 pages), converted, then one part range changed (body 19–117, index 118–120 instead
of 19–116 / 117–120): the rerun computed characters, figures, equations, MathML and tables for
every page again — **1,278 s (21 min)** (profiled run, machine shared), about 1½ h for a
500-page book. The parts reach the structure stage; every later stage key named the lists key,
so a parts change gave every later stage a new key.

## Change

`book_core/page_memo.py`: the expensive per-page work of the book stages is kept by what that
page's work read — the producing code, configuration, the page's layout/native/analysis keys,
and digests of the page's units, figures, equations and character evidence. The book parts are
never part of a page memo key. The stages still run and make their whole-book decisions again
from the per-page results, so the output is what a full run computes.

| stage | kept per page | read back when |
|---|---|---|
| characters | the page observation | same native text, layout and units |
| figures | image measurements (kind, format, edges); exported image bytes | same figure boxes and objects |
| equations | glyph outlines; the page record (detection, ownership, repairs) | same units, figures, character evidence and book glyph/size/pitch evidence |
| tables | the page analysis (tables, candidates, claims, pieces) | same units, figures, equations, navigation kind, page label |

Parts can be given at upload (optional, Convert page); the conversion follows them, and a
later confirmation of the same ranges converts nothing again. Confirmation stays mandatory
before export.

## Results

* Same parts change on PULSE with the memo: **271–290 s** (machine fully loaded by other
  runs); only the page whose part changed (p117) was recomputed in characters, equations and
  tables, none in figures.
* Fast path vs full run with the same parts: **byte-identical, 646 of 646 files**.
* ART, Hypertension, IAP: output content identical to main (only cache keys differ).

## Left for later: the figure step

With every page read back, figures still takes ~90 s for 120 pages: looking up the cached
layout-model detections needs each page rendered (the detection key holds the render's
digest), in the prefetch workers (which also load both models) and again for figure support.
A fix belongs in the detection cache (e.g. a render-digest index keyed by source and page);
changing the detection package changes every book's detection cache key, so it was not done
here. Assembly (~45 s / 120 pages) depends on the parts and reruns by design.
