# Banking TASCI `new_pipeline_v1` progress report

**Assessment date:** 27 October 2026  
**Scope:** Requirement-by-requirement implementation and research-readiness review  
**Git provenance:** `main`; no commit exists (`UNKNOWN_NO_COMMIT`).  
**Execution restrictions:** GPU/cluster investigation and U1/U2 pilots remain paused. No local CPU pilot, human labels, final split, supervised training, final domain adaptation, or commit was performed for this assessment.

## Executive status

The data preparation, candidate selection, freeze, strict unlabelled corpus, and U1/U2 smoke-test foundations are present and evidenced. The central remaining dependency is **manual annotation of the 1,000 frozen Candidate 2 records**. At the latest metadata check, the existing isolated workspace was `calibration_001`, 0/50 complete, and still used the old workspace metadata shape. The researcher has since specified that all eleven batches follow the same human-only workflow: `calibration_001` remains the immutable technical ID but is displayed as **Annotation Batch 1**, not as a distinct calibration method. The authoritative requirements document still describes a calibration stage; that written discrepancy needs a formal requirements amendment to prevent future sessions following the superseded method.

This report separates **software readiness** from **research execution**. Passing tooling tests do not mean human gold exists or experiments have run. Overall completion is not compressed into one percentage because the unweighted average would conflate infrastructure with the still-unstarted annotation, supervised training, and evaluation work.

## Requirement-aligned progress matrix

| Requirement area | Status | Current evidence and remaining work |
|---|---|---|
| Purpose, versioning, migration (Sections 1, 28–30) | **Mostly complete** | `new_pipeline_v1` config and authorised U0/U1/U2 amendment exist. No Git commit, so run-level commit provenance remains unresolved. |
| Data counts and manifests (Sections 4–6) | **Complete for prepared assets; some preparation evidence partial** | Verified sources: 100,768 South African candidates and 10,847 international records; combined 111,615. Strict unlabelled corpus contains 110,615 records, checksum `5ea719ec528510ddd8566410a1b533ff294093c2ce87538f472dae789cf9e3ea`, zero frozen-ID overlap, privacy PASS. Broader cleaning/privacy provenance is documented but remains a partial audit finding. |
| Sample, approval, immutable identity freeze (Sections 7, 13.5) | **Complete** | Candidate 2 is approved and Freeze Revision 2 is `FROZEN`: 1,000 IDs (500/250/250, regions 500/500). Gold-ID checksum: `fdee989ff1a5935b5404488b215ebda60da86cf0da2f9d81bb1f684d055cea4f`. No labels are part of the freeze. |
| Eleven approved batches and membership (Section 13) | **Artifacts complete; current operations partially migrated** | All 11 physical batch files retain their approved IDs and checksums; the batch manifest and Freeze Revision 2 membership checksum verify. Batch sizes are 50 + 9×100 + 50. New code defines user-facing names 1–11 and uniform metadata/workflow, but the currently active Batch 1 workspace still has the legacy manifest fields; uniform workspace migration/opening for all eleven has not been completed or integration-tested. |
| Human-only annotation, backups, audit, adjudication (Sections 8, 10–14) | **Tooling partial; research labels not started** | Schema, validator, safe checkpoint/restore code, audit utilities, and explicit human decision/adjudication scaffolding exist. Current workspace metadata reports 0 completed. No annotations or adjudicated gold have been created. Need finish migration of active workspace metadata, ensure every save requires record ID, intent, Boolean warning decision, opinions including explicit `[]` for researcher-confirmed zero opinions, acknowledgement, current file checksum, workspace version, and guide version; exercise uniformly for all 11 technical IDs using synthetic fixtures. |
| Calibration methodology interpretation (Section 13.2) | **Requirements conflict identified** | Researcher instruction says there is no separate calibration methodology. Continue to treat all batches uniformly; retain `calibration_001` only for immutable ID/provenance and display it as Annotation Batch 1. Update the authoritative requirements and related historical docs under an explicit amendment so the old calibration gate cannot be revived. |
| Final gold validation (Sections 14, 13.5) | **Implemented, not run on real gold** | Read-only `final_gold_validation.py` validates a completed 1,000-record input against approved package, all 11 memberships, and frozen IDs. Synthetic tests pass. No valid completed-gold input exists yet, so the real final-gold gate is unrun. |
| Group-aware 80/10/10 split (Section 15) | **Not ready / implementation gap** | Legacy `scripts/create_splits.py` is tied to the legacy annotation schema, defaults to prohibited 70/15/15, and emits CSV ID manifests plus a report rather than the required full JSONL, split manifest, distributions, and leakage reports. No new-pipeline 800/100/100 split has been created. Build and test a separate `new_pipeline_v1` split-preparation path after human gold validation; never run it on current data. |
| Strict MLM corpus (Section 16) | **Complete** | Text-only corpus and manifests are present and verified; no labels or protected gold IDs are included. |
| U0/U1/U2 adaptation (Section 17 and authorised amendment) | **Smoke complete; pilots deferred** | Shared U1/U2 implementation/configs and CPU smoke evidence exist; U1/U2 smoke reports and artifacts are preserved. No one-epoch pilot or final adaptation has run. The failed U1 cluster preflight is not a training result. Per researcher instruction, do not inspect cluster/GPU or run pilots until separately authorised. |
| Target extraction and category prediction (Sections 18–19) | **Partial / missing** | BIO alignment utilities and a legacy BERT token-classification baseline exist. No new-pipeline self-attention extractor or canonical entity-attribute text/category pair learner is implemented. |
| Intent model (Section 20) | **Partial / missing** | Legacy SVM/BiLSTM/BERT baselines and genuine-context rendering exist. New six-intent training configuration integration and required GRU contextual model/paired current-only-context experiments remain absent. Current Candidate 2 records have no verified previous context, so context experiment is not currently supported by this gold sample. |
| Sentiment and TASCI integration (Sections 21–22) | **Partial / mostly missing** | Legacy SVM/BiLSTM/BERT sentiment infrastructure exists. New four-label downstream builders/configs, GloVe loader, intent projection/fusion, TASCI sentiment head, and integrated inference are missing or incomplete. |
| Transfer, ablation, five-seed experiments (Sections 23–24) | **Not executed; scaffolding partial** | Representation matrix lists U0/U1/U2 tasks/domains and five seeds. Transfer/ablation registries, experiment runners, seed aggregation, subgroup/error-analysis outputs, and actual matched runs are not complete. No final metrics or predictions exist for `new_pipeline_v1`. |
| Reproducibility, ethics, tests (Sections 25–27, 32–33) | **Partial** | Privacy handling, manifests, schema tests, checksum gates, existing evaluation utilities, and immutable run patterns are available. No Git commit; full suite not run after recent workflow changes; some Section 32 end-to-end/new-schema/split/five-seed coverage remains. |

