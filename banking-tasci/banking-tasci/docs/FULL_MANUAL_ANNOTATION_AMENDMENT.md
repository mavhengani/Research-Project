# Full Manual Annotation Amendment

**Project:** Banking TASCI `new_pipeline_v1`

**Recorded:** 27 October 2026

**Status:** Researcher-directed workflow documented; corresponding text in `NEW_PIPELINE_REQUIREMENTS.md` still requires reconciliation.

## Scope

The approved Candidate 2 sample contains exactly 1,000 frozen record identities. All gold task labels for those records must come from explicit human decisions. Software may present label-hidden records, validate entries, preserve approved membership and provenance, calculate unambiguous offsets from human-selected text, and support safe saves, backups, review, and adjudication. It must not infer, propose, or fill gold values from record text, ratings, metadata, candidate filters, model output, or AI-generated annotation.

The eleven approved physical batches remain unchanged: `calibration_001` (50 records), `main_001` through `main_009` (100 records each), and `final_001` (50 records). Their technical identifiers, membership, source files, checksums, and freeze artifacts remain immutable. In the annotation interface they are **Annotation Batches 1–11**. The name `calibration_001` is a historical technical identifier, not a separate annotation method or a gate that prevents work on the other approved batches.

Every batch uses the same human-only schema, guide-version recording, completion acknowledgement, validation, safe workspace writes, backups, and audit history. The researcher decides the intent, public-warning flag, and every opinion field for each record. An empty opinion list is an explicit human decision. Any disagreement requiring adjudication is resolved through a recorded human decision before the final gold package is validated.

## Gates and provenance

Opening or saving a batch requires its approved membership and checksum to verify. A completed 1,000-record gold package must pass schema, offset, privacy, group, and frozen-ID validation, then be versioned and checksummed before any train/validation/test split. No current label-hidden package or empty workspace is evidence of completed human annotation.

`NEW_PIPELINE_REQUIREMENTS.md` Section 13.2 still describes Batch 1 as a calibration stage followed by a guide-freeze gate. That wording conflicts with the researcher-directed uniform workflow recorded here and in `docs/new_pipeline_v1_annotation_instructions.md`. This document records the change for review; the authoritative requirements text and historical handovers must be reconciled before treating the conflict as closed. It does not alter frozen data, approvals, or the approved batch manifest.

**Related documents:** `docs/new_pipeline_v1_annotation_instructions.md`, `docs/new_pipeline_v1_calibration_instructions.md`, and `NEW_PIPELINE_REQUIREMENTS.md`.
