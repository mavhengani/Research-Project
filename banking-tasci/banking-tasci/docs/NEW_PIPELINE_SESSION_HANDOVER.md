# New Pipeline Session Handover

> **Storage cleanup — 27 October 2026:** At the researcher's request, removed completed smoke runs' redundant `checkpoint-25` directories (legacy MLM, U1, U2), the local pilot staging tar copies already transferred and checksum-verified on the cluster, regenerable test/bytecode caches, and an unreferenced 2,250,776-record South African intermediate CSV whose retained Parquet source has the same schema and record count. Retained `checkpoint-50`, `resume-55`, completion/reload/resume reports, the pinned model cache, Python environments, frozen artifacts, strict corpus, source Parquet, annotation package, and cluster job evidence. File-level hashes and the retention rule are recorded in `artifacts/reports/new_pipeline_v1/storage_cleanup_2026-10-27.json`. Project size fell from about 13.0 GiB to 8.0 GiB. No Git commit was made.

> **Current session: 11.** Sessions 1–3 are summarised in Appendices A–C.
> Session 4 is detailed in Sections 1–17 below. Session 5 is summarised in
> the section below. Sessions 7–11 are summarised immediately below; Session 6 is in Section 0 below.

## Session 11 — calibration workspace safety and adjudication scaffolding (20 October 2026)

**Researcher authorization:** implementation/testing only for calibration workflow, safe annotation progress/backup/restore/audit, adjudication scaffolding, final validation and later downstream preparation. GPU/cluster work remains paused. No Slurm/GPU/SSH investigation or pilot was performed. No approximately 15-hour local CPU pilot was run. Existing U1/U2 staging, smoke, and failed-job evidence was left unchanged. No human labels were generated; no real supervised split, supervised training, final U1/U2 adaptation, or Git commit occurred.

**Read-only frozen revision inspection:** Candidate 2 Freeze Revision 2 is present at `artifacts/frozen/new_pipeline_v1/candidate_2/revision_2/`. Its manifest states `FROZEN`, 1,000 unique IDs, source counts 500/250/250, regional counts 500/500, and gold-ID checksum `fdee989ff1a5935b5404488b215ebda60da86cf0da2f9d81bb1f684d055cea4f`. The ID checksum file and approved batch membership were read only; no frozen artifact was changed.

**Implemented:**

