# Banking TASCI `new_pipeline_v1` Progress Report

**Report date:** 14 October 2026  
**Pipeline version:** `new_pipeline_v1`  
**Git state:** `UNKNOWN_NO_COMMIT` (no commit created)  
**Session mode:** `TESTS_NOT_RUN_IMPLEMENTATION_ONLY_SESSION`

## Executive summary

The verified source-corpus preparation and candidate 1,000-record package/batching work are in place. An implementation layer for package review, explicit researcher approval, immutable identity freeze, calibration controls, and safe annotation resumption has since been added. That newest layer has **not been tested or executed**. The existing candidate package is **not approved, not frozen, and not annotated**; the static review recommendation remains `NOT_READY_FOR_RESEARCHER_APPROVAL`.

No train/validation/test partitions or strict unlabelled corpus have been created. No model training or Git commit has been performed.

## Data and candidate-package status

| Item | Current documented state |
|---|---|
| South African candidate corpus | 100,768 records, unique IDs, zero duplicate IDs; materialised and manifest-verified |
| International prepared corpus | 10,847 records; manifest-verified |
| Combined relevant corpus | 111,615 records; combined manifest verified |
| Candidate sample plan | 1,000 records: 500 South African tweets, 250 international tweets, 250 international reviews |
| Canonical IDs | 1,000 unique namespaced IDs; no cross-source collision recorded |
| Annotation package | Label-hidden candidate records; 1,000 records, with empty `opinions`, null task labels, and `not_started` status per prior static review |
| Existing batches | 11 files: calibration 50, nine main batches of 100, final 50; total 1,000 |
| Package approval | Not performed; no approval artifact created |
| Gold identity freeze | Not performed; no frozen ID manifest created |
| Human annotation | Not started |

## Candidate package review status

The existing report at [annotation_package_review.md](annotation_package_review.md) records checksums and static findings for the currently persisted package. Its recommendation is **`NOT_READY_FOR_RESEARCHER_APPROVAL`**. Reported issues requiring researcher resolution or explicit acceptance include:

- South African v2 candidate-rule coverage is unavailable in the saved sample plan.
- `duplicate_group`, `leakage_group`, `review_id`, `thread_id`, and `conversation_id` are null throughout, so group/linkage integrity cannot be established from the package.
- The sample has no context-available examples.
- 71 international review records have the literal `review` in the bank field.
- The persisted main/final batches are not consistently source-balanced; several main batches are source-homogeneous and the final batch is South African-only.
- Existing batch files were created before a later batching-code update; they were not regenerated during the subsequent implementation-only work.

These package observations remain unaltered. The new review tooling has not been run to create a machine-readable review record.

## Implementation progress since the candidate package was produced

Added, but not executed:

- Candidate review model and read-only package inspection logic in `src/banking_tasci/data/annotation_package_review.py`.
- Explicit approval validation and separate approval-record writing in `src/banking_tasci/data/annotation_approval.py`.
- Identity-only gold freeze preparation and explicit immutable-write controls in `src/banking_tasci/data/gold_sample_freeze.py`.
- Review, approval, and freeze command-line entry points under `scripts/`.
- Calibration guide-freeze and main/final annotation-start gates, batch completion/validation controls, checksum-aware resumption, and atomic checkpoint saving in `annotation_batches.py`.
- Checksum-verified loading of frozen gold-ID artifacts for strict-corpus readiness. This is readiness integration only; it does not build the strict corpus.

Tests were added or modified for review/approval, freeze, workflow gates, and batching transitions. **All tests for this implementation-only session remain `NOT_RUN`.** Static editor diagnostics reported no errors, but that is not test or runtime evidence.

## Test evidence

Last recorded complete-suite result from the prior execution session: **976 passed, 0 failed, 1 skipped, 4 warnings**. Last recorded focused result for sample-plan and batching tests: **60 passed**. Neither result covers the code added in the current implementation-only session. No tests have been run for this report.

## Phase status

- **Phase 2 — source manifests:** documented as complete.
- **Phase 3 — sampling and annotation preparation:** candidate package and batches exist; review found unresolved package concerns. New review/approval gates are implemented but untested. Do not treat researcher approval as complete.
- **Phase 4 — gold freeze and splitting:** blocked. Approval, annotation, and freeze have not occurred. No partitions exist.
- **Phase 5 — strict unlabelled corpus:** blocked pending frozen gold IDs; no corpus was built.
- **Training phases:** not started.

## Required next work

1. Run the unexecuted focused tests for approval, freeze, workflow, batching, and strict-corpus frozen-ID loading; then run the complete suite according to the project's test policy.
2. Review and resolve the issues in `annotation_package_review.md` with the researcher. Do not approve while the report remains `NOT_READY_FOR_RESEARCHER_APPROVAL`.
3. Generate a fresh machine-readable review only after resolving those issues; verify current package and batch checksums.
4. Obtain explicit researcher approval and create the separate approval artifact only if the review is ready.
5. Freeze IDs only in a later, separately authorised action with the required immutable-ID acknowledgement.
6. Do not begin annotation-dependent splitting or strict-corpus materialisation until the relevant human workflow and freeze requirements are satisfied.

