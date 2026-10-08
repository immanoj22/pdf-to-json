# Cache validity

Derived evidence is cached per source page with atomic writes and payload checksums.
A producing-source SHA-256 is computed from sorted package-relative Python filenames and
file contents (CRLF normalised to LF). Source files are re-read when computing a key,
including in a long-lived process. Editing any producer changes its cache namespace.
Derivation entry points also reject a changed producer scope after import: restart the
worker after source deployment, so old loaded code cannot populate new-source keys.
No old-project cache is written, cleared or updated.

| Cache | Code scope | Other identity inputs |
|---|---|---|
| extraction/native | caching, device, extraction, model | PDF digest, extractor version/configuration, Python/Unicode/package versions, resolved device, native/cache version |
| object analysis | above plus objects | native identity, analysis version, dependencies, repetition evidence, render configuration |
| repetition | extraction scope | PDF digest, extractor identity, repetition version |
| own layout | analysis scope plus layout | chained analysis identity, LAYOUT_VERSION, dependencies, render scale, resolved device |
| learned detections | above plus detection | source/page and render digest/dimensions, LAYOUT_VERSION, model repository and immutable revision, threshold, dependencies, requested/resolved device |
| fusion | layout and detection scope | complete own/detector payloads and fusion configuration; computed evidence is persisted in experiment sidecars, no independent runtime cache |

The own layout uses no learned weights: model revision and learned threshold are
not applicable there. Its rule constants are covered by source hashing. Dependency
versions are chained where upstream output affects downstream output. Model results
are keyed by their actual execution device after CPU recovery, never stored under a
failed GPU key. Weights/downloads remain ignored and separate from derived outputs.

The bundled producers are covered by the package source scopes. External detector
implementations must provide a producer-source fingerprint through RegionDetector;
external Extractor implementations must carry their code/configuration identity in
ExtractorIdentity (the primary production implementation remains PyMuPDF).
Preserve the complete FusionResult when persisting evidence: model-only proposals
and their review flags live in its comparisons, outside the own PageLayout.

Tests edit every producing source under a temporary package copy and verify that its
digest changes; import-closure tests detect omitted local producer modules. Cache-key
tests also exercise real key functions. Model-output comparisons use geometric and
confidence tolerances; ledger conservation remains exact.
