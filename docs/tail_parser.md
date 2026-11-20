# Reference parser: two readers and the validators

Every reference is read twice: by the **trained parser** (AnyStyle, a CRF model, MIT licence, runs
locally and offline) and by our **rules** (`formats/vancouver.py`). `formats/hybrid.py` chooses:

* a reading must pass the **validators**: a 4-digit year, real surnames (not initials, not empty),
  a title, a source that is not a one-letter / year-like / identifier text, a journal article with a
  volume or pages, a real volume;
* one passes: it is used; both pass and agree (authors, year, title): the rules' reading (the
  client's tag conventions); both pass, one title holds the other: the longer, unless the rules'
  title was cut at an abbreviation (flagged); both pass and disagree, or neither passes: the closer
  reading, **flagged as a review item** (kind `reference`), never silent. A one-letter source is
  never written.
* the same reading feeds tail, BITS and JATS (`structured_references`: a reference is written as
  `element-citation` only when it has no flag).

## Set up the trained parser (no Docker, no root)

```
micromamba create -p $ANYSTYLE_HOME/rb -c conda-forge ruby=3.3 c-compiler cxx-compiler make
GEM_HOME=$ANYSTYLE_HOME/rb/share/rubygems $ANYSTYLE_HOME/rb/bin/gem install anystyle-cli --no-document
# ANYSTYLE_HOME defaults to tools/anystyle_home next to the script (the app: anystyle_command in app_settings.yaml)
BOOK_ANYSTYLE_CMD=/path/to/tools/anystyle.sh   # or anystyle_command: in app_settings.yaml
```
Without it the rules read alone (a reference they cannot read is flagged). GROBID could be a third
reader later (same `parse_many` shape).

## Learning

A reference a person corrected in the review (Correct the text…) and that is then read without a
flag is saved as a training sample in **one file on this machine**,
`<app data>/reference_training/samples.jsonl` (git-ignored, never uploaded), with the **job id**.

```
python -m book_adapters references stats      --dir app_data/reference_training
python -m book_adapters references retrain    --dir app_data/reference_training   # writes model.mod
python -m book_adapters references delete-job --dir app_data/reference_training JOBID
```
The app uses `model.mod` (passed to AnyStyle with `-P`) the next time it starts.

## Results (CPU, same PDFs)

| PDF | refs | not flagged | notes |
|---|---|---|---|
| ref.pdf (Vancouver) | 147 | 124 (84%) | 137/147 identical to tail.xml, lossless 0/0 |
| Hypertension (`1.`) | 112 | 100 (89%) | lossless 0/0 |
| IEEE file | 93 | 81 (87%) | lossless 0/0, no one-letter source |

Flagged references are written best-effort and listed for review.

## CRLF

Every tail path ends in `tail.document`, which forces CRLF on every line. The zips found in
Downloads and Trash (including the 93-reference `delivery.zip`) all hold CRLF (947 `\r`, 947 `\n`
for that file); a test unzips the downloaded zip and checks it. A reader that opens the file in
text mode with universal newlines (Python `open(..., "r")`, many editors) shows no `\r`.