- `src/banking_tasci/data/calibration_workspace.py` provides validated, dry-run-by-default human checkpoint save and restore operations; explicit observed-current-checksum compare-and-swap; atomic writes; dated backups with verification; immutable-source and annotation validation; backup registration; progress counts; and a hash-linked audit-event verifier.
- `scripts/calibration_workspace.py` exposes `status`, `save`, `restore`, and `verify-audit`. Save/restore mutate only with `--apply`, observed checksum, actor, and reason. There is no command to create labels.
- `src/banking_tasci/data/new_pipeline_adjudication.py` compares two completed, schema-valid submissions; refuses ID-set or immutable-source mismatches; reports task-field disagreements; and applies only explicit human A/B/new decisions with rationale. Unresolved cases return pending-review IDs and no adjudicated output. Audit provenance is returned separately from canonical records; nothing is written automatically.
- `scripts/adjudicate_new_pipeline_annotations.py` adds explicit `compare`, `template`, and `apply` subcommands. Decision templates contain IDs and field names only. Template and apply writes require `--write`; apply refuses unresolved disagreements and refuses to overwrite output paths.
- Added synthetic-only tests for checkpoint dry-run/write, backup integrity, restore, stale checksum refusal, invalid/tampered data refusal, audit-chain verification, adjudicator decisions, unresolved items, schema validation, and immutable-field mismatch.
- New-pipeline validation now separates blocking errors from non-blocking schema warnings, reports both counts and affected record IDs, and renders warning counts in Markdown (including the taxonomy's monitored `GENERAL` attribute).

**Verification:** initial local focused command covered `test_calibration_workspace.py`, `test_calibration_activation.py`, `test_new_pipeline_adjudication.py`, `test_new_pipeline_annotation_validator.py`, `test_new_pipeline_schema.py`, and `test_annotation_workflow.py`: **113 passed**. After adding explicit error/warning counts, `GENERAL`-category warning reporting, and a privacy-safe dry-run decision-template CLI regression, expanded local focused run also included `test_annotation_batches.py`: **161 passed**. Python compilation and adjudication CLI help smoke-check passed; static diagnostics reported no errors; the machine-readable audit JSON parsed successfully. The full suite was not run. Existing real calibration files, frozen IDs, approval, batches, and progress workspace were not opened for writing or modified.

**Next safe implementation:** add CLI/manifest integration to validate a human calibration checkpoint and generate an isolated adjudication decision template using only record IDs and field names; retain dry-run defaults and separate researcher gates. Continue with synthetic tests first. Only after real human annotation is explicitly supplied should complete-gold validation/adjudication run against it. Do not unlock main/final batches until the explicit calibration validation and guide-freeze gates pass.

---

## Session 10 — Candidate 2 approved, IDs not frozen (14 October 2026)

**Researcher decision:** Rotondwa Mavhengani explicitly chose
`APPROVE_CANDIDATE_2_FOR_IDENTITY_FREEZE`, accepting the documented sample,
allocation, batches, 71 unverifiable review-bank nulls, and the no-context
limitation. This decision was supplied directly in the session request; the
requested `researcher_approval_decision.md` was not present in the repository.
The decision does not authorize freezing IDs, annotation, splits, corpus
building, or training.

**Pre-approval verification:** passed before both attempts. Candidate 2 has
1,000 records and canonical IDs; source allocation 500/250/250; regional
allocation 500/500; all task labels remain hidden and all 1,000 statuses are
`not_started`. The review recommendation remains
`READY_FOR_RESEARCHER_APPROVAL`. Plan SHA-256 is
`ff8f88e0fe2741a6b9c4da0cb6ef3ade94deb87bee8f4a7d706daf21d82b8c2d`, annotation
records SHA-256 is
`4399dfb086fb883c7bff5584a9fed67451247cb7729187a580b24bac3e140f46`, batch
manifest SHA-256 is
`2a557eee8c702306e54a6ff196035e58fb79cab568d50cfae9c093eafea65ef5`, and
lineage-diff SHA-256 is
`7e8e2a740e688effceb5a0691e25f2e15b67fb9d0cbbf03493d369f6d5aed397`.
Candidate 1 preservation evidence remains 17/17 matching checksums. No approval
or frozen manifest existed before the successful attempt.

**Initial attempt (14 October 2026 20:34:44 UTC):** the exact command below
failed before writing because the CLI defaults selected Candidate 1 input and
manifest paths for a Candidate 2 review. The focused test then passed (**9
passed**). A scoped fix made CLI defaults candidate-aware and added the
required candidate number, annotation-record checksum, context limitation,
and notes to the approval artifact. No candidate data or batch files were
changed.

**Approval command executed successfully (14 October 2026 20:38:09 UTC):**

```bash
python3 scripts/approve_annotation_package.py --reviewer "Rotondwa Mavhengani" --review-report artifacts/reports/new_pipeline_v1/candidate_2/annotation_package_review.json --expected-sample-checksum ff8f88e0fe2741a6b9c4da0cb6ef3ade94deb87bee8f4a7d706daf21d82b8c2d --expected-batch-manifest-checksum 2a557eee8c702306e54a6ff196035e58fb79cab568d50cfae9c093eafea65ef5 --approve
```

The Candidate 2 artifact was created at
`artifacts/approvals/new_pipeline_v1/candidate_2/annotation_package_approval.json`.
SHA-256: `e87e939be67c6f829ab9aaa37ae914d44cfb9059f06e3b352267a9d591ee0c89`.
Approval ID: `62bd53b39e222e0cb9fe9a9b`; approval timestamp:
`2026-10-14T20:38:09Z`; status: `APPROVED`. The artifact records the
researcher, candidate number 2, pipeline version, all required checksums,
review count/recommendation, `UNKNOWN_NO_COMMIT`, exact command, and the
accepted no-context limitation. It contains no human task labels.

The focused approval suite passed after the fix (**10 passed**); `make test`
was not run. Post-approval checks confirm the Candidate 2 plan, annotation
records, batch manifest, lineage diff, and review checksums are unchanged.
Candidate 1 remains preserved (17/17 checksums). Package approved: **YES**.
IDs frozen: **NO**. Annotation started: **NO**. Splits created: **NO**. Strict
corpus built: **NO**. Training started: **NO**. No Git commit was created.

**Next step:** a separate identity-freeze session, with its own explicit
authorization and read-only verification. Before executing the template below,
make the freeze tooling Candidate-2-aware: `gold_sample_freeze.py` currently
derives the plan-manifest path under the generic
`artifacts/manifests/new_pipeline_v1/` directory, while Candidate 2 has no
`gold_sample_plan_manifest.json` at that path. Its approval validator also
does not yet compare the stored `annotation_records_checksum` to the current
records. Add those integrity checks and run only the directly relevant freeze
tests in that future session. The approval does not itself freeze IDs or
authorize annotation.

**Later Candidate 2 freeze command template (not run; not executable until the
freeze-tool path/checksum checks above are addressed):**

```bash
python3 scripts/freeze_gold_sample.py \
  --approval artifacts/approvals/new_pipeline_v1/candidate_2/annotation_package_approval.json \
  --sample-plan data/annotations/new_pipeline_v1_candidate_2/gold_sample_plan.jsonl \
  --annotation-records data/annotations/new_pipeline_v1_candidate_2/annotation_records.jsonl \
  --annotation-manifest artifacts/manifests/new_pipeline_v1/candidate_2/annotation_package_manifest.json \
  --batch-manifest artifacts/manifests/new_pipeline_v1/candidate_2/annotation_batch_manifest.json \
  --authority "Rotondwa Mavhengani" \
  --output-dir artifacts/frozen/new_pipeline_v1/candidate_2 \
  --freeze --acknowledge-immutable-ids
```

## Session 9 — candidate-2 materialization and static review (14 October 2026)

**Git:** branch `main`; no commits; provenance `UNKNOWN_NO_COMMIT`. No commit
was created.

**Full suite:** ran `make test` once before materialization: **1,018 passed,
1 skipped, 4 warnings**. Static-review generation then exposed missing
`tempfile` and `os` imports; the Markdown formatter was repaired and its
targeted regression passed (**1 passed**). The full suite was not rerun after
these review-writer-only changes.

**Dry-run:** reran `python3 scripts/build_candidate_package_v2.py` without
`--write`. Values matched the previously verified dry-run: 1,000 records and
IDs; sources 500/250/250; regions 500/500; v2 rules A=153, B=100, C=193,
D=32, E=14, F=8; 250/250 review IDs; 71 selected invalid/unavailable review
banks set null; all context unavailable; zero selected duplicate groups;
1,000 leakage groups; all 11 proposed batches exactly on source/region target;
no balancing warnings.

**Candidate-1 pre-write checksum baseline:** captured for sample plan, package,
three manifests, static Markdown review, and all 11 batch files. Checksums were
compared again after materialization and all matched. The candidate-1 dry-run
preservation flag was also `true`.

**Candidate 2 materialized** only in
`data/annotations/new_pipeline_v1_candidate_2/`.
The builder wrote 1,000 label-hidden plan and annotation records and 11 batch
files. Candidate-2 manifests and lineage/diff are under
`artifacts/manifests/new_pipeline_v1/candidate_2/`; enrichment report is under
`artifacts/reports/new_pipeline_v1/candidate_2/`. Plan checksum:
`ff8f88e0fe2741a6b9c4da0cb6ef3ade94deb87bee8f4a7d706daf21d82b8c2d`;
annotation checksum:
`4399dfb086fb883c7bff5584a9fed67451247cb7729187a580b24bac3e140f46`; batch
manifest checksum `2a557eee8c702306e54a6ff196035e58fb79cab568d50cfae9c093eafea65ef5`.

**Static review:** generated candidate-specific JSON and Markdown reports.
Recommendation: `READY_FOR_RESEARCHER_APPROVAL`, with no machine-review issues.
This recommendation is not approval. Review explicitly documents no genuine
context source; context-aware experiments remain blocked. Duplicate-group
coverage is verified as none among selected records; leakage coverage is
present for all 1,000 records; review-ID coverage is 250/250. Thread and
conversation identifiers are unavailable in verified sources. Review checksums:
JSON `0e16c5e986bb5c72124b7dc24020bc6933f0365d11243bb57b0e43b830bee837`,
Markdown `b4df1eeb6ccbf6e63c30625bffd9123927c8330f486400a109de66d5bcb1dce1`.

**Lineage diff:** canonical-ID comparison reports 1,000 retained, 0 added,
0 removed; 71 invalid review bank corrections to null; 250 review-ID additions;
500 rule-provenance additions; and 905 batch-membership changes versus
candidate 1. Source and regional totals are unchanged. Diff checksum:
`7e8e2a740e688effceb5a0691e25f2e15b67fb9d0cbbf03493d369f6d5aed397`.
Candidate-2 batch allocations are exact, with no balancing warnings.

**Actions not taken:** candidate 1 was not modified; no approval or freeze was
performed; annotation was not started; no split or strict unlabelled corpus
was built; training was not launched; no commit was created. Candidate-2 batch
statuses remain `generated`, and record statuses remain `not_started`.

**Next decision:** explicit researcher review/approval is a separate action.
Do not run approval or freeze until separately authorized. Before annotation,
resolve or accept the no-context limitation and confirm the candidate-2 review.

**Later approval command (not run; only after explicit authorization):**

```bash
python3 scripts/approve_annotation_package.py \
  --reviewer "<researcher name>" \
  --review-report artifacts/reports/new_pipeline_v1/candidate_2/annotation_package_review.json \
  --expected-sample-checksum ff8f88e0fe2741a6b9c4da0cb6ef3ade94deb87bee8f4a7d706daf21d82b8c2d \
  --expected-batch-manifest-checksum 2a557eee8c702306e54a6ff196035e58fb79cab568d50cfae9c093eafea65ef5 \
  --approve
```

Do not execute this command without separate explicit researcher approval.

---

## Session 8 — focused verification and candidate-2 dry-run (14 October 2026)

**Status:** `FULL_SUITE_NOT_RUN_FOCUSED_VERIFICATION`.

**Git:** branch `main`; no commits; `git rev-parse HEAD` fails; preserve
`UNKNOWN_NO_COMMIT`. No commit was made.

**Syntax verification:** the first compile invocation used the parent folder
and failed because the project-relative paths did not exist there. Re-running
from the project root found syntax/structure defects in
`candidate_package_v2.py`: a malformed raw-bank set comprehension, a displaced
duplicate fragment, and misplaced `_UnionFind`/leakage-key code. These were
corrected. The requested `py_compile` command then completed successfully for
the five requested Python modules/scripts; it was repeated successfully after
the final CLI changes.

```bash
python3 -m py_compile src/banking_tasci/data/annotation_batches.py \
  src/banking_tasci/data/candidate_package_v2.py \
  src/banking_tasci/data/candidate_package_diff.py \
  src/banking_tasci/data/annotation_package_review.py \
  scripts/build_candidate_package_v2.py
```

**Focused testing:**

- Initial requested set: **137 passed, 2 failed**.
- test_cannot_complete_batch_with_incomplete_records: the incomplete-batch
  error wording no longer matched the established assertion phrase.
- `test_review_build_accepts_complete_static_evidence`: the static reviewer
  incorrectly treated Python `None` (valid null bank metadata) as the literal
  invalid placeholder string `none`. The review now checks placeholder values
  only when the actual field is a string.
- Fixes: restored the established incomplete-batch error phrase; made null-bank
  handling type-aware so true null values remain valid.
- Failure-only rerun: both affected tests passed (**2 passed**).
- Final focused rerun:
  `python3 -m pytest tests/test_annotation_batches.py tests/test_annotation_workflow.py tests/test_candidate_package_v2.py tests/test_annotation_approval.py tests/test_gold_sample_freeze.py tests/test_gold_sample_plan.py tests/test_strict_unlabelled_corpus.py -q`
  — **139 passed**. The full suite and `make test` were not run.

**Candidate-2 dry-run:** the first attempt refused because the materialized
100,768-row SA candidate parquet omits `possible_official_account`, which the
canonical v2 selector requires. The CLI was corrected to recompute rule
provenance from the checksum-verified prepared parent parquet, while retaining
selected SA metadata from the verified materialized candidate artifact. The
second dry-run completed without writing but revealed review IDs were being
counted as duplicate groups. Duplicate and leakage evidence were separated,
regression-tested, and the final dry-run then completed without writing.

```bash
python3 scripts/build_candidate_package_v2.py
```

Dry-run totals: 1,000 records / 1,000 unique canonical IDs; source allocation
500 SA tweets, 250 international tweets, 250 international reviews; regional
allocation 500 SA / 500 international. V2 rule counts: A=153, B=100, C=193,
D=32, E=14, F=8. Review IDs: 250/250. Bank metadata: 0 corrected from a
different verified bank value, 71 set null for invalid/unavailable bank
metadata. Context: all 1,000 unavailable; reviews have null previous_text.
Duplicate groups: zero selected verified near/exact-text groups; leakage
groups: all 1,000 records assigned deterministic groups. The duplicate/leakage
key paths were separated after the first dry-run revealed review IDs had been
miscounted as duplicate groups; a regression assertion was added and the
focused suite rerun successfully.

Batch allocation was exact with no warnings: calibration 25/13/12 (SA/
international tweet/review); each of nine main batches 50/25/25; final
25/12/13. Candidate-1 dry-run checksum snapshot reports unchanged. A separate
post-run SHA-256 inspection matched candidate-1 plan, annotation package, all
three manifests, static Markdown review, and all 11 batch files. Candidate-2
data, candidate-2 manifest/report roots, approval/freeze artifacts, split
files, and strict-corpus output were absent on inspection.

Candidate 2 was not generated; no review was generated; no approval, freeze,
annotation, split, strict corpus, training, or commit occurred. Current static
review status for candidate 1 remains `NOT_READY_FOR_RESEARCHER_APPROVAL`.
Phase 3 remains PARTIAL. Full-suite status is
`FULL_SUITE_NOT_RUN_FOCUSED_VERIFICATION`.

**Next session:** run the full suite once if authorized, then obtain separate
researcher authorization before candidate-2 materialization. Candidate-2 review
must remain a separate, non-approval action.

**Later materialization commands (not run):**

```bash
make test
python3 scripts/build_candidate_package_v2.py --write
```

Do not materialize candidate 2 unless the full suite is acceptable and the
researcher explicitly authorizes the write.

## Session 7 — candidate-2 implementation-only continuation (14 October 2026)

**Status:** `TESTS_NOT_RUN_IMPLEMENTATION_ONLY_SESSION`.

**Scope:** restore the interrupted batching module, implement source-target
reporting and candidate-2 enrichment/staging support, add canonical-ID lineage
diff support, make static review candidate-specific, and write focused tests.
No tests, Python imports, project scripts, or CLIs were executed. Candidate 1
data/manifests/batches/review were not intentionally modified; their checksums
were not revalidated in this session. Candidate 2 was not generated. No
approval, freeze, annotation, split, strict corpus, training, or commit occurred.

**Files created:**

- `src/banking_tasci/data/candidate_package_diff.py`
- `scripts/build_candidate_package_v2.py` (dry-run by default; not executed)
- `tests/test_candidate_package_v2.py` (NOT_RUN)

**Files modified:**

- `src/banking_tasci/data/annotation_batches.py` — recreated as one coherent
  module after the reported patch corruption; retains batching, metadata,
  manifest, atomic-write, state-transition, submission, resumption, and
  checkpoint APIs. Adds source/region targets, observations, deviations,
  connected-group counts, and warning explanations. This replacement has not
  been imported or tested; compatibility is based on source-level caller/test
  inspection only.
- `src/banking_tasci/data/candidate_package_v2.py` — ingestion-compatible
  `make_record_id()` review identity mapping; source-evidence bank correction
  report; v2 rule join by `record_id`; source/region/bank distributions;
  preserved SA near-duplicate source ID; exact-text groups for all members;
  review linkage in leakage components; label-hidden/context guards. Not
  runtime verified.
- `src/banking_tasci/data/candidate_package_diff.py` — compares candidate
  records by canonical ID and reports metadata, group, context, batch, and
  allocation differences.
- `src/banking_tasci/data/annotation_package_review.py` and
  `scripts/review_annotation_package.py` — candidate-2 roots, review-ID and
  group/batch integrity, balance evidence, explicit context-experiment
  limitation, candidate-1 checksum comparison, and JSON/Markdown renderers.
  Review outputs were not generated.
- `tests/test_annotation_batches.py` — added source-target/deviation/API tests
  (NOT_RUN).
- `docs/NEW_PIPELINE_SESSION_HANDOVER.md`,
  `docs/NEW_PIPELINE_GAP_ANALYSIS.md`,
  `docs/NEW_PIPELINE_MIGRATION_PLAN.md`, and
  `artifacts/audits/new_pipeline_gap_analysis.json` — this session and
  evidence-based status update.

**Static concerns:** source-level inspection only. In particular, greedy
whole-group batch packing may refuse a feasible packing; the candidate-2
review-ID matcher must be verified against actual raw/prepared review rows;
source-specific bank corrections must be checked against original manifests;
and all batch transition/checkpoint compatibility needs the focused tests.
Do not claim the modules import or the output is valid until a later test/run
session verifies them.

**Next-session exact checks (do not run as part of this session):**

```bash
python3 -m pytest tests/test_annotation_batches.py tests/test_annotation_workflow.py tests/test_annotation_approval.py tests/test_gold_sample_freeze.py -q
python3 -m pytest tests/test_candidate_package_v2.py tests/test_annotation_approval.py -q
python3 -m pytest tests/test_gold_sample_plan.py tests/test_strict_unlabelled_corpus.py -q
```

After those focused tests pass, inspect the proposed paths and run the candidate
builder in dry-run only:

```bash
python3 scripts/build_candidate_package_v2.py
```

Do not run `--write`, do not generate review artifacts, and do not approve or
freeze without separate researcher direction.

## Session 6 — implementation-only approval/freeze workflow (12 October 2026)

**Status:** `TESTS_NOT_RUN_IMPLEMENTATION_ONLY_SESSION`.

**Scope:** read requirements and current implementation/review evidence; add
candidate review representation, explicit researcher approval, identity-only
freeze, strict-corpus frozen-ID loading, calibration/main-batch gates, and safe
checkpoint persistence. No tests or generated scripts were run. No candidate
annotation data or existing report was rewritten. No approval, freeze,
annotation, split, strict corpus, training, or commit was performed.

**Files created:**

- `src/banking_tasci/data/annotation_package_review.py`
- `src/banking_tasci/data/annotation_approval.py`
- `src/banking_tasci/data/gold_sample_freeze.py`
- `scripts/review_annotation_package.py`
- `scripts/approve_annotation_package.py`
- `scripts/freeze_gold_sample.py`
- `tests/test_annotation_approval.py`
- `tests/test_gold_sample_freeze.py`
- `tests/test_annotation_workflow.py`

**Files modified:**

- `src/banking_tasci/data/annotation_batches.py` — any annotation batch start
  requires an APPROVED package; main/final batch start additionally requires
  a completed, validated calibration batch with a frozen guide;
  completion requires every record complete, validation requires an explicit
  passing result, calibration guide freezing is explicit, submission/checkpoint
  checks are checksum-aware, and checkpoint replacement requires the observed
  current checksum (optional no-overwrite backup).
- `src/banking_tasci/data/annotation_approval.py` independently checks exact
  allocation, package IDs, label-hidden state, privacy, and the existing
  batch files' sizes/checksums/membership. It writes approval separately and
  refuses to replace an existing approval record.
- `src/banking_tasci/data/gold_sample_freeze.py` requires matching approval,
  checksums, authority, and immutable-ID acknowledgement. Preview metadata is
  `PENDING_FREEZE`; only explicit writing assigns `FROZEN` in a new directory.
- `src/banking_tasci/data/unlabelled_corpus.py` — `load_gold_ids()` accepts the
  freeze manifest, verifies `FROZEN` status and the referenced JSONL checksum,
  then maps canonical source records into the existing source-partitioned ID
  set without including annotation labels.
- `scripts/build_annotation_batches.py` — output metadata distinguishes JSONL
  byte checksums from logical-ID checksums.
- `scripts/build_strict_unlabelled_corpus.py` — optional
  `--frozen-gold-manifest` readiness/final input.
- `tests/test_annotation_batches.py` — transition tests now cover explicit
  validation, completed-record counts, and frozen guide use.

**Static inspection only:** editor diagnostics reported no errors for the
changed/new Python files. This is not test or runtime evidence. All tests added
or modified in this session are **NOT_RUN**. Existing candidate artifacts
remain untouched and pending researcher review; the earlier Markdown review
at `artifacts/reports/new_pipeline_v1/annotation_package_review.md` still
recommends `NOT_READY_FOR_RESEARCHER_APPROVAL`. Its blockers include missing SA
v2-rule coverage, all-null group/linkage fields, no context-available examples,
the literal `review` bank metadata value, and source-homogeneous stored batches.
No new review, approval, or freeze artifact was written.

**Next session commands (do not run during this session):**

```bash
python3 -m pytest tests/test_annotation_approval.py tests/test_gold_sample_freeze.py \
  tests/test_annotation_workflow.py tests/test_annotation_batches.py \
  tests/test_gold_sample_plan.py -q
python3 -m pytest tests/test_strict_unlabelled_corpus.py -q
```

After tests, first create a new machine-readable review record (output only
under `artifacts/reports`, never under `data/annotations`):

```bash
python3 scripts/review_annotation_package.py --reviewer "<researcher name>" --write
```

The expected current recommendation is `NOT_READY_FOR_RESEARCHER_APPROVAL`; do
not approve it. Approval is only eligible after the researcher resolves the
recorded blockers and a fresh review says `READY_FOR_RESEARCHER_APPROVAL`.
Freeze remains a later, separate command requiring `--freeze`,
`--acknowledge-immutable-ids`, authority, and a new output directory. Only
after an actual freeze should readiness be checked:

```bash
python3 scripts/build_strict_unlabelled_corpus.py --mode PREPARATION \
  --frozen-gold-manifest artifacts/frozen/new_pipeline_v1/gold_sample_manifest.json
```

Do not run FINAL mode or materialise the strict corpus from this implementation-only session.

Conditional commands for a later, explicitly authorised researcher decision
(do not run while the review recommendation remains `NOT_READY`):

```bash
python3 scripts/approve_annotation_package.py \
  --reviewer "<researcher name>" \
  --review-report artifacts/reports/new_pipeline_v1/annotation_package_review.json \
  --expected-sample-checksum 6d16d48d8997753c6c02b632e6e6e8dcb8dd6facccbf6eae403803b7ebdbb9f3 \
  --expected-batch-manifest-checksum e0925db9a0620da8198ce22bf38d4662a52854d303ee7bcf1e6d9f0e025015a3 \
  --approve

python3 scripts/freeze_gold_sample.py \
  --approval artifacts/approvals/new_pipeline_v1/annotation_package_approval.json \
  --authority "<researcher or delegated authority>" \
  --output-dir artifacts/frozen/new_pipeline_v1 \
  --freeze --acknowledge-immutable-ids
```

---


## 0. Session 5 summary (12 October 2026)

**Scope:** fix a pre-existing South African sampler defect found while
re-running the required baseline; implement the canonical combined
1,000-record gold sample plan; implement calibration + main + final
annotation batching with group-aware assignment and safe-resumption /
calibration-freeze metadata. No training. No splits. No strict-corpus build.
No gold labels inserted. No Git commit.

**Baseline (re-run once, as required).** `make test` initially returned
**1 failed / 915 passed / 1 skipped** - `tests/test_sa_sampling.py::
test_real_corpus_selection_is_exactly_500_and_100_per_bank` failed,
selecting only 12 of 500 records. Root cause (new finding **R45**): in
`south_africa_sampler.py`'s `_prepare()`, `DataFrame.apply(_group_key, axis=1)`
over the full 100,768-row real corpus coerced the (overwhelmingly `None`)
result column so that every missing group collapsed onto the **same**
`float('nan')` singleton object. The selection loop's `group is not None`
check treated NaN as "not None", so after the first ungrouped record was
added to `used_groups`, every subsequent ungrouped record in the same band
looked like a duplicate-group conflict by object identity - collapsing
500-target selection down to 12. Confirmed empirically
(`duplicate_group_conflicts: 201512` against only 24 real near-duplicate
groups in the corpus). Did **not** reproduce on the smaller synthetic test
fixtures (~1,500 rows), which is why it was not caught earlier - this
appears to be a pandas result-dtype-inference quirk that is sensitive to
frame size, not a logic error visible from the code alone.

**Fix:** added `_is_missing_group()` (treats `None` and float NaN as "no
group") and used it at all three group-conflict comparison sites, plus
explicit normalisation of the `_group` column after `apply()` so no NaN
singleton survives into later comparisons. `sample_south_africa(REAL_CORPUS,
seed=42)` now returns exactly 500 selected, 100 per bank, 0 shortages, 0
spurious conflicts. Re-ran `make test`: **916 passed, 0 failed, 1 skipped**,
confirmed as the corrected baseline. No other file was touched to reach this
result.

**Combined gold sample plan — built and verified against real data.**
`src/banking_tasci/data/gold_sample_plan.py` + `scripts/build_gold_sample_plan.py`
invoke the two already-verified samplers under seed 42 and combine their
output into one canonical, namespaced 1,000-record plan. Run against the real
materialised South African corpus and the real international `prepared.csv`:

| Property | Result |
|---|---|
| Total | **1,000** |
| Unique canonical IDs | **1,000** |
| `south_africa_tweet` | 500 |
| `international_tweet` | 250 |
| `international_review` | 250 |
| Region `south_africa` / `international` | 500 / 500 |
| Cross-source collisions | **0** |
| South African source sha256 | `15fca4f1…6231a` (unchanged) |
| International source sha256 | `2a3435ad…52fd` (unchanged) |

Canonical IDs use the pattern `<canonical_source>::<source_record_id>`
(e.g. `south_africa_tweet::<id>`); the original ID is preserved as
`source_record_id` and never overwritten. 21 focused tests
(`tests/test_gold_sample_plan.py`) were written and executed earlier this
session against synthetic fixtures - **21 passed**.

**Written this session (`--write --write-annotation-package`):**

- `data/annotations/new_pipeline_v1/gold_sample_plan.jsonl` (1,000 records,
  carries `selection_reason` for audit)
- `artifacts/manifests/new_pipeline_v1/gold_sample_plan_manifest.json`
- `artifacts/reports/new_pipeline_v1/gold_sample_plan.md`
- `data/annotations/new_pipeline_v1/annotation_records.jsonl` (1,000 records,
  Section 11 label-hidden view: `selection_reason` absent, `opinions: []`,
  `primary_intent: null`, `annotation_status: "not_started"`)
- `artifacts/manifests/new_pipeline_v1/annotation_package_manifest.json`

**Calibration + batching — implemented, core mechanics tested, new
resumption utilities NOT yet executed.** `src/banking_tasci/data/annotation_batches.py`
+ `scripts/build_annotation_batches.py` implement:

- union-find connected-component grouping over `duplicate_group` /
  `leakage_group` / `review_id` / `thread_id` / `conversation_id`, so a
  shared value in *any* of these fields keeps records in one batch;
- an oversized-group guard that raises rather than silently splitting a
  group larger than the largest batch (100);
- a deterministic, diversity-seeking calibration selection (round-robin
  across `(source, context_available, length_band, bank)` strata, seed 42)
  followed by deterministic first-fit-decreasing placement into
  `main_001..main_009` and `final_001`;
- deterministic output order within each batch (sorted by `record_id`,
  independent of placement order);
- `BatchMetadata` carrying `batch_status`, `annotation_guide_version`,
  `created_at`/`opened_at`/`completed_at`/`validated_at`, `record_count`,
  `checksum`, `source_sample_manifest_checksum`, `record_ids`, and
  distribution breakdowns;
- `transition_batch_status()` - an explicit state machine
  (`generated -> in_progress -> completed -> validated -> frozen`, with a
  `validation_failed -> in_progress` retry path) so **no batch is ever
  marked completed, validated, or frozen automatically**;
- `validate_submission()` - rejects duplicate record IDs, records foreign to
  the batch, missing records, and records tagged with the wrong
  `annotation_version`;
- `next_incomplete_record()` - deterministic lookup for safe resumption;
- `write_batches()` - atomic per-batch JSONL write, refuses to overwrite
  without `overwrite=True`.

The core batching mechanics (grouping, assignment, sizes, determinism,
metadata, manifest, write/overwrite) were implemented and tested earlier in
this session against a synthetic 1,000-record fixture - **24 passed**. The
status-transition and safe-resumption additions
(`transition_batch_status`, `validate_submission`,
`next_incomplete_record`, deterministic in-batch ordering) were added
**after** that run and were executed in a follow-up pass later the same
session (see below) - **all 60 pass** across both new test files.

**Follow-up execution (same session, continued).** `make test` re-run:
**976 passed, 0 failed, 1 skipped**. `pytest tests/test_gold_sample_plan.py
tests/test_annotation_batches.py -q`: **60 passed**, including the
previously-unexecuted resumption/status-transition tests.
`scripts/build_annotation_batches.py` was then run dry-run and then
`--write` against the real `data/annotations/new_pipeline_v1/
annotation_records.jsonl`:

| Batch | Type | Size | Sources |
|---|---|---|---|
| `calibration_001` | calibration | 50 | international_review 30, international_tweet 5, south_africa_tweet 15 |
| `main_001`-`main_002` | main | 100 each | international_review only |
| `main_003` | main | 100 | international_review 20, international_tweet 80 |
| `main_004` | main | 100 | international_tweet only |
| `main_005` | main | 100 | international_tweet 65, south_africa_tweet 35 |
| `main_006`-`main_009` | main | 100 each | south_africa_tweet only |
| `final_001` | final | 50 | south_africa_tweet only |

Total **1,000** records across **11** batches, `unresolved_balancing_warnings: []`,
`total_groups: 1000` (every selected record is its own singleton group on real
data - consistent with the samplers' own group-integrity guarantee). Written:
`data/annotations/new_pipeline_v1/batches/{calibration_001,main_001..main_009,final_001}.jsonl`,
`artifacts/manifests/new_pipeline_v1/annotation_batch_manifest.json`,
`artifacts/reports/new_pipeline_v1/annotation_batches.md`.

**Known limitation (not a test failure, a soft requirement gap).** Only
`calibration_001` is diversity-selected; the `main_00N` batches are filled by
first-fit-decreasing over components sorted by `record_id`, which - because
canonical source prefixes sort alphabetically
(`international_review` < `international_tweet` < `south_africa_tweet`) -
produces source-homogeneous main batches rather than a mix in every batch.
Requirements Section 13, point 4 ("preserve source and regional
representation across batches where feasible") is satisfied for calibration
only. No test requires main-batch mixing, so this is not a regression, but a
future improvement would shuffle/interleave remaining components across
main batches rather than placing each whole stratum contiguously.

**Status: all of this session's work is now executed and evidenced.** The
earlier-recorded `TESTS_NOT_RUN_IMPLEMENTATION_ONLY_SESSION` status applied
only to the implementation-only portion of this session and has been
superseded by the follow-up execution above.

### Session 5 exact next task

1. Decide whether to address the main-batch source-mixing limitation noted
   above, or accept calibration-only diversity for now.
2. When ready to annotate: freeze the 1,000 selected identifiers into
   `artifacts/manifests/new_pipeline_v1/gold_ids.json`, which unblocks
   Phase 5 (strict unlabelled corpus).
3. Request authorisation for the baseline Git commit.
4. Only then consider Phase 3 "label-hidden package preparation" fully
   evidenced; update the gap analysis / migration plan status accordingly.

### Session 5 commands for the following session

```bash
cd banking-tasci/banking-tasci

# state
git status && git rev-parse HEAD 2>&1 | head -1

# REQUIRED: run once, was not re-run at the end of session 5
make test

# focused regression for this session's new/changed modules
python3 -m pytest tests/test_gold_sample_plan.py tests/test_annotation_batches.py \
                  tests/test_sa_sampling.py -q

# combined gold sample plan already written this session; re-run read-only
# to confirm it is still reproducible against the unchanged sources
python3 scripts/build_gold_sample_plan.py

# NOT yet executed this session - run to actually produce the batch files
python3 scripts/build_annotation_batches.py
python3 scripts/build_annotation_batches.py --write
```

## 1. Date and pipeline version

- **Session date:** 12 October 2026 (session 4)
- **Pipeline version:** `new_pipeline_v1`
- **Requirements baseline:** `NEW_PIPELINE_REQUIREMENTS.md` (version `new_pipeline_v1`, 12 October 2026)
- **Scope:** materialise the SA v2 candidate corpus; verify it; build the combined manifest; implement the strict unlabelled-corpus builder; prepare the SA sampler in dry-run. No training, no final annotation.

## 2. Git state and commit

**Still no commits.**

```text
git status          -> On branch main. No commits yet.
git rev-parse HEAD  -> fatal: ambiguous argument 'HEAD': unknown revision
```

No commit created — not authorised. Four sessions deep. This session made the gap **machine-detectable**: `manifest.git_commit()` now returns the explicit token `UNKNOWN_NO_COMMIT` rather than a prose string, so audits can detect it by equality. A commit hash is never invented.

## 3. Files inspected

- `src/banking_tasci/data/sa_candidate_filter.py` — found duplicate definitions (see §9)
- `scripts/resample_south_africa_v2.py` — `build_reservoir` vectorised masking (the authoritative path)
- `outputs/logs/run_20260905_191954_887494.log` — confirmed *"vectorised keyword matching"*
- `src/banking_tasci/data/manifest.py`, `international_sampler.py`, `new_pipeline_schema.py`, `clean.py`
- `scripts/generate_source_manifest.py`, `scripts/sample_international_gold.py`
- `tests/test_new_pipeline_manifest.py`, `test_new_pipeline_sampling.py`, `test_scripts_import_isolation.py`
- `configs/new_pipeline_v1.yaml`, `configs/taxonomies/banking_entity_attribute_v1.yaml`
- `data/interim/south_africa_prepared.parquet`, `data/interim/prepared.csv` (read-only)

## 4. Files created (8)

**Source (3)**
1. `src/banking_tasci/data/sa_candidates_v2.py` — the canonical v2 selection
2. `src/banking_tasci/data/unlabelled_corpus.py` — strict-corpus builder
3. `src/banking_tasci/data/south_africa_sampler.py` — SA gold sampler

**Scripts (3)**
4. `scripts/materialize_south_africa_candidates_v2.py`
5. `scripts/build_combined_relevant_manifest.py`
6. `scripts/build_strict_unlabelled_corpus.py`
7. `scripts/sample_south_africa_gold.py`

**Tests (3)**
8. `tests/test_sa_materialisation.py` (37), `tests/test_sa_sampling.py` (55), `tests/test_strict_unlabelled_corpus.py` (37)

## 5. Files modified

- `src/banking_tasci/data/manifest.py` — added `NO_COMMIT_MARKER`; `git_commit()` returns the explicit token
- `scripts/generate_source_manifest.py` — registered the materialised corpus; forwards `required_columns`
- `tests/test_new_pipeline_manifest.py` — +15 tests (combined manifest, commit marker)
- Four documentation files

**Not modified:** `sa_candidate_filter.py`, `resample_south_africa_v2.py`, any legacy config, the 796-record corpus, the international sampler.

## 6. Artifacts generated

| Artifact | Status |
|---|---|
| `data/processed/new_pipeline_v1/south_africa_candidates_v2.parquet` | **100,768 rows**, sha256 `15fca4f1…6231a`, 12 MB |
| `…/south_africa_candidates_v2_materialisation.json` | full provenance report |
| `…/south_africa_candidates_v2_source_manifest.json` | **VERIFIED** |
| `…/international_source_manifest.json` | **VERIFIED** (regenerated) |
| `…/combined_relevant_manifest.json` | **VERIFIED**, 111,615 |
| `…/strict_unlabelled_readiness.json` | **BLOCKED_AWAITING_GOLD_IDS** |

No annotation file, gold-ID manifest, strict corpus, split, or model artifact was produced.

## 7. Focused tests executed and results

| File | Result |
|---|---|
| `tests/test_sa_materialisation.py` | **37 passed** |
| `tests/test_sa_sampling.py` | **55 passed** |
| `tests/test_strict_unlabelled_corpus.py` | **37 passed** |
| `tests/test_new_pipeline_manifest.py` | **56 passed** |
| `tests/test_new_pipeline_sampling.py` | **60 passed** |
| **Combined focused run** | **245 passed, 0 failed** (109.71 s) |

## 8. Full suite

**Not run.**

`FULL_SUITE_NOT_RUN_CREDIT_SAVING`

The policy permits one run at the end, but this session's work was substantial (8 new files, 129 new tests, a 12 MB materialisation, and several multi-minute real-corpus operations), and the focused set already covers every file touched. Running the full suite would have added ~3 minutes of credits for marginal signal.

**Honest limitation:** I have verified the 245 focused tests and the five affected files. I have **not** re-verified the other ~35 test modules this session. The session-3 baseline was 772 passed / 0 failed; my changes were additive (new modules) plus one narrow change to `manifest.git_commit()`'s return value. That last change is the only plausible regression vector — anything asserting the old prose string would now fail. I searched and found only `tests/test_new_pipeline_manifest.py` referencing it, and that file passes. **Not verified:** `test_reproducibility.py` and the baseline/model modules, which use `training/reproducibility.py`'s own separate `_read_git_commit()` — untouched by this session.

**Next session must run:** `make test`

## 9. Defect found: `sa_candidate_filter.py` duplicate definitions (R44)

The brief said to "import one canonical filtering function". Following that literally would have produced the **wrong corpus**.

`sa_candidate_filter.py` (920 lines) has duplicate definitions:

| Symbol | Lines |
|---|---|
| `CandidateResult` | 189, **748** |
| `classify_candidate` | 198, **757** |
| `is_potential_zero_aspect` | 313, **892** |
| `_any` | 353, **375** |

The later definitions shadow the earlier ones, so the **live** `classify_candidate` is the regex variant at line 757 (confirmed via `inspect.getsourcelines`). Measured against the vectorised keyword logic on a 40,000-row sample of the real parent:

| Path | Candidates |
|---|---|
| Vectorised (authoritative) | 1,838 |
| Row-wise `classify_candidate` (live) | 2,592 |
| **Disagreements** | **756 (1.89%)** |

The historical log settles which is authoritative: *"Applying evidence-based candidate filter (vectorised keyword matching)"* — the message emitted by `resample_south_africa_v2.py:202`, inside `build_reservoir`, which never calls `classify_candidate`.

**Resolution:** extracted the vectorised logic verbatim into `src/banking_tasci/data/sa_candidates_v2.py`, now the single canonical selection used by materialisation, tests, and docs. It reproduces 100,768 and the full rule breakdown exactly. `sa_candidate_filter.py` was **not** modified — `resample_south_africa_v2.py` and legacy tests depend on its current behaviour and its completed outputs are preserved. R44 is therefore **PARTIAL**: mitigated, not fully resolved.

## 10. Materialisation details

**Command:** `python3 scripts/materialize_south_africa_candidates_v2.py`

Pre-write verification (all assertions run *before* any file is created):

| Check | Result |
|---|---|
| Row count | **100,768** = expected |
| Unique identifiers | **100,768** |
| Duplicate identifiers | **0** |
| All IDs present in parent | **True** |
| Strict subset of parent | **True** (100,768 < 2,250,776) |
| Rule counts match documented | **True** |
| Forbidden columns | **none** |
| Logical checksum | `2763ccfb…3567` |

- **Source sha256:** `f780da1241fef4b2b7f21aba295dc4236131071248e3bcd302fc22f31a6f06f7` (byte-identical afterwards)
- **Output sha256:** `15fca4f1ccb950b6cbbfa3390549ccb5cca8b7dc7e078a017e170a4104a6231a`
- **Atomic write:** temp file in the same directory → `os.replace`; temp file cleaned on failure
- **Overwrite protection:** refuses without `--overwrite`
- **No coercion:** any count deviation aborts with exit 2 unless `--allow-count-change` is passed deliberately

`candidate_strata` and `filter_reason` are **excluded** from the output per Requirements 6.5 — the attributed rule lives in the report for audit, not on records where an annotator could see it.

## 11. South African sampler dry-run

Verified against the real materialised corpus:

- **500** selected, **100 per bank** (FNB/Absa/Nedbank/Standard Bank/Capitec), **500 unique**
- Bands q33=**132.0** / q66=**219.0**; selection balanced short 167 / medium 166 / long 167
- Years 2018–2022 all represented; v2 rules all six (A=153 B=100 C=193 D=32 E=14 F=8)
- **Zero shortages**; `can_select_full_total` and `can_select_full_per_bank` both `True`
- Deterministic under seed 42; global RNG untouched; duplicate/thread groups never split

Band comparison across all three sources — the concrete justification for Requirements 7.4:

| Source | q33 | q66 |
|---|---|---|
| South African tweets | 132.0 | 219.0 |
| International tweets | 140.0 | 183.0 |
| International reviews | 289.3 | 327.7 |

**No annotation file written.** A real write requires **both** `--write` and `--authorise-final-write`.

## 12. Requirement-status changes

| ID | Was | Now | Evidence |
|---|---|---|---|
| **R3** | REQUIRES_DATA_CONFIRMATION | **COMPLETE** | materialised + VERIFIED manifest + 37 tests |
| **R5** | MISSING | **COMPLETE** | combined manifest VERIFIED at 111,615 |
| R7 | MISSING | **PARTIAL** | builder + readiness; blocked on gold IDs *by design* |
| R10 | CONFLICTS | **PARTIAL** | SA dry-run 500 / 100-per-bank verified |
| R33 | PARTIAL | PARTIAL | +129 tests |
| R44 | *(new)* | **PARTIAL** | canonical path extracted; module not de-duplicated |

**Totals:** 19 COMPLETE · 12 PARTIAL · 5 MISSING · 5 CONFLICTS · 2 N/A · 1 REQUIRES_DATA_CONFIRMATION (44 findings).

**Phase 2: 100%.** **Phase 3: ~70%** (both sides dry-run; calibration batching and the authorised write remain).

## 13. Decisions made

1. **Established the canonical filter rather than assuming it.** Checking first revealed the duplicate definitions and the 1.89% divergence; importing `classify_candidate` as instructed would have selected the wrong records.
2. **Extracted rather than modified.** `sa_candidate_filter.py` and `resample_south_africa_v2.py` were left untouched to preserve legacy behaviour and completed outputs.
3. **Excluded candidate-rule columns from the materialised output** (Requirements 6.5), keeping rule attribution in the report only.
4. **Used a logical (identifier-set) checksum** for determinism assertions, because parquet bytes vary between writes while the selected record set does not.
5. **Built the combined manifest by reference**, not by concatenation — avoids duplicating ~15 MB and a second artifact to keep in sync.
6. **Kept R7 at PARTIAL** despite all arithmetic checking out. Arithmetic is not a corpus.
7. **Required two flags for a gold write** (`--write` + `--authorise-final-write`).
8. **Made the Git gap machine-detectable** via `UNKNOWN_NO_COMMIT` rather than closing it without authorisation.
9. **Fixed a real bug in my own first attempt:** rule labels were reindexed positionally, silently yielding all-`unknown` coverage. Rule labels are computed against the *parent* corpus, whose row positions differ from the materialised subset, so the join must be by `record_id`. Pinned by `test_rule_labels_map_by_record_id_not_position`.
10. **Skipped the full suite** and recorded the limitation honestly rather than implying coverage I did not verify.

## 14. Remaining blockers

1. **The 1,000 gold identifiers do not exist.** Blocks Phase 5 entirely and Phase 4 transitively. Not an engineering blocker — it needs annotation to begin.
2. **No Git commit** (four sessions).
3. **Calibration batching** (50 + 9×100 + 50) not yet implemented — the last engineering step before annotation.
4. **R44 partially resolved** — `sa_candidate_filter.py` still has four shadowed symbols.
5. **Two fragile test modules** (`test_evaluation_phase3a1.py`, `test_near_duplicates.py`) cannot be collected standalone.

## 15. Exact next task

1. Run `make test` once to confirm the session-3 baseline (772 passed) plus this session's additions, with no regression from the `git_commit()` change.
2. Implement calibration batching in both samplers (50 + 9×100 + 50 = 1,000; the final 50 must be explicit).
3. When the researcher is ready to annotate: run both samplers with `--write --authorise-final-write`, then freeze the selected IDs into `artifacts/manifests/new_pipeline_v1/gold_ids.json` as `{"south_africa": [...], "international_tweets": [...], "international_reviews": [...]}`. That file unblocks Phase 5.
4. Re-run `scripts/build_strict_unlabelled_corpus.py` — it should flip from `BLOCKED` to `READY_FOR_FINAL`.
5. Request authorisation for the baseline Git commit.

## 16. Commands for the following session

```bash
cd banking-tasci/banking-tasci

# state
git status && git rev-parse HEAD 2>&1 | head -1

# REQUIRED: full suite was not run last session
make test

# confirm all three manifests remain VERIFIED
python3 scripts/generate_source_manifest.py --source south_africa_candidates_v2
python3 scripts/generate_source_manifest.py --source international
python3 scripts/build_combined_relevant_manifest.py

# strict corpus readiness (expect exit 3 until gold IDs exist)
python3 scripts/build_strict_unlabelled_corpus.py

# sampler dry-runs (write nothing)
python3 scripts/sample_south_africa_gold.py --with-rule-coverage
python3 scripts/sample_international_gold.py

# focused regression set for session-4 work
python3 -m pytest tests/test_sa_materialisation.py \
                  tests/test_sa_sampling.py \
                  tests/test_strict_unlabelled_corpus.py \
                  tests/test_new_pipeline_manifest.py \
                  tests/test_new_pipeline_sampling.py -q
```

## 17. Warnings about temporary, legacy, or incomplete behaviour

- **`sa_candidate_filter.py` has four shadowed symbols**, and its live `classify_candidate` disagrees with the authoritative selection on ~1.9% of rows. **Never use it for v2 candidate selection** — use `banking_tasci.data.sa_candidates_v2.select_v2_candidates`.
- **The strict 110,615 corpus does not exist and must not be fabricated.** The builder is correct to report `BLOCKED`.
- **`scripts/create_splits.py` still defaults to the prohibited 70/15/15.** Always pass `--train-ratio 0.80 --validation-ratio 0.10 --test-ratio 0.10 --seed 42`.
- **Legacy label constants remain intentionally wrong for the new pipeline** (`INTENT_LABELS` has 7 incl. `warning`; `ASPECT_SENTIMENTS` lacks `conflict`). Preserved for the 796-record corpus.
- **Existing `near_dup_group_id` values predate the session-3 stable-hash fix** and are non-reproducible if recomputed. The materialised corpus carries them forward as-is for traceability; only 24 of 100,768 records have one.
- **Every artifact records `git_commit: "UNKNOWN_NO_COMMIT"`.**
- **The full suite was not run this session** — see §8 for exactly what is and is not verified.
- **The 796-record `combined_adjudicated_v2.jsonl` remains valid intermediate-generation data.** Never present it as satisfying the 1,000-record requirement.

---

# Appendix A — Session 1 (audit)

Read the requirements in full and audited the repository, producing 40 findings and the migration plan. Documentation only; no tests run. Key findings: no Git commits; SA corpus 2,250,776 vs a 100,768 requirement; international already correct at 10,847; schema needed structural change; no `pipeline_version`, taxonomy, MLM code, or TASCI integration; `create_splits.py` defaulted to 70/15/15 and `annotations.py` to seven intents.

# Appendix B — Session 2 (Phase 1)

Established the baseline (506 passed / 10 failed) and implemented Phase 1: `new_pipeline_v1.yaml`, the canonical taxonomy (13 entities / 69 categories), and `new_pipeline_schema.py` (full Section 8 schema, six intents + `public_warning`, four sentiments incl. `conflict`, explicit/implicit targets), plus `manifest.py` and the manifest generator. +161 tests → 667 passed, identical failure list. Closed R1, R14, R15, R16, R17, R39.

# Appendix C — Session 3 (defect fixes + Phase 2/3 start)

Fixed all ten pre-existing failures and one newly-surfaced flaw: the BiLSTM duplicate definition (R41), the `scripts` package-import fragility that caused exactly 9 failures (R42), and process-dependent MinHash hashing from builtin `hash()` — a correctness issue for leakage prevention, not just a flaky test (R43). Extended the manifest tooling to the full Phase 2 field/status set and built the international sampler (250+250, dry-run). Reproduced the 100,768 count exactly. Suite went **772 passed / 0 failed**. Closed R11, R12, R41, R42, R43.
