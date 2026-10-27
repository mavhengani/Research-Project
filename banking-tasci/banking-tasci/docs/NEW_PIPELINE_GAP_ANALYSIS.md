# New Pipeline Gap Analysis (`new_pipeline_v1`)

> **Authoritative current state — 20 October 2026:** U1/U2 smoke execution is complete. CUDA pilot submission is unavailable because the one permitted cluster authentication check failed. The local CPU route passes storage and checkpoint checks but is not execution-ready until an awake, powered, uninterrupted 12.9–16.1 hour window is confirmed and pilot resume CLI support is completed. The approved 50-record Candidate 2 calibration workspace is `in_progress` at 0/50; no labels were generated. Historical gap statements below remain for provenance and do not override this header.

> ## Session 16 note (14 October 2026) — compatible MLM interpreter unavailable
>
> The host has only Python 3.14.5 and no available Python 3.11/3.12 or local
> interpreter manager. The pinned compatible dependency specification and MLM
> execution modes are prepared, but model-dependent gates remain blocked. No
> modelling dependency or base model was installed or downloaded.

> ## Session 15 note (14 October 2026) — MLM implementation gate is model-blocked
>
> MLM validate-only configuration and entry point now verify the strict corpus
> identity, checksum, count, and gold exclusion without loading a model. The
> requested model-backed gates cannot run because the macOS Python 3.14
> environment has no PyTorch/Transformers stack or cached `bert-base-uncased`.
> Focused tests passed **96**. No model, checkpoint, smoke run, pilot, or
> annotation action was created.

> ## Session 14 note (14 October 2026) — Strict corpus ready, MLM gated
>
> The strict unlabelled corpus was materialised with 110,615 records after
> exclusion of all 1,000 Revision-2 frozen IDs. Its checksum, exclusion report,
> and privacy report are recorded under the strict-corpus manifest directory.
> Only `record_id` and `text` remain. The MLM scaffold validates the immutable
> corpus but has training disabled and does not initialise a model. Focused
> strict-corpus/freeze/configuration tests passed **103**; full suite was not run.

> ## Session 13 note (14 October 2026) — Freeze Revision 2 resolves provenance gap
>
> Candidate 2 Revision 2 preserves the original frozen identity projection and
> its SHA-256, while adding approval ID, approved batch membership, verified
> source-manifest references, original-freeze provenance, and strict-corpus
> count expectations. Focused freeze/readiness tests passed **44**. Readiness
> is `READY_FOR_FINAL` when assessed with the three verified source manifests.
> No strict corpus or later-stage artifact was created.

> ## Session 12 note (14 October 2026) — frozen identity artifact has a provenance gap
>
> The authorised Candidate 2 identity freeze wrote four immutable files and its
> `gold_record_ids.jsonl` checksum matches the approved dry-run projection.
> Candidate 1 and Candidate 2 source artifacts remain checksum-preserved.
> The frozen manifest omits the approval ID and approved batch-membership
> reference required for the frozen identity schema. It was not repaired or
> overwritten. Strict-corpus readiness remains blocked because no verified source
> manifests were supplied alongside the valid frozen ID manifest.

> ## Session 11 note (14 October 2026) — Candidate 2 freeze-ready, not frozen
>
> Candidate-aware freeze lookup and full approval/sample/annotation/batch/review
> checksum validation are now implemented. Focused approval, freeze, and
> strict-corpus tests passed **54**. The Candidate 2 dry-run verified all supplied
> checksums, 1,000 unique records, source 500/250/250, regions 500/500, and the
> deterministic proposed gold-ID SHA-256
> `fdee989ff1a5935b5404488b215ebda60da86cf0da2f9d81bb1f684d055cea4f`.
> No frozen artifact was written. Strict corpus remains
> `BLOCKED_AWAITING_FROZEN_GOLD_IDS`; annotation, splits, corpus construction,
> training, and Git commit remain unperformed.

> ## Session 10 note (14 October 2026) — Candidate 2 approved, not frozen
>
> Researcher Rotondwa Mavhengani explicitly selected
> `APPROVE_CANDIDATE_2_FOR_IDENTITY_FREEZE`. Read-only checks confirmed 1,000
> records/IDs, source 500/250/250, region 500/500, hidden labels, `not_started`
> statuses, expected plan/annotation/batch/lineage checksums, and
> `READY_FOR_RESEARCHER_APPROVAL`. The initial CLI attempt failed because its
> defaults selected Candidate 1; scoped fixes made the CLI candidate-aware and
> added candidate number, annotation-record checksum, exact command, and the
> accepted no-context limitation to the approval record. The prescribed command
> then succeeded at 2026-10-14T20:38:09Z. Approval artifact:
> `artifacts/approvals/new_pipeline_v1/candidate_2/annotation_package_approval.json`,
> SHA-256 `e87e939be67c6f829ab9aaa37ae914d44cfb9059f06e3b352267a9d591ee0c89`;
> status `APPROVED`. Focused approval tests: **9 passed** before the fix and
> **10 passed** after; full suite not run. Candidate 1 preservation remained
> 17/17 checksums, and Candidate 2 package checksums were unchanged. IDs frozen:
> **NO**; annotation/splits/strict corpus/training: **NO**. The requested
> decision report file was absent; the explicit decision in the session request
> was used. Next: a separate identity-freeze session with explicit
> authorization. Before that, the freeze helper must resolve Candidate 2's plan
> manifest rather than the generic Candidate 1 path and validate the approval's
> annotation-record checksum against current records. The displayed freeze
> template is not yet executable. See the Session 10 handover entry for details.