## Verified data and protected-artifact status

Read-only checks on 27 October confirmed:

- Candidate 2 sample plan SHA-256: `ff8f88e0fe2741a6b9c4da0cb6ef3ade94deb87bee8f4a7d706daf21d82b8c2d`.
- Candidate 2 label-hidden annotation package SHA-256: `4399dfb086fb883c7bff5584a9fed67451247cb7729187a580b24bac3e140f46`.
- Candidate 2 batch manifest SHA-256: `2a557eee8c702306e54a6ff196035e58fb79cab568d50cfae9c093eafea65ef5`.
- Freeze Revision 2 membership SHA-256: `c59300ee14ef733e864f10a442e879a7c0fb83932c7ccbf425e3961e2eebc1da`.
- Technical batch `calibration_001` SHA-256: `7665366000c4b95b6c57fac91a2bd786098f16848001bf59a5c2c5a0b8700e66`.
- Freeze Revision 2 manifest SHA-256: `9f1ea416430979040a613daae132859b7021157fb3a4ca5f26cb943e1cfd005e`.
- Frozen ID JSONL SHA-256: `fdee989ff1a5935b5404488b215ebda60da86cf0da2f9d81bb1f684d055cea4f`.
- Strict unlabelled corpus SHA-256: `5ea719ec528510ddd8566410a1b533ff294093c2ce87538f472dae789cf9e3ea`.
- Every file checksum in the Candidate 2 batch manifest matches its physical batch file (11/11).
- U1/U2 smoke evidence remains at the previously recorded paths; the smoke reports and model/run artifacts were not changed during this review.

