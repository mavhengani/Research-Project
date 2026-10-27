# Banking TASCI `new_pipeline_v1` Candidate 2 Progress

**Date:** 14 October 2026  
**Git:** branch `main`, no commit; provenance marker `UNKNOWN_NO_COMMIT`  
**Current recommendation for candidate 1:** `NOT_READY_FOR_RESEARCHER_APPROVAL`

## Summary

Candidate 2 has **not been generated**. Candidate 1 remains the persisted,
unchanged package. This progress report records focused test findings and
source inspection performed while attempting the correction. No approval,
freeze, annotation, split, strict unlabelled-corpus construction, model
training, or commit was performed.

## Focused testing

The initial focused workflow run covered approval, freeze, workflow, batching,
sample-plan, and strict-corpus tests. Result: **117 passed, 2 failed**.

The failures were test-fixture defects, not confirmed implementation failures:

1. `test_review_build_accepts_complete_static_evidence` tried to create the
	 batch directory a second time; its package fixture had already created it.
2. `test_main_batch_can_start_after_explicit_guide_freeze` marked calibration
	 validated while leaving its completed-record count at zero, correctly
	 violating the all-records-complete gate.

After correcting those fixtures, the two affected test modules were rerun:
**15 passed**. The full focused set has **not** been rerun after subsequent
candidate-2 and batching edits. No full-suite run was performed.

## Source evidence inspected

- The prepared international corpus has 10,847 records, including 999
	`bank_reviews` rows. Each review is a complete review text in one row.
- The raw `bank_reviews3.csv` has source fields `bank`, `bank_image`, `review`,
	date, title, author, and rating. All 285 rows whose bank is the literal
	`review` use the generic `ALL_BANKS.png` image. That image does not verify a
	specific bank; candidate 2 must set the bank to null rather than infer one
	from review text.
- The prepared reviews have no populated `thread_id`, no conversation ID, and
	all context flags are false. No review-internal context was carried into the
	prepared row. Do not fabricate context; review sentence segmentation would
	be a separate, provenance-preserving preparation stage.
- The materialized South African candidate file has 100,768 records and 24
	non-null `near_dup_group_id` values covering 11 distinct group IDs. Preserve
	these verified group values for selected records; do not recompute or join
	them positionally.
- South African rule provenance must come from `select_v2_candidates()` and
	be joined by stable `record_id`. Missing or duplicated mappings must fail
	closed.

## Implementation state — 14 October implementation-only continuation

The previously suspect batching module has been recreated as one coherent
source file, with the inspected script/test caller API retained. It now
contains deterministic whole-group assignment, canonical source quotas,
observed source/region distributions, deviations, per-batch group counts,
balancing explanations, status/resumption/checkpoint controls, and atomic
batch writes. **No import or test was executed**, so public API compatibility
and runtime behavior remain unverified.

Candidate-2 implementation support now includes:

- `candidate_package_v2.py`: stable-ID rule mapping through
	`select_v2_candidates()`, exact ingestion `make_record_id()` review identity,
	evidence-only bank correction/nulling, verified SA near-duplicate IDs,
	full exact-text duplicate membership, namespaced leakage groups, source and
	region counts, label-hidden projection, and no-context enforcement.
- `candidate_package_diff.py`: candidate comparison by canonical `record_id`,
	including metadata, grouping, context, batch, and allocation differences.
- `scripts/build_candidate_package_v2.py`: dry-run by default; write path fixed
	to candidate-2-only directories; candidate-1 checksum snapshots; atomic
	staging; source checksums/manifests; batch artifacts; lineage and diff.
- Static review tooling accepts candidate-specific paths, checks batch and
	group integrity, context limitations, and candidate-1 artifact checksums;
	candidate-2 JSON/Markdown review outputs are implemented but were not
	generated.
- Focused batching, enrichment, diff, CLI safety, and static-review tests were
	added or extended. All remain **NOT_RUN**.

Editor/language-server diagnostics reported no errors in changed Python files,
docs, or the JSON audit. This is static evidence only, not syntax/import/test or
runtime verification. Candidate 1 checksum snapshots were not executed or
verified in this session.

## Candidate 1 preservation

Candidate 1 artifacts were not intentionally modified during this work. Their
existing checksums and contents have not been revalidated after the attempted
implementation. Do not overwrite or regenerate them. Candidate 2 must use the
separate path `data/annotations/new_pipeline_v1_candidate_2/`, with its own
manifests and reports under candidate-specific subdirectories.

## Required next actions

1. Run focused tests in the next execution-authorized session for batching,
	approval/workflow, candidate-2 enrichment, diff, and static-review tooling.
2. Fix any test/runtime findings before using either builder. Inspect and run
	the candidate-2 builder in dry-run mode only after the focused tests pass.
3. Candidate-2 `--write` is a separate, later action; do not generate candidate
	2 without explicit authorization. Candidate 1 remains the preserved parent.
4. Keep approval, freeze, annotation, splits, strict corpus, and training
	blocked; no candidate-2 review should auto-approve or freeze anything.