## Session constraints and status

This report documents progress only. No tests, generated scripts, approval commands, freeze commands, or training commands were executed while preparing it. The existing annotation package, batch files, protected 796-record intermediate corpus, and all model/data artifacts were left unchanged.

**Status:** `TESTS_NOT_RUN_IMPLEMENTATION_ONLY_SESSION`

---

## Progress update — 14 October 2026

**Session status:** implementation in progress; candidate 2 has not been generated. Candidate 1 remains the current preserved package. No approval, freeze, annotation, split, strict-corpus build, training, or commit has occurred.

### Repository state

- Branch: `main`.
- No commits exist; `git rev-parse HEAD` fails.
- Provenance marker remains `UNKNOWN_NO_COMMIT`.
- Candidate 1 and the protected 796-record intermediate corpus remain untouched.

### Source inspection and evidence found

- The prepared international corpus contains the complete review text in one row per review, with 999 `bank_reviews` rows. It has no populated `thread_id`, no conversation ID, and all context flags are false. The preparation code maps each whole review into one canonical record and assigns its deterministic source `record_id` from the source name and normalized full review text. Therefore no previous-review context should be fabricated; sentence-level context would require a later explicit segmentation step.
- The raw `bank_reviews3.csv` contains `bank`, `bank_image`, `review`, date, title, author, and rating. All 285 rows whose bank is the literal `review` have the generic `ALL_BANKS.png` image; that is not verified bank identity. For the sampled records, the defensible correction is to set bank to null, not infer it from review text.
- The verified materialized South African artifact has 24 records with source `near_dup_group_id` values (11 distinct values). These existing groups can be preserved as evidence; the candidate builder must not recompute them or use positional joins.
- The canonical v2 rule function is `select_v2_candidates()` in `sa_candidates_v2.py`. Selected rule mappings must be keyed and joined by stable `record_id`; missing or duplicate mappings should fail closed.

### Focused test execution

The first focused workflow run executed only the relevant tests and reported **117 passed, 2 failed**:

1. `test_review_build_accepts_complete_static_evidence` — its fixture attempted to create a batch directory that its package helper had already created.
2. `test_main_batch_can_start_after_explicit_guide_freeze` — its fixture marked calibration validated without recording all 50 records complete, correctly tripping the newly added completion guard.

After correcting those two fixtures, the two affected modules were rerun: **15 passed**. This was a focused rerun, not the complete workflow suite. No full-suite run has been made during this progress update.

### Implementation attempted

- Added `candidate_package_v2.py` to enrich candidate 1 selection provenance using a record-ID rule map, recover review bank values from verified raw source fields where available, null the `review`/generic-bank sentinel, create deterministic complete-review IDs, preserve verified SA near-duplicate evidence, derive exact-normalized-text duplicate evidence, and construct namespaced leakage groups.
- Began replacing the previous source-clustered batch placement with explicit per-batch source targets and whole-group-aware balancing. The edit was interrupted while patching `annotation_batches.py`; the current file is **incomplete/corrupted and must be restored before any tests or CLI can be run**. Do not use it to generate batches. Candidate 1 batch files were not regenerated.
- Candidate 2 has **not** been written. No artifact was written under `data/annotations/new_pipeline_v1_candidate_2/`.

### Outstanding defects / next required actions

1. Restore `annotation_batches.py` to a complete importable module, then implement the per-batch source targets and honest deviation reporting without splitting connected groups.
2. Correct the candidate builder: review metadata provenance must be passed explicitly rather than looked up from a per-ID map; bank distribution must include SA and international tweets; preserve existing SA group IDs; assign exact-text groups consistently to all members; and ensure all selected review IDs map uniquely to raw rows using the exact ingestion `make_record_id()` algorithm.
3. Add the source-evidence loading/orchestration and candidate-2 staging CLI, including atomic writes to a new directory, candidate-1 immutability checks, checksums, manifests, lineage, package diff, and static-review JSON/Markdown outputs.
4. Extend focused tests to cover record-ID rule joins under shuffled order, missing/duplicate rule mappings, verified bank correction/nulling, deterministic review IDs, verified grouping, true-context limits, 11 batch targets/deviations, staging isolation, package lineage/diff, and review recommendation gates.
5. Run the complete focused workflow set once when implementation is complete. Run `make test` at most once at the end if credits permit; otherwise report `FULL_SUITE_NOT_RUN_CREDIT_SAVING`.
6. Do not approve or freeze candidate 1 or candidate 2. The latest evidenced static recommendation remains `NOT_READY_FOR_RESEARCHER_APPROVAL`.

### Actions explicitly not taken

- No candidate 1 package, manifests, or batch files changed.
- No candidate 2 artifacts generated.
- No approval or freeze command executed.
- No annotation started, no splits created, no strict unlabelled corpus built, no training launched, and no Git commit created.

**Current result:** candidate-package correction is incomplete; implementation is not yet ready for approval review.
