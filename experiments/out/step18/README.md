# Step 18 evidence

See [the report](../../../docs/step18_report.md) first. This is measurement
evidence for frozen converter `8d6a0b0036db3f28dd8b671a2950ceca9918a680`,
tag `holdout-freeze-1`; no fixes are included.

- [Final assembled results](results_v2.json): M01–M18 for each book. The initial
  [assembly](results.json) is retained, not replaced. v2 adds registered-component
  disclosures and existing OCR-record counts; scoring results are unchanged.
- `ent_textbook/` and `mideast/`: pretty JSON copies of the completed publications,
  exact review exports, original manifests, identity/readable-copy receipts.
  These are not self-contained publication packages; manifest asset hashes refer
  to the unchanged original publication. No image/crop file is included.
- `math_holdout/`: failure identity/status only. No fabricated publication.
- `ent_textbook/alignment_evidence/`: original and pre-score scoped provisional
  mapping/alignment; gold/reference originals were not edited.
- `measurement_evidence/audit/`: fixed sample populations/decisions, 559 agent
  judgments and 20 pending owner re-judgments, uncertainty and error taxonomies.
  Crop/context paths point to retained local images; agent judgments have not
  been independently verified.
- `measurement_evidence/`: attempt/preflight/reuse/monitor/evaluation receipts,
  copy manifests and final integrity inventory. Some live receipts capture an
  intermediate instant; terminal `result.json` receipts establish completion.
  Redundant compressed attempt-1 cache JSON was also copied during packaging and
  retained without deletion. Those copies are evidence, not additional runs.
- `orchestration_tools/`: invocation, routing, monitoring, presentation and report
  helpers. Frozen backend/evaluator implementations remain unchanged. Failed
  wrapper attempts remain preserved separately; no failed check is counted as
  successful.

The earlier 5 MB check concerned the pre-freeze cleanup commit. The expressly
requested readable books and provisional alignments here include four files
above 5 MB: ENT book (54,201,084 B), Mideast book (23,817,123 B), original alignment
(13,250,652 B), scoped alignment (13,250,575 B). They are neither hidden nor omitted.

No source PDFs, reference XML, image/crop binaries, model weights or old project
files are copied. Private/local evidence paths are meaningful on this workspace;
original reference access remains through the registered source keys.
The local `.gitattributes` preserves evidence bytes in Git, including original
CRLF receipts and compressed JSON records; it changes no Git configuration or
converter setting. Recorded SHA-256 values apply to these exact bytes.

Owner review is the next gate. No Step 19 implementation or adapter work follows
automatically.