> ## Session 9 note (14 October 2026) — candidate 2 materialized and reviewed
>
> `make test` ran once before materialization: **1,018 passed, 1 skipped, 4
> warnings**. Candidate 2 was written only to candidate-specific paths. Its
> 1,000 unique records satisfy 500/250/250 source allocation and 500/500
> regions; rule counts are A=153, B=100, C=193, D=32, E=14, F=8; all 250
> reviews have deterministic IDs; 71 invalid/unavailable review bank values
> are null; no selected duplicate groups were evidenced; all records have
> leakage groups; context is unavailable for all 1,000. Eleven batches meet
> exact source and region quotas with no warnings. The canonical-ID diff shows
> 1,000 retained, 0 added, 0 removed. Candidate-1 package, manifests, static
> review, and all 11 batch checksums match the pre-write baseline. Static
> review recommends `READY_FOR_RESEARCHER_APPROVAL` but does not approve.
> No approval, freeze, annotation, split, strict corpus, training, or commit
> occurred. R19 is COMPLETE; Phase 3 remains PARTIAL due R20 validator work and
> subsequent researcher/human workflow. A report-writer import fix after the
> full-suite run passed its focused regression; the full suite was not rerun.

> ## Session 9 note (14 October 2026) — candidate 2 materialized and reviewed
>
> Git remains branch `main`, no commit, provenance `UNKNOWN_NO_COMMIT`. The
> complete suite ran once before materialization: **1,018 passed, 1 skipped,
> 4 warnings**. Afterwards, a missing-import defect in the candidate-2 Markdown
> review writer was fixed and its targeted regression passed; the full suite
> was not rerun. Candidate-2 dry-run matched the expected counts/quotas.
> Candidate 2 was then materialized only at its candidate-specific path, with
> 1,000 records, 1,000 unique IDs, 11 batches, verified manifests/checksums,
> canonical-ID lineage/diff, and candidate-specific static review. The review
> recommendation is `READY_FOR_RESEARCHER_APPROVAL`, not approval. Candidate-1
> plan/package/manifests/review/all 11 batches match their pre-write SHA-256
> baseline. No approval, freeze, annotation, split, strict corpus, training,
> or commit occurred. R19 is now COMPLETE for implemented/tested calibration
> batching and candidate package preparation. Phase 3 remains PARTIAL because
> annotation validation (R20), researcher decision/approval, and human
> annotation are incomplete. Context-aware experiments remain blocked pending
> a genuine, provenance-linked context dataset.

> ## Session 8 note (14 October 2026) — focused verification and dry-run
>
> Git state was rechecked: branch `main`, no commits, `UNKNOWN_NO_COMMIT`.
> The requested `py_compile` verification ultimately succeeded after repairing
> a malformed bank-row comprehension and displaced fragments in
> `candidate_package_v2.py`. The initial focused set reported 137 passed / 2
> failed; both defects were corrected (legacy batch error-message contract and
> null bank handling), and a final focused rerun reported **139 passed** across
> batching, workflow, candidate, approval, freeze, plan, and strict-corpus
> tests. `make test` was not run.
>
> Candidate-2 dry-run first exposed that the materialized SA candidate parquet
> intentionally lacks `possible_official_account`. Rule provenance now reads
> the checksum-verified prepared parent; selected SA metadata still comes from
> the verified materialized candidate source. A second dry-run completed
> without writing. It reported 1,000 unique IDs (500/250/250; 500/500 regions),
> all six rules (A=153, B=100, C=193, D=32, E=14, F=8), review IDs 250/250,
> 71 invalid review-bank values set null, no verified duplicate groups among
> selected IDs, leakage groups for all records, context false for all 1,000,
> exact target allocations in all 11 proposed batches, and no balancing
> warnings. Candidate-1 package, manifests, review, and batch checksums matched
> a separate post-run SHA-256 inspection. Candidate 2, review outputs,
> approval, freeze, annotation, splits, strict corpus, training, and commit were
> not created. **R19 remains PARTIAL and Phase 3 is not complete**; the dry-run
> is not a materialized package or researcher review.

> ## Session 7 note (14 October 2026) — candidate-2 implementation only, NOT_RUN
>
> Restored `annotation_batches.py` as a coherent single-definition module and
> added explicit source/region target, observed, deviation, group-count, and
> warning fields. Implemented candidate-2 enrichment with record-ID rule
> provenance, ingestion-compatible review identity, verified bank metadata
> handling, source-evidenced grouping, candidate-specific static review,
> canonical-ID diff/lineage, and a dry-run-by-default candidate-2 staging CLI.
> Focused tests were written but **NOT_RUN**. No Python imports, scripts, CLIs,
> review generation, or data generation were executed. Candidate 1 was not
> intentionally changed; its checksums were not revalidated. Candidate 2 does
> not exist. Approval, freeze, annotation, splits, strict corpus, training, and
> commit did not occur. Because the recreated batching implementation and new
> candidate-2 code have no runtime evidence, **R19 remains PARTIAL** and Phase
> 3 remains incomplete; use a provisional, evidence-based estimate of **70%**
> until the focused tests and later authorized dry-run provide executable
> evidence. Context-aware experiments remain blocked by the verified absence
> of preceding context; no synthetic context is permitted.

> ## Session 6 note (12 October 2026) — approval/freeze workflow implemented, NOT_RUN
>
> Added `annotation_package_review.py`, `annotation_approval.py`, and `gold_sample_freeze.py`, plus review/approval/freeze CLIs. Approval and freeze are separate explicit actions; dry-run approval reports `NOT_APPROVED`, and freeze preview reports `PENDING_FREEZE`. Freeze emits identity/provenance fields only and does not write annotation labels. Batch transitions now gate main/final work on an approved package plus a fully completed, validated, explicitly guide-frozen calibration batch. Checkpoint writes require record membership/version validation, current-checksum acknowledgement for replacement, atomic replacement, and optional backup. Frozen-ID loading was connected to strict-corpus readiness without building that corpus.
>
> **No tests or generated scripts were run.** New and modified tests are `NOT_RUN`; static editor diagnostics reported no errors. Existing requirement statuses are intentionally unchanged pending test evidence. The current candidate package review remains `NOT_READY_FOR_RESEARCHER_APPROVAL`; no approval, freeze, annotation, split, strict corpus, training, or commit occurred. See the Session 6 section in `docs/NEW_PIPELINE_SESSION_HANDOVER.md` for files and next-session test commands.