The active Batch 1 workspace metadata is still legacy-shaped: `batch_id=calibration_001`, `batch_status=in_progress`, 0/50 completed, with no persisted `technical_batch_id`, display name, approved membership checksum, guide version, workspace version, or last-updated fields. This is a known migration task, not a protected-source checksum mismatch. The current Candidate 2 source batches and frozen artifacts were not modified.

## Current focused verification

Command run locally from the project root using `.venv/bin/python`:

`tests/test_calibration_workspace.py tests/test_calibration_activation.py tests/test_new_pipeline_adjudication.py tests/test_new_pipeline_annotation_validator.py tests/test_new_pipeline_schema.py tests/test_annotation_workflow.py tests/test_annotation_batches.py tests/test_final_gold_validation.py -q`

**Result: 169 passed, 5 deprecation warnings.** The warnings are from legacy calibration-named wrappers retained for compatibility. Recent module compilation also passed. The full test suite was not run; this focused result does not establish full regression status.

## What is done vs. what remains to finish

### Completed foundations

1. Source preparation/manifests and verified counts.
2. Candidate 2 1,000-record selection, approval, Freeze Revision 2, strict unlabelled corpus.
3. Eleven immutable batch files/membership, verified checksums.
4. Canonical new-pipeline schema/taxonomy and substantial validation.
5. U1/U2 implementation and smoke execution evidence (not full pilots).
6. Synthetic-tested final-gold validation, group-aware annotation helpers, safe backup/checkpoint and explicit human-only adjudication foundations.

### Critical remaining work, in order

1. **Formalize and complete the uniform annotation methodology.** Amend the authoritative Section 13 wording to remove the now-superseded calibration methodology. Finish uniform metadata for all batches and safely migrate the existing Batch 1 workspace metadata only after a controlled migration/backup design. Do not alter source batch files or membership.
2. **Finish and manually complete all 1,000 annotations.** Human decisions must be supplied by the researcher; software cannot generate labels. Validate each submitted batch and preserve decision provenance/backups. Current progress is 0/1,000.
3. **Adjudicate and run the real final-gold gate.** Ensure disagreements are resolved by documented human decisions; produce and freeze a checksum-backed completed-gold package only after the validator passes.
4. **Implement a dedicated new-pipeline split-preparation tool.** Must use the new schema, enforce whole leakage groups, pin 80/10/10 and seed 42, emit the required full-record JSONL and distribution/leakage reports, and remain dry-run/read-only until explicitly approved. Do not create the real split yet.
5. **Build task-specific `new_pipeline_v1` datasets/configurations.** Add target, category, intent, sentiment, and integrated training input builders; SVM/BiLSTM baseline configurations; U0/U1/U2 downstream conditions; source-only/mixed-domain transfer and matched ablations.
6. **Implement missing TASCI components.** Self-attention aspect extraction, category-pair prediction, contextual GRU intent, GloVe/OOV policy, intent fusion, sentiment head, and structured inference remain to be implemented and tested.
7. **Implement evaluation/reproducibility completion.** Add five-seed aggregation, subgroup and error-analysis reports, reload/resume checks for downstream components, immutable run artifacts with all checksums, and Git provenance after explicit commit authorization.
8. **Run research experiments only after gates pass.** U1/U2 pilots remain paused by researcher decision. No final adaptation, supervised training, transfer, ablation, or five-seed run is currently authorized/performed.

## Overall readiness conclusion

`new_pipeline_v1` is **not complete and not ready for final experiments**. Its data/provenance and self-supervised smoke foundations are strong, but the principal human-gold dependency is 0/1,000; the new split pipeline and most new-pipeline supervised/TASCI models are absent; no one-epoch U1/U2 pilot has completed; and no new-pipeline downstream or five-seed results exist. The immediate critical path is uniform, human-led annotation and validated gold completion—not cluster execution.

The older 20 October progress report is retained as historical session evidence. This 27 October assessment supersedes its statements that Batch 1 is a special calibration phase and its 0/50 framing for project-wide annotation progress.