## Explicitly not done

- Candidate 2 was not generated.
- Candidate 1 was not intentionally overwritten or regenerated.
- No approval or freeze was performed.
- No annotation, split, strict corpus, or training was started.
- No Git commit was created.

**Session 7 result:** candidate correction remained incomplete. Candidate 1 was
still `NOT_READY_FOR_RESEARCHER_APPROVAL`. Session status at that point:
`TESTS_NOT_RUN_IMPLEMENTATION_ONLY_SESSION`; the later Session 8 update below
supersedes its verification status.

---

## Verification update — 14 October 2026

**Session status:** `FULL_SUITE_NOT_RUN_FOCUSED_VERIFICATION`.

- Git was rechecked: branch `main`, no commits; `UNKNOWN_NO_COMMIT` remains the
	provenance marker.
- The requested compile check succeeded after fixing a malformed raw-bank
	comprehension, displaced duplicate code, a misplaced `_UnionFind` class,
	and an indentation defect in leakage-key propagation.
- Initial focused run: **137 passed, 2 failed**. One was a batch error-message
	compatibility mismatch; the other incorrectly treated actual null bank
	values as the invalid string placeholder `none`. Both defects were fixed.
- The first candidate-2 dry-run exposed that the materialized SA candidate
	source lacks `possible_official_account`; rule provenance now uses the
	checksum-verified prepared parent source. A later dry-run exposed review IDs
	being mistaken for duplicate groups; duplicate and leakage evidence were
	separated and regression-tested.
- Final focused run: **139 passed** across the requested seven modules.
- Candidate-2 dry-run: 1,000/1,000 unique records; source 500/250/250 and
	region 500/500; v2 rules A=153, B=100, C=193, D=32, E=14, F=8; 250/250
	review IDs; 71 invalid review-bank values set null; zero selected duplicate
	groups; all 1,000 records receive leakage groups; context unavailable for
	all records; exact 11-batch targets with no warnings.
- Candidate-1 checksum snapshot and independent post-run SHA-256 inspection
	matched its plan, annotation file, manifests, static review, and 11 batches.
- Candidate-2 output roots remain absent; no review, approval, freeze,
	annotation, split, strict corpus, or training artifact was created. Candidate
	1 remains `NOT_READY_FOR_RESEARCHER_APPROVAL`.

The complete suite was not run. Candidate 2 remains ungenerated and unapproved;
Phase 3 remains partial.

---

## Candidate-2 materialization and static review — 14 October 2026

The complete suite was run once before writing candidate 2: **1,018 passed,
1 skipped, 4 warnings**. After that suite run, the Markdown review writer's
missing `tempfile` and `os` imports were fixed; its focused regression passed
(**1 passed**). The complete suite was not rerun after that small fix.

Candidate 2 was materialized under
`data/annotations/new_pipeline_v1_candidate_2/`. It has 1,000 records and 1,000
unique canonical IDs, source allocation 500/250/250, regional allocation
500/500, and v2 rule distribution A=153, B=100, C=193, D=32, E=14, F=8. The
selected review bank sentinel was set null for 71 records; no bank was replaced
from a different valid raw source bank value. All 250 reviews have deterministic
review IDs. There are no selected verified duplicate-group members; all 1,000
records have distinct leakage groups. All context flags are false; complete
reviews retain null `previous_text`.

Eleven batch files were written: calibration 50, nine main batches of 100,
final 50. Each batch matches the source and region targets exactly; balancing
warnings are empty. The package diff compares by canonical ID and records
1,000 retained IDs, zero additions, zero removals, 71 bank-null corrections,
250 review-ID additions, 500 rule-provenance additions, and changed batch
membership. Candidate-2 package checksums are plan
`ff8f88e0fe2741a6b9c4da0cb6ef3ade94deb87bee8f4a7d706daf21d82b8c2d`, annotation
`4399dfb086fb883c7bff5584a9fed67451247cb7729187a580b24bac3e140f46`, and batch
manifest `2a557eee8c702306e54a6ff196035e58fb79cab568d50cfae9c093eafea65ef5`.

Candidate-2 review files:

- `artifacts/reports/new_pipeline_v1/candidate_2/annotation_package_review.json`
- `artifacts/reports/new_pipeline_v1/candidate_2/annotation_package_review.md`

**Recommendation:** `READY_FOR_RESEARCHER_APPROVAL`, with no automated review
issues. This is not approval. The review explicitly records context-aware
experiments as blocked pending a genuine linked-context dataset. Candidate 1
remains `NOT_READY_FOR_RESEARCHER_APPROVAL`; its sample, package, manifests,
review, and 11 batch checksums all match the pre-write baseline. No approval,
freeze, annotation, split, strict corpus, training, or commit occurred.

R19 is now COMPLETE for implemented batching and candidate-2 package
preparation. Phase 3 remains PARTIAL because the new-schema annotation
validator gap (R20) and researcher/human annotation workflow remain unresolved.