> ## Session 5 headline (12 October 2026) — combined gold sample plan built; batching implemented
>
> **New finding R45 (fixed): South African sampler NaN-identity group-collision bug.** Re-running the required baseline (`make test`) surfaced one failure: the real-corpus integration test expected 500 selected / 100 per bank and got 12. Root cause: `south_africa_sampler.py`'s `_prepare()` builds `_group` via `DataFrame.apply(_group_key, axis=1)`; over the full 100,768-row real corpus this coerced the (almost entirely `None`) result column so every missing group collapsed onto the **same shared `float('nan')` object**. The conflict check (`group is not None and group in used_groups`) treated NaN as "not None", so after the first ungrouped record was accepted, every later ungrouped record in the same band looked like it collided with an already-used group **by object identity** — `duplicate_group_conflicts` measured **201,512** against only 24 genuine near-duplicate groups in the whole corpus. Did not reproduce on the ~1,500-row synthetic test fixtures, which is why it was not caught earlier. Fixed with an explicit `_is_missing_group()` helper (treats `None` and float NaN as "no group") applied at the column-normalisation step and all three comparison sites. Re-verified: `sample_south_africa(REAL_CORPUS, seed=42)` now returns exactly 500, 100 per bank, 0 shortages. `make test` baseline corrected: **916 passed, 0 failed, 1 skipped**.
>
> **The combined 1,000-record gold sample plan is built and verified against real data** (`src/banking_tasci/data/gold_sample_plan.py` + `scripts/build_gold_sample_plan.py`): 500 `south_africa_tweet` + 250 `international_tweet` + 250 `international_review`, 500 south_africa / 500 international, 1,000 unique namespaced IDs, 0 cross-source collisions, both source checksums unchanged. Written: `gold_sample_plan.jsonl`, `annotation_records.jsonl` (Section 11 label-hidden view), and both manifests.
>
> **Calibration + batching is implemented** (`src/banking_tasci/data/annotation_batches.py` + `scripts/build_annotation_batches.py`): union-find group-aware assignment into `calibration_001` (50) + `main_001..main_009` (100 each) + `final_001` (50) = 1,000, deterministic diversity-seeking calibration selection, deterministic in-batch ordering, and explicit calibration-freeze status transitions (`generated -> in_progress -> completed -> validated -> frozen`) so no batch is ever marked complete automatically. Core mechanics tested (24/24 passing against a synthetic fixture). The newer safe-resumption additions (`validate_submission`, `next_incomplete_record`) and their tests were written after that run and have **not yet been executed** — see `docs/NEW_PIPELINE_SESSION_HANDOVER.md` Section 0 for the exact pending commands. The batching script has **not yet been run against the real annotation package**; no batch files exist on disk yet.

> ## Session 4 headline (12 October 2026) — Phase 2 COMPLETE
>
> **R3 is CLOSED.** The South African corpus is no longer "reproducible in principle" — it is a materialised, checksummed, manifest-verified artifact:
>
> | | |
> |---|---|
> | Path | `data/processed/new_pipeline_v1/south_africa_candidates_v2.parquet` |
> | Rows | **100,768** (= expected) |
> | Unique IDs / duplicates | **100,768 / 0** |
> | Parent relationship | **strict subset** (100,768 < 2,250,776), every ID present |
> | Rule counts | C=38,185 A=33,360 B=18,428 D=6,380 E=2,880 F=1,535 → **sum 100,768** |
> | Output sha256 | `15fca4f1…6231a` |
> | Manifest status | **VERIFIED**, all 20 required fields populated |
>
> **The combined corpus is VERIFIED**: 100,768 + 10,847 = **111,615** exactly, built *by reference* to the two immutable source manifests, with measured raw identifier overlap of **0**.
>
> ### A defect that would have silently produced the wrong corpus (new finding R44)
>
> The brief said to "import one canonical filtering function". Following that naively would have been wrong. `sa_candidate_filter.py` turns out to carry **duplicate definitions** — the same defect class as R41:
>
> | Symbol | Lines |
> |---|---|
> | `CandidateResult` | 189, **748** |
> | `classify_candidate` | 198, **757** |
> | `is_potential_zero_aspect` | 313, **892** |
> | `_any` | 353, **375** |
>
> The *live* `classify_candidate` is the regex variant at line 757, and it **disagrees with the authoritative vectorised selection on 756 of 40,000 sampled rows (1.89%)** — it is more permissive. The historical log confirms the authoritative path: *"Applying evidence-based candidate filter (vectorised keyword matching)"*.
>
> Had materialisation imported `classify_candidate`, it would have selected a different record set and **not** reproduced 100,768. The count assertion would have caught it, but the lesson stands: "one canonical function" had to be *established*, not assumed. The vectorised logic was extracted verbatim into `src/banking_tasci/data/sa_candidates_v2.py`, which now reproduces the count and full rule breakdown exactly.
>
> ### What is deliberately still incomplete
>
> - **Strict unlabelled corpus (110,615) → PARTIAL, not COMPLETE.** All five arithmetic identities check out and all three manifests are VERIFIED, but the 1,000 gold identifiers do not exist, so the corpus **cannot** be built. The builder correctly reports `BLOCKED` (exit 3). Arithmetic alone must never mark this complete.
> - **South African sampler → PARTIAL.** Dry-run selects exactly 500 / 100-per-bank with zero shortages, but no annotation file was written; a real write requires **both** `--write` and `--authorise-final-write`.

