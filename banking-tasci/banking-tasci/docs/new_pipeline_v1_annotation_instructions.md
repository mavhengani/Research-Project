# `new_pipeline_v1` human annotation instructions

## Uniform batch policy

All eleven approved Candidate 2 annotation files use the same human-only gold-label policy, schema, validation, backup, audit, guide-version, and completion rules. The physical technical batch ID `calibration_001` remains unchanged for checksum/provenance compatibility and is shown to annotators as **Annotation Batch 1**. It is not a distinct pilot, calibration, or annotation method.

| Technical ID | User-facing name | Records |
|---|---:|---:|
| `calibration_001` | Annotation Batch 1 | 50 |
| `main_001`–`main_009` | Annotation Batches 2–10 | 100 each |
| `final_001` | Annotation Batch 11 | 50 |

A guide version is recorded with each workspace. It applies consistently to all batches. There is no gate that requires Batch 1 to finish or a guide-freeze event before another independently approved batch can be opened. Each batch still requires its approved package membership, source checksum, an isolated workspace, atomic backed-up writes, and validation.

## Human-only decisions

Only the researcher may supply gold values. Software may validate the decisions, preserve provenance, and calculate offsets for one unique exact substring selected by the researcher. Software must never infer or suggest labels from text, ratings, metadata, filters, or model predictions.

For each record explicitly decide:

- `primary_intent` using the six allowed values;
- `public_warning` as an explicit Boolean;
- `opinions` as an explicit list. Use `[]` only when the researcher has decided the record has no opinions;
- `annotation_status` as `in_progress` or `completed`, explicitly acknowledging completion.

For every opinion explicitly supply `target` (string or null), `target_type`, `entity`, `attribute`, `category`, `opinion_phrase` (string or null), `sentiment`, and `annotation_notes` (string or null). The category may be assembled deterministically as `ENTITY#ATTRIBUTE` only from the human-supplied entity and attribute. Explicit target/opinion offsets are accepted only when they exactly match researcher-selected text; automatic offset resolution is allowed only for a unique exact substring. Ambiguous/repeated selections require explicit human offsets.

A completion acknowledgement is required for each record whose human fields change. For zero-opinion records, `opinions: []` plus that acknowledgement records the researcher's explicit decision; the software does not decide that a record is zero-opinion.

## Safe workspace operations

Use the current commands in `scripts/annotation_workspace.py`, `scripts/manage_annotation_workspace.py`, and `scripts/annotation_review.py`. Opening, saving, and restoring are dry-run/read-only unless the command explicitly requests a write. Every save requires an actor, reason, the observed working-file SHA-256, workspace version, guide version, exact changed record IDs, and per-record acknowledgement. Before replacement, the tool validates the entire submitted batch and verifies an atomic backup. It never writes to the approved source file or freeze artifacts.

The retired `scripts/activate_calibration_workspace.py` and `scripts/calibration_workspace.py` names are deprecated compatibility entrypoints only; they must delegate to the uniform workflow and preserve dry-run behavior.
