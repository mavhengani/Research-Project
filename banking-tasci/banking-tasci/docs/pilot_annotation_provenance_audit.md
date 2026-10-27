# Pilot Annotation Provenance Audit

**Date:** 25 September 2026

The stored `pilot_unannotated.jsonl` is not a pristine label-hidden input. It
contains 600 completed records, 426 records with non-empty aspects, and 150 null
intents. Its SHA-256 is identical to `pilot_annotator_a.jsonl`; all three
non-adjudicated files share the same canonical annotation-content hash after
annotator metadata is removed.

The authoritative original-component gold remains
`data/annotations/pilot_adjudicated.jsonl`. No annotation file was restored,
renamed, or modified. Complete checksums and counts are recorded in
`outputs/pilot_annotation_provenance_audit.json`.