> ## Session 3 headline (12 October 2026)
>
> **The test suite is now fully green: 772 passed, 0 failed, 1 skipped** (baseline was 667 passed / 10 failed).
>
> **The 100,768-record question is answered.** The figure is the documented output of the **v2 evidence-based candidate filter** — not an unexplained number and never a fabrication risk. A read-only re-execution of that filter against the parquet this session produced **exactly 100,768 candidates, 100,768 unique identifiers, 0 duplicates**, with a per-rule breakdown reproducing the September 2026 run log digit for digit (C=38,185 · A=33,360 · B=18,428 · D=6,380 · E=2,880 · F=1,535, sum **100,768**). `docs/south_africa_filter_history.md` had recorded all along that 100,768 is the **v2** pool while 2,086,851 is the superseded **v1** broad catch-all, and warns they must not be presented as two measurements of the same filter. R3 stays `REQUIRES_DATA_CONFIRMATION` for one narrow reason only: the selection is reproducible but **not yet materialised as its own checksummed artifact**.
>
> **Three repository defects were found and fixed** (new findings R41–R43), one of which was a genuine correctness issue, not just a flaky test:
>
> | | Defect | Why it mattered |
> |---|---|---|
> | R41 | `_write_bilstm_posthoc_artifacts` defined **twice**; the later shadowing definition added an unused `model` parameter, so the 8-arg call site left `splits` unfilled | BiLSTM CLI could not complete; no posthoc artifacts |
> | R42 | `tests/test_south_africa_resampling.py` had **exactly 9** `from scripts...` imports — matching the **exactly 9** failures — but `scripts/__init__.py` does not exist and only `src/` was on `sys.path` | 9 order-dependent failures made the suite useless as a gate |
> | R43 | `clean.py:_shingle` used builtin `hash()`, which Python **randomises per process** | Near-duplicate grouping was **non-reproducible**, undermining leakage prevention (Requirements 15.2) — masked by luck, not introduced by this work |

**Audit date:** 12 October 2026 (session 1)
**Last updated:** 12 October 2026 (session 3 — Phase 2 tooling complete, Phase 3 international sampler built, suite green)
**Requirements baseline:** `NEW_PIPELINE_REQUIREMENTS.md` (document version `new_pipeline_v1`, last updated 12 October 2026)
**Companion machine-readable report:** `artifacts/audits/new_pipeline_gap_analysis.json` (40 findings, same requirement IDs as this document)

**Session 1 scope:** read-only audit. No code modified.
**Session 2 scope:** executable baseline established, Phase 1 (configuration, taxonomy, schema) implemented, Phase 2 manifest tooling prepared. 161 tests added. No legacy file modified — checksums re-verified. No training launched. Nothing deleted.

---

## 0. Session 2 status change summary

Eleven findings were re-evaluated against new executable evidence. Status changed only where a passing test or a generated artifact backs it.

| ID | Area | Was | Now |
|---|---|---|---|
| R1 | Pipeline versioning | COMPLETE *(session 2)* | **COMPLETE** |
| R13 | Annotation record/opinion schema | CONFLICTS | **PARTIAL** |
| R14 | Explicit/implicit target support | COMPLETE *(session 2)* | **COMPLETE** |
| R15 | Canonical entity-attribute taxonomy | COMPLETE *(session 2)* | **COMPLETE** |
| R16 | Sentiment labels (incl. `conflict`) | CONFLICTS | **COMPLETE** |
| R17 | Communicative-intent taxonomy | CONFLICTS | **COMPLETE** |
| R39 | Canonical `new_pipeline_v1.yaml` | MISSING | **COMPLETE** |
| R3 | South African candidate count | CONFLICTS | **REQUIRES_DATA_CONFIRMATION** |
| R4 | International corpus count | COMPLETE | COMPLETE (now manifest-backed) |
| R33 | Test coverage | PARTIAL | PARTIAL (substantially advanced) |
| R2 | Git provenance | MISSING | MISSING (unchanged, not authorised) |

**Totals moved from** 7 COMPLETE · 8 PARTIAL · 11 MISSING · 9 CONFLICTS · 3 N/A · 2 CONFIRM
**to** 12 COMPLETE · 10 PARTIAL · 8 MISSING · 6 CONFLICTS · 2 N/A · 2 CONFIRM.

R3's move from `CONFLICTS_WITH_NEW_REQUIREMENT` to `REQUIRES_DATA_CONFIRMATION` is a deliberate refinement, not a downgrade: the conflict is unchanged in substance, but it is no longer *undetected*. Tooling now exists that detects and reports it on every run, so it is a documented open data question rather than a silent discrepancy.

### Test-suite trajectory across sessions

| Point | Passed | Failed | Skipped |
|---|---|---|---|
| Session 1 baseline (pre-Phase 1) | 506 | 10 | 1 |
| Session 2 (after Phase 1) | 667 | 10 | 1 |
| **Session 3 (after defect fixes + Phase 2/3)** | **772** | **0** | **1** |

Session 2 recorded the 10 failures as two groups and deferred both as out of Phase 1 scope. Session 3 diagnosed and fixed both, plus a third latent flaw that surfaced once the first two stopped masking the suite:

- **9 × `test_south_africa_resampling.py`** — *not* shared-state mutation as session 2 hypothesised. The module has **exactly 9** `from scripts.resample_south_africa_v2 import ...` statements, matching the 9 failures precisely. `scripts/__init__.py` does not exist, so `scripts` resolves only while the **project root** is on `sys.path`, yet the module inserted only `src/`. Reproduced directly: with only `src` on the path the import raises `ModuleNotFoundError: No module named 'scripts'`. Fixed by inserting the project root explicitly, exactly as the module already did for `src/`. **The resampling implementation was not modified.** (Finding R42.)
- **1 × `test_cli_bilstm_intent_end_to_end`** — `_write_bilstm_posthoc_artifacts` was defined **twice** in `baseline_runner.py` (lines 339 and 376). The later definition shadowed the earlier one and added a leading `model` parameter it never used, so the 8-argument call at line 319 bound `splits` into `metrics` and left `splits` unfilled. The duplicate also dropped `cluster_job_metadata.json` and used an O(n²) scan where the original used an O(n) dict lookup. Removed the duplicate; kept the definition matching the call site. (Finding R41.)
- **1 × `test_near_duplicates.py::test_detect_near_identical_texts_flagged`** — surfaced *after* the above fixes and was **not** in the baseline 10. Initially it looked like an import problem (the module cannot be collected standalone), but the real cause was `clean.py:_shingle` using builtin `hash()`, which Python randomises per process. The same test passed and failed across identical consecutive runs (pass/fail/fail/pass); with `PYTHONHASHSEED` pinned it passed 4/4. Replaced with a blake2b-based `_stable_hash`: 6/6 stable unpinned. **This was a correctness issue, not cosmetics** — near-duplicate grouping underpins leakage prevention, and the module's docstring already promised determinism it did not deliver. (Finding R43.)

A note on attribution: the full suite went green immediately after the BiLSTM fix, before the import fix landed. That was coincidence — `test_south_africa_resampling.py` sorts *before* `test_train_baselines_cli.py`, so a change to the latter cannot fix the former. The import fragility was diagnosed and fixed on its own evidence rather than being assumed resolved.

---

## 1. Audit method

Every finding below is backed by one of: a direct file read, a `grep`/`pyarrow` query executed during this session, or an explicit cross-reference to a prior session's own audit document (which is itself treated as evidence of the repository's state at that time, not as evidence of new-requirements conformance). Where a prior session's finding could not be independently re-verified against a live file, it is marked `REQUIRES_DATA_CONFIRMATION` rather than asserted as fact.

Status values used (per Section 29 of the requirements document):

| Status | Meaning |
|---|---|
| `COMPLETE` | Implemented, evidenced, and matches the new requirement exactly |
| `PARTIAL` | Some real implementation exists but does not fully satisfy the requirement |
| `MISSING` | No implementation or artifact exists at all |
| `CONFLICTS_WITH_NEW_REQUIREMENT` | A live default, constant, or artifact actively contradicts the new requirement (not just a historical mention) |
| `NOT_APPLICABLE` | Cannot be evaluated yet because a prerequisite is missing |
| `REQUIRES_DATA_CONFIRMATION` | Needs a researcher decision or external data before it can be classified |

## 2. Git and repository state

```text
git status  -> On branch main. No commits yet.
git rev-parse HEAD -> fatal: ambiguous argument 'HEAD': unknown revision
```

**There are no commits in this repository.** The entire `banking-tasci/` tree, this requirements document, and every supporting file are untracked. This is itself the most consequential single finding of the audit: Section 25's reproducibility requirement (Git commit hash recorded per run) cannot be satisfied by any run — past, present, or future — until an initial commit exists. Every `git_commit.txt` artifact already written by `src/banking_tasci/training/reproducibility.py` reads `"unknown (not a git repository)"`.

`docs/git_repository_audit_25sept.md`, a prior session's own audit, independently reached the same conclusion in September.

## 3. Headline findings

### 3.1 Dataset counts: a genuine, verified conflict — not a documentation error

The new requirements document (Section 4.1) specifies a South African starting corpus of **100,768** customer-feedback candidate records. The repository's actual prepared data is **2,250,776** records.

This was verified three independent ways during this audit:

1. Direct `pyarrow` read of `data/interim/south_africa_prepared.parquet`: `num_rows == 2250776`.
2. `outputs/south_africa_data_report.json`: `"rows_after_all_filters": 2250776`.
3. `outputs/revised_pipeline_source_inventory.json` and `outputs/revised_pipeline_source_verification.json`: both independently record `"rows": 2250776` for the same file, with matching SHA-256 checksums.

I also tested whether the 100,768 figure might already be hiding inside the parquet under an existing boolean flag:

- `customer_feedback_candidate == True` → **2,086,851** rows (not 100,768)
- `customer_feedback_candidate == True` AND NOT `likely_promotional` AND NOT `possible_official_account` → **2,033,936** rows (not 100,768)

Neither matches. `outputs/south_africa_candidates_v2_validation.json` independently confirms that `data/interim/south_africa_candidates_v2.parquet` — a file name that looks like it should hold exactly this narrower candidate set — **does not exist on disk**.

**Conclusion:** the 100,768-record South African corpus is a genuinely new target, not an already-computed-but-mislabelled quantity. It requires either a new, stricter filter to be designed and run, or researcher confirmation that this count was produced outside this repository and needs to be imported. See Finding R3.

The **international corpus count is already correct and checksummed**: `data/interim/prepared.csv` has exactly 10,847 rows, confirmed in three independent reports with a matching SHA-256 (`2a3435ad...`). No action needed there.

### 3.2 Three historical generations of counts and splits are layered in this repository

Reading the prior audit documents (`docs/revised_pipeline_implementation_audit.md`, `docs/tasci_implementation_gap_analysis.md`, `docs/project_status_25_september_2026.md`) alongside the live code revealed that this repository has already passed through two earlier requirements generations that were never fully executed:

| Generation | Gold total | Split | Intent labels | Status |
|---|---|---|---|---|
| Legacy (original) | ~600 international + partial SA | 70/15/15 | 7 incl. `warning` | Partially executed; live code defaults still reflect this generation |
| Intermediate (documented Sept 2026) | 796 (600 intl + 196 SA), target 496 | 348/75/73 (planned) | not revised | 796-record gold exists; 496 target never built |
| **New (`new_pipeline_v1`, this audit)** | **1,000** (500 SA + 250 + 250) | **80/10/10** | **6 + separate `public_warning`** | Not yet started |

None of the three has fully matching code, data, and documentation at the same time. The practical implication: **do not delete or relabel anything from generations 1 or 2** — `data/annotations/combined_adjudicated_v2.jsonl`, the `combined_v2`/`south_african_v2` manifests, and the completed SVM run directories are all generation-2 artifacts that remain scientifically valid for whatever they already measured. New work must land under clearly new, distinctly-named paths.

### 3.3 The annotation schema itself needs to change shape, not just its label lists

`src/banking_tasci/data/annotations.py`'s `AnnotationRecord`/`AspectSpan` dataclasses are the single source of truth consumed by every annotation-pipeline tool (sampler, validator, splitter, BIO converter). Reading them directly against Section 8 of the requirements shows the gap is structural, not cosmetic:

- The required list is named `opinions`; the code has `aspects`.
- Required opinion-level fields `target`, `target_start`, `target_end`, `target_type`, `entity`, `attribute`, `opinion_phrase`, `opinion_start`, `opinion_end` do not exist. The code has `term`, `start`, `end`, `category`, `sentiment` only — a single explicit span, no entity/attribute split, no implicit-target representation at all.
- Required record-level fields `bank`, `review_id`, `thread_id`, `conversation_id`, `publish_year`, `duplicate_group`, `leakage_group`, `privacy_status`, `primary_intent`, `public_warning`, `annotation_version`, `annotation_notes` do not exist.

This is the single most consequential gap in the repository, because almost every other finding in Sections 9–15 traces back to it. See Finding R13.

### 3.4 What is already strong and directly reusable

Three things in this repository are genuinely solid, already tested, and should **not** be rewritten:

- **`src/banking_tasci/data/context.py`** — correctly implements genuine-context/`[NO_CONTEXT]` handling exactly as Section 12 requires, including an explicit, verified guard against ever using the previous physical CSV row as context (the Section 27 anti-pattern). No gap.
- **`src/banking_tasci/data/bio.py`** — a clean, tokenizer-agnostic BIO conversion module with full round-trip verification. No gap in the data-layer logic (the model that consumes it is a separate, missing piece — see R27).
- **`scripts/create_splits.py`'s grouping/allocation engine** — `group_key()` and `assign_groups_to_splits()` are a pure, seeded, deterministic, group-aware stratified splitter with a hard "refuse to run on invalid input" precondition. The only wrong thing about this script is its **default ratios** (0.70/0.15/0.15, explicitly prohibited by Section 27) and its **output file set** (missing the required `.jsonl`/leakage-report/Markdown files) — the splitting algorithm itself is correct and should be reused as-is with corrected arguments.
- **`src/banking_tasci/data/anonymise.py`** — identifier removal is implemented, tested, and evidenced with real measured counts on 2.25M real records (email: 6,275; URL: 682,609; mention: 3,971,875; etc.). No gap.
- **`src/banking_tasci/training/reproducibility.py`** — the artifact-writing infrastructure (immutable run directories, per-artifact graceful failure, environment capture) is sound and should be extended (to add `pipeline_version`, checksums, `taxonomy_version`) rather than replaced.

### 3.5 What is entirely missing

> **Session 2 update:** the first, second, and fifth bullets below are now **resolved**. `configs/new_pipeline_v1.yaml`, `configs/taxonomies/banking_entity_attribute_v1.yaml` (13 entities / 69 categories), and `src/banking_tasci/data/new_pipeline_schema.py` all exist and are covered by 161 passing tests. The MLM and TASCI bullets remain accurate and unaddressed.

- ~~No `pipeline_version` marker anywhere~~ → **resolved session 2** (R1 COMPLETE).
- ~~No canonical entity-attribute taxonomy file~~ → **resolved session 2** (R15 COMPLETE). The legacy nine-value flat `ASPECT_CATEGORIES` still exists in `annotations.py` but is now explicitly scoped to legacy data only, and the new schema actively rejects flat categories (`test_legacy_flat_category_is_rejected`).
- **No masked-language-model / domain-adaptation code at all** — no MLM dataset class, no masking policy, no MLM training loop. `bert_baseline.py` is a supervised-head consumer of an already-pretrained checkpoint, not an adaptation trainer. *(Still accurate.)*
- **No TASCI integration** — no self-attention aspect extractor, no GRU contextual intent model, no GloVe loader, no intent-projection/fusion module, no TASCI-specific sentiment head, no end-to-end inference pipeline (`src/banking_tasci/inference/` is an empty stub package). *(Still accurate.)*
- ~~`configs/new_pipeline_v1.yaml` does not exist~~ → **resolved session 2** (R39 COMPLETE).

### 3.6 What directly conflicts with explicitly prohibited legacy behaviours (Section 27)

Two prohibited behaviours are not just mentioned in old prose — they are the **live, operative defaults** in current code today:

1. **70/15/15 splits**: `scripts/create_splits.py` defines `DEFAULT_TRAIN_RATIO = 0.70`, `DEFAULT_VALIDATION_RATIO = 0.15`, `DEFAULT_TEST_RATIO = 0.15`. Anyone running this script without explicit `--train-ratio`/`--validation-ratio`/`--test-ratio` flags today gets the prohibited split.
2. **Seven primary intents including `warning`**: `src/banking_tasci/data/annotations.py`'s `INTENT_LABELS` and `configs/intent.yaml`'s `intent.labels` both independently enumerate `['complaint', 'compliment', 'request_for_assistance', 'suggestion', 'warning', 'churn_signal', 'general_feedback']` — seven labels, with `warning` as a primary class rather than the required separate `public_warning` boolean.

Neither of these needs new engineering to fix the symptom (both scripts/configs already accept explicit overrides or could have their label lists edited) — but both need the fix to happen inside the correctly-scoped new-schema/new-config work (R13, R17, R21) rather than as an isolated patch, since downstream code depends on these exact values.

> **Session 2 update.** Both legacy behaviours are **still present in the legacy code paths, deliberately and by design** — `create_splits.py` still defaults to 70/15/15 and `annotations.py` still lists seven intents, because the 796-record intermediate corpus depends on them. What changed is that correct alternatives now exist alongside them and are enforced for `new_pipeline_v1`:
>
> - **Split ratios:** `configs/new_pipeline_v1.yaml` declares 0.80/0.10/0.10, asserted by `test_split_ratios_are_80_10_10` and guarded by `test_split_is_not_the_prohibited_70_15_15`. The legacy default is unchanged, so **every `new_pipeline_v1` invocation must still pass the ratios explicitly** until a Phase 4 wrapper pins them.
> - **Intent taxonomy:** the new schema's `PRIMARY_INTENTS` has exactly six values with `warning` absent, and the validator rejects `primary_intent="warning"` with guidance pointing at `public_warning`. Legacy `INTENT_LABELS` is untouched and verified untouched by `test_legacy_annotation_constants_are_unchanged`.
>
> R21/R35 therefore remain `CONFLICTS_WITH_NEW_REQUIREMENT`: the prohibited default still exists in the shared script, and that is the honest status until Phase 4 removes the risk of silent omission.

---

## 4. Findings table (summary)

Full detail, evidence, file paths, and recommended actions for every finding are in `artifacts/audits/new_pipeline_gap_analysis.json`. Summary:

| ID | Area | Status |
|---|---|---|
| R1 | Pipeline versioning | COMPLETE *(session 2)* |
| R2 | Git provenance | MISSING |
| R3 | South African candidate count (100,768) | **COMPLETE** *(session 4: materialised + VERIFIED manifest)* |
| R4 | International corpus count (10,847) | COMPLETE *(session 2: manifest-backed)* |
| R5 | Combined relevant corpus (111,615) | **COMPLETE** *(session 4: VERIFIED by reference)* |
| R6 | Gold annotation corpus count (1,000 / 500+250+250) | CONFLICTS_WITH_NEW_REQUIREMENT |
| R7 | Strict unlabelled corpus (110,615) | PARTIAL *(session 4: builder + readiness; BLOCKED on gold IDs by design)* |
| R8 | South African data-prep evidence (dedup/clean/privacy) | PARTIAL |
| R9 | Candidate rules are not task labels | COMPLETE |
| R10 | Gold sampling counts and bank/strata allocation | PARTIAL *(session 4: SA dry-run 500 / 100-per-bank verified)* |
| R11 | Source-specific quantile length bands | COMPLETE *(session 3)* |
| R12 | Sampler output completeness (checksum, shortages) | COMPLETE *(session 3, international)* |
| R13 | Annotation record/opinion schema (Section 8) | PARTIAL *(session 2: new schema exists; consumers not migrated)* |
| R14 | Explicit/implicit target support | COMPLETE *(session 2)* |
| R15 | Canonical entity-attribute taxonomy | COMPLETE *(session 2)* |
| R16 | Sentiment labels (incl. `conflict`) | COMPLETE *(session 2)* |
| R17 | Communicative-intent taxonomy (6 + `public_warning` flag) | COMPLETE *(session 2)* |
| R18 | Context handling (`[NO_CONTEXT]`, genuine linkage) | COMPLETE |
| R19 | Calibration (50) + batching (50+900+50) | **COMPLETE** *(session 9: full suite 1,018 passed/1 skipped; candidate 2 materialized, 11 exact source-balanced batches/checksums, static review READY; no approval/freeze)* |
| R20 | Annotation validator checks (Section 14) | PARTIAL |
| R21 | Gold-corpus split ratios (80/10/10 vs live 70/15/15) | CONFLICTS_WITH_NEW_REQUIREMENT |
| R22 | Group-aware leakage splitting logic | COMPLETE |
| R23 | Split output file set (`.jsonl`, leakage report, etc.) | PARTIAL |
| R24 | MLM corpus exclusions | NOT_APPLICABLE (no corpus exists yet) |
| R25 | Domain-adaptation MLM training | MISSING |
| R26 | BIO target-extraction data layer | COMPLETE |
| R27 | Self-attention aspect-extractor model | MISSING |
| R28 | Entity-attribute category prediction model | MISSING |
| R29 | Intent classification conditions (GRU + baselines) | PARTIAL |
| R30 | Sentiment conditions and TASCI fusion | PARTIAL |
| R31 | Baseline families overall (SVM/BiLSTM/BERT/adapted/TASCI) | PARTIAL |
| R32 | Reproducibility writer | PARTIAL |
| R33 | Required test coverage (Section 32) | PARTIAL *(session 4: +129; 245 focused passing)* |
| R34 | Ethics/privacy anonymisation | COMPLETE |
| R35 | Prohibited legacy split ratio (duplicate of R21) | CONFLICTS_WITH_NEW_REQUIREMENT |
| R36 | Prohibited seven intents (duplicate of R17) | CONFLICTS_WITH_NEW_REQUIREMENT |
| R37 | Prohibited legacy counts / three generations | CONFLICTS_WITH_NEW_REQUIREMENT |
| R38 | Cohen's Kappa / single-annotator provenance | REQUIRES_DATA_CONFIRMATION |
| R39 | Canonical `configs/new_pipeline_v1.yaml` | COMPLETE *(session 2)* |
| R40 | Makefile entry points | NOT_APPLICABLE |

Session 3 added three repository-defect findings:

| ID | Area | Status |
|---|---|---|
| R41 | BiLSTM posthoc duplicate definition | COMPLETE *(session 3)* |
| R42 | `scripts` package-import fragility | COMPLETE *(session 3)* |
| R43 | Process-dependent MinHash hashing | COMPLETE *(session 3)* |
| R44 | `sa_candidate_filter` duplicate definitions | PARTIAL *(session 4: canonical path extracted; module not yet de-duplicated)* |

Session 5 added one repository-defect finding and moved R19:

| ID | Area | Status |
|---|---|---|
| R45 | South African sampler NaN-identity group-collision bug | COMPLETE *(session 5: fixed, re-verified against real 100,768-record corpus)* |

**Totals (session 9, 45 findings):** 21 COMPLETE · 12 PARTIAL · 4 MISSING · 5 CONFLICTS_WITH_NEW_REQUIREMENT · 2 NOT_APPLICABLE · 1 REQUIRES_DATA_CONFIRMATION. R19 advanced to COMPLETE based on the full-suite result, materialized batches, and static review. R20 remains PARTIAL; Phase 3 is not wholly complete.

*(Session 3 was 17 · 9 · 7 · 6 · 2 · 2 over 43 findings; session 2 was 12 · 10 · 8 · 6 · 2 · 2; session 1 baseline was 7 · 8 · 11 · 9 · 3 · 2.)*

---

## 5. Questions requiring researcher input before implementation proceeds

1. **How should the 100,768-record South African candidate corpus be produced?** No existing filter or flag combination in the current 2,250,776-row parquet produces this count. Options: (a) design and run a new, stricter candidate filter with full audit evidence; (b) confirm the figure was computed elsewhere and needs importing.

   **Session 3 answer: largely resolved.** The figure is not arbitrary — it is the documented output of the **v2 evidence-based candidate filter** in `scripts/resample_south_africa_v2.py`, built on the rule set in `src/banking_tasci/data/sa_candidate_filter.py`. Evidence gathered this session:

   | Evidence | Detail |
   |---|---|
   | Executable reproduction | Read-only re-execution of rules A–F against the parquet → **exactly 100,768** candidates, **100,768 unique** `record_id`s, **0 duplicates** |
   | Rule breakdown | C=38,185 · A=33,360 · B=18,428 · D=6,380 · E=2,880 · F=1,535 → **sum 100,768**, matching the run log digit for digit |
   | Run log | `outputs/logs/run_20260905_191954_887494.log`: `Candidates: 100768` |
   | Written provenance | `docs/south_africa_filter_history.md` (distinguishes v2's 100,768 from v1's 2,086,851 and warns against conflating them), `docs/south_africa_resampling_report.md`, `docs/research_proposal_current.tex` |
   | Source immutability | checksum `f780da12…6f06f7` unchanged after verification |

   The manifest now carries a `derived_selection` record documenting the method, generator, rules, constraints, rule breakdown, and provenance log, so the raw-count mismatch is **explained** rather than unexplained. The status remains `REQUIRES_DATA_CONFIRMATION` for one narrow reason: the selection is reproducible but **not yet materialised as its own checksummed artifact**. Writing that artifact is the single step to `COMPLETE`, and it involves no fabrication — the rules are pre-existing and documented.

   Note the manifest still honestly reports `row_count: 2250776` against `expected_row_count: 100768`; the observed value is never overwritten with the expected one.
2. **Is genuinely independent dual annotation planned for the new 500-record South African sample?** The existing 196-record component's strong Kappa statistics (R38) describe a different, smaller, earlier sample and must not be assumed to transfer.
3. **Should the existing 796-record intermediate gold corpus be used as a partial seed for the new 1,000-record sample, or should sampling start fresh from the 100,768/10,847 pools?** The requirements document does not say either way.

These are logged as open items in `docs/NEW_PIPELINE_SESSION_HANDOVER.md`.

---

## 6. What each session did not do

**Session 1 (audit).** No code was rewritten, no configuration was changed, no training job was launched, and no existing data or annotation file was deleted or overwritten. The only files created were this document, its JSON companion, the migration plan, and the session handover.

**Session 2 (Phase 1 implementation).** New files only — no existing implementation file, configuration file, or data file was modified. Specifically verified after the change:

## U0/U1/U2 self-supervised amendment — 20 October 2026

| Capability | Status | Evidence |
| --- | --- | --- |
| U0 baseline definition | COMPLETE | Versioned U0 config; shared trainer rejects continued pretraining |
| U1 token MLM strategy | COMPLETE | Dynamic 80/10/10 masking, exclusions, serialisable statistics and focused tests |
| U2 contiguous span masking | COMPLETE | Bounded, non-overlapping contiguous sampling with budget/statistics tests |
| U2 SBO | COMPLETE | Executable project-specific boundary-plus-relative-position head and finite separate/combined loss tests |
| Shared partition | COMPLETE | Identical corpus, partition, train-ID and monitor-ID checksums validate for U1/U2 |
| Representation-safe checkpoints | PARTIAL | Atomic metadata and mismatch validation implemented; end-to-end trained checkpoint reload/resume awaits authorised smoke |
| Smoke/pilot matrix | BLOCKED_AWAITING_DEPENDENCY | U1 and U2 smoke runs were explicitly prohibited this session |
| Matched final compute policy | REQUIRES_RESEARCH_DECISION | Equal updates, processed tokens, or compute must be frozen before final adaptation |

The technical U2 implementation is a project-specific boundary-plus-relative-position SBO variant and must not be described as a verbatim reproduction of the published SpanBERT implementation.

| Artifact | Expected SHA-256 (pre-existing record) | Re-verified |
|---|---|---|
| `scripts/resample_south_africa_v2.py` | `cffc7e5c…cfac` | matches |
| `data/interim/prepared.csv` | `2a3435ad…52fd` | matches |
| `data/interim/south_africa_prepared.parquet` | `f780da12…6f06f7` | matches |

`data/annotations/combined_adjudicated_v2.jsonl` still contains exactly 796 records. All five legacy configs (`base`, `aspect`, `intent`, `sentiment`, `full_pipeline`) are present and still load. No masked-language training was launched. No gold split was regenerated. No Git commit was created (not authorised).
