# New Pipeline Migration Plan (`new_pipeline_v1`)

> **Authoritative current state — 20 October 2026:** data governance, Freeze Revision 2, strict-corpus construction, U1/U2 implementation, and both smoke gates are complete. The Microsoft CUDA route is unavailable after the single authorised authentication check. The sequential CPU route is storage-safe but awaits a confirmed uninterrupted power/awake window and a real pilot-resume CLI. Only `calibration_001` has been activated in a separate workspace; it remains 0/50 complete, and every main/final batch remains locked. Older phase notes are historical.

**Date:** 12 October 2026
**Based on:** `docs/NEW_PIPELINE_GAP_ANALYSIS.md` and `artifacts/audits/new_pipeline_gap_analysis.json`
**Principles followed:** Section 30 of `NEW_PIPELINE_REQUIREMENTS.md` (audit before rewriting; preserve current state; introduce `new_pipeline_v1` behind configuration; centralise schemas/taxonomy/counts/labels; do not delete legacy outputs; do not fabricate data; do not launch expensive training before manifests/leakage tests pass; every phase has tests and completion criteria; everything stays traceable).

> **Session 14 update (14 October 2026): strict corpus complete; MLM not started.** The strict 110,615-record corpus was built by stable-ID exclusion from the 111,615 verified sources using Candidate 2 Freeze Revision 2. Zero gold IDs remain, and privacy validation passes with only `record_id` and `text` retained. Corpus/evidence checksums are recorded. MLM configuration and a validation-only entry point exist with training explicitly disabled. Focused tests: **103 passed**; full suite not run.

> **Session 13 update (14 October 2026): Candidate 2 Freeze Revision 2 is governance-complete.** The new revision preserves the original 1,000-ID file byte-for-byte and adds approval ID, batch-membership, verified source-manifest, and supersession references. Focused tests passed **44**; strict-corpus readiness with verified source manifests is `READY_FOR_FINAL`. No strict corpus, annotation, split, training, or commit was created.

> **Session 12 update (14 October 2026): Candidate 2 identity freeze written with an integrity gap.** The authorised freeze created exactly four identity artifacts, preserved the expected proposed ID checksum, and left all Candidate packages unchanged. The frozen manifest is missing the approval-ID and batch-membership references required by the session. It must not be changed; a new pipeline version is required. Strict-corpus readiness remains `BLOCKED_AWAITING_FROZEN_GOLD_IDS` because verified source manifests were not supplied to the readiness assessment. No annotation, labels, splits, strict corpus, training, or commit occurred.

> **Session 11 update (14 October 2026): Candidate 2 freeze-ready, IDs NOT FROZEN.** Candidate-aware freeze lookup and the complete approval/sample/annotation/batch/review checksum chain are implemented. Focused approval, freeze, and strict-corpus tests passed **54**. The dry-run verified Candidate 2, 1,000 unique IDs, source 500/250/250, regions 500/500, and proposed gold-ID SHA-256 `fdee989ff1a5935b5404488b215ebda60da86cf0da2f9d81bb1f684d055cea4f`; it wrote no files. Strict-corpus readiness remains `BLOCKED_AWAITING_FROZEN_GOLD_IDS`. Actual freeze, annotation, splits, corpus construction, training, and a commit remain unperformed.

> **Session 10 update (14 October 2026): Candidate 2 APPROVED, IDs NOT FROZEN.** The researcher explicitly authorized `APPROVE_CANDIDATE_2_FOR_IDENTITY_FREEZE`. The first CLI attempt exposed Candidate 1 default paths; scoped fixes routed by the review's candidate number and added required approval metadata. The exact approval command then succeeded, writing `artifacts/approvals/new_pipeline_v1/candidate_2/annotation_package_approval.json` (SHA-256 `e87e939be67c6f829ab9aaa37ae914d44cfb9059f06e3b352267a9d591ee0c89`, approved at `2026-10-14T20:38:09Z`). Focused approval tests passed **9** before the fix and **10** after it; full suite not run. Candidate 1 remained preserved 17/17; Candidate 2 package checksums remained unchanged. The artifact records candidate number, annotation-record checksum, exact command, and accepted no-context limitation. No freeze, annotation, splits, strict corpus, training, or commit occurred. Phase 3 remains PARTIAL due R20 and the human workflow. A separate identity-freeze session needs explicit authorization and a Candidate-2-aware fix to the freeze tool's plan-manifest path and annotation-record checksum validation before the command template can be executed.

> **Session 9 update (14 October 2026):** Candidate 2 was materialized in its isolated candidate-specific root after `make test` returned **1,018 passed, 1 skipped, 4 warnings**. Candidate-specific static JSON/Markdown review recommends `READY_FOR_RESEARCHER_APPROVAL`; no approval/freeze action followed. Candidate-1 checksums were unchanged. R19 is COMPLETE; Phase 3 package/batching implementation is complete, but Phase 3 overall remains PARTIAL because the new-schema validator gap R20, separate researcher approval, and human annotation remain outstanding. Context-aware experiments remain blocked pending a genuine linked-context dataset. No splits, strict corpus, training, or commit occurred. A small Markdown-writer import fix after the suite was run and verified with its focused regression test; the full suite was not rerun.

> **Session 8 update (14 October 2026; focused verification):** requested Python compilation succeeded after syntax/structure fixes. The focused set finished **139 passed**. Candidate-2 dry-run showed 1,000 unique records at 500/250/250 and 500/500, all six rules, 250/250 review-ID coverage, all 11 source-target batch allocations exact with no warnings, and candidate-1 checksum preservation. Candidate 2 was not written during that session.

> **Session 7 update (14 October 2026; implementation-only):** `annotation_batches.py` was restored and extended with whole-group source/region balancing diagnostics. Candidate-2 enrichment, a candidate-2-only dry-run staging CLI, canonical-ID diff/lineage, and candidate-specific static-review support were implemented; focused tests were added but all remain **NOT_RUN**. No project script or CLI was executed, no candidate-2 output/review was generated, and candidate 1 was not intentionally modified. Phase 3 remains **PARTIAL**, provisionally **70%** based on executable evidence rather than code volume; R19 remains PARTIAL until the recreated allocator passes focused tests. No approval, freeze, annotation, split, strict corpus, training, or commit occurred. Context-aware experiments remain blocked pending genuine context data.

This plan sequences the work needed to close the gaps identified in the audit. It does not implement anything itself — each phase below should become its own focused piece of work (and, where useful, its own spec) with tests and evidence before the next phase starts.

> **Session 6 update (implementation-only, 12 October 2026):** package review representation, explicit approval/freeze tooling, calibration guide gates, checkpoint resumption, and frozen-ID readiness loading are implemented but untested (`TESTS_NOT_RUN_IMPLEMENTATION_ONLY_SESSION`). No approval or freeze artifact was created. The existing review still recommends `NOT_READY_FOR_RESEARCHER_APPROVAL`; Phase 3/4 status is not advanced until tests, researcher resolution of review issues, explicit approval, and explicit freeze are completed. See the current-session section in `docs/NEW_PIPELINE_SESSION_HANDOVER.md`.

---

## Non-negotiable constraints carried into every phase

- Never delete or overwrite: `data/annotations/combined_adjudicated_v2.jsonl`, any `*_v1`/`*_v2` annotation or manifest file, `data/processed/combined_v2/`, `data/processed/south_african/`, `data/processed/south_african_v2/`, completed `outputs/runs/*` directories, or any existing report under `outputs/`.
- All new artifacts land under clearly new, distinctly-named paths (e.g. `data/annotations/new_pipeline_v1_*.jsonl`, `data/processed/new_pipeline_v1/`, `outputs/runs/new_pipeline_v1/...` per the Section 25 recommended directory pattern).
- No expensive training (BERT, BiLSTM, MLM adaptation, TASCI) is launched until the corresponding data manifests and leakage tests pass for that phase.
- Every phase ends with: a short completion report, the tests that back it, and an update to `docs/NEW_PIPELINE_SESSION_HANDOVER.md`.

---

## Phase 0 — Freeze and audit

**Status: COMPLETE except for the Git commit, which remains unauthorised.**

- [x] Record Git state (no commits exist — re-verified session 2).
- [x] Inventory entry points, configuration, manifests, schemas, annotation code, split logic, MLM code, models, evaluation scripts, tests, cluster scripts, saved artifacts.
- [x] Write `docs/NEW_PIPELINE_GAP_ANALYSIS.md` and `artifacts/audits/new_pipeline_gap_analysis.json`.
- [x] **Establish an executable baseline** (session 2): `make test` → 506 passed, 10 failed, 1 skipped, 122.38s. All 10 failures pre-existing; 9 are test-isolation pollution (the file passes 54/54 alone), 1 is a genuine bug at `baseline_runner.py:319`.
- [ ] **Still requires authorisation:** initialize Git and make an initial commit. Phase 1 has now landed *without* a baseline commit, which means there is no `git diff` isolating it. This is a real provenance cost and the reason this item should be cleared before Phase 3.

**Completion criteria:** gap analysis and JSON report exist and are evidence-based (done). Executable baseline recorded (done). Git initialized and first commit made (pending authorisation).

---

## Phase 1 — Configuration and schemas — **COMPLETE (session 2)**

All five items below are implemented and backed by 161 passing tests. The full suite moved from 506 to 667 passing with an identical failure list, so nothing regressed.

- [x] **`configs/new_pipeline_v1.yaml`** — every Section 28 block (counts, annotation, split, domain_adaptation, context, evaluation) plus a taxonomy reference, `new_pipeline_v1` artifact paths, and an explicit `preserve_unchanged` list. Inherits `seed`/`anonymise`/`near_dup` from `base.yaml` via the existing `base:` mechanism rather than duplicating them. The `counts` block carries an in-file warning that its values are **targets to validate against, not facts**.
- [x] **`configs/taxonomies/banking_entity_attribute_v1.yaml`** — the single canonical taxonomy. 13 entities, 69 `ENTITY#ATTRIBUTE` categories, each with a Section 19 semantic mapping. Loaded only through `new_pipeline_schema.load_taxonomy()`; no duplicate category list was introduced anywhere.
- [x] **`src/banking_tasci/data/new_pipeline_schema.py`** — full Section 8 record (20 fields) and opinion (12 fields) schema, `opinions` not `aspects`, explicit/implicit `target_type`, entity/attribute split, opinion phrases with offsets, plus a collect-all-errors validator emitting `rule_id` + `fix_guidance` per Section 14.
- [x] **Six-intent + `public_warning` and four-value sentiment taxonomies** live in the new module only. Legacy `INTENT_LABELS` (7, incl. `warning`) and `ASPECT_SENTIMENTS` (3) are untouched and verified untouched by test.
- [x] **Schema tests** — taxonomy validity, entity-attribute pairs, category composition, explicit offsets, implicit nullness, zero/multi-opinion, `[NO_CONTEXT]`, round-trip serialisation.

**Completion criteria met:** both config files load; the schema round-trips explicit, implicit, zero-opinion, multi-opinion, `conflict`-sentiment, all six intents, and `public_warning=true`; all new tests pass; legacy files unchanged (checksums re-verified).

**Carried forward:** R13 stays `PARTIAL` rather than `COMPLETE` because the new schema exists but its *consumers* (sampler, splitter, BIO converter) still read the legacy schema. Migrating them is Phase 3/4 work.

---

## Phase 2 — Data manifests — **COMPLETE (session 4)**

> **Session 4 closed Phase 2.** All three required manifests now report `VERIFIED`:
>
> | Manifest | Status | Count |
> |---|---|---|
> | `south_africa_candidates_v2_source_manifest.json` | **VERIFIED** | 100,768 |
> | `international_source_manifest.json` | **VERIFIED** | 10,847 |
> | `combined_relevant_manifest.json` | **VERIFIED** | **111,615** |
>
> The South African corpus was materialised to `data/processed/new_pipeline_v1/south_africa_candidates_v2.parquet` (sha256 `15fca4f1…6231a`) with every assertion run *before* writing: exact count, unique IDs, zero duplicates, all IDs present in the parent, strict-subset confirmed, rule counts matching, and no forbidden or raw-identifier columns. Writing is atomic (temp file → `os.replace`) and refuses to overwrite without `--overwrite`.
>
> A prerequisite had to be solved first: `sa_candidate_filter.py` carries **duplicate definitions**, and its live `classify_candidate` disagrees with the authoritative vectorised selection on ~1.9% of rows. The vectorised logic was therefore extracted into `src/banking_tasci/data/sa_candidates_v2.py` as the single canonical selection (finding R44).
>
> Also this session: the manifest's Git marker became the explicit `UNKNOWN_NO_COMMIT` token so the provenance gap is machine-detectable rather than prose.

### Session 3 state (retained)

> **Session 3 update.** The blocker largely dissolved under investigation. The 100,768 figure is the documented output of the **v2 evidence-based candidate filter**, and a read-only re-execution reproduced it **exactly** (100,768 candidates, 100,768 unique IDs, 0 duplicates, per-rule breakdown matching the September 2026 run log digit for digit). What remains is not a research decision but a mechanical step: **materialise the selection as its own checksummed artifact.**
>
> The manifest generator was also extended to the full Phase 2 field and status set:
>
> - **Fields added:** `count_status`, `unique_record_count`, `duplicate_record_count`, `null_counts`, `source_distribution`, `region_distribution`, `context_availability`, `review_group_coverage`, `derived_selection` (alongside the Phase 1 fields).
> - **Statuses added:** `MISMATCH`, `SOURCE_MISSING` (with `FILE_MISSING` kept as a backwards-compatible alias), `INVALID_SCHEMA`, `PRIVACY_FAILURE` — joining `VERIFIED` and `REQUIRES_DATA_CONFIRMATION`.
> - **Status precedence:** a privacy failure outranks a matching count, so a source leaking a raw handle column can never be reported `VERIFIED` (pinned by `test_privacy_failure_outranks_count_match`).
> - **Anti-coercion invariants** are now enforced by test rather than convention: `test_mismatch_cannot_be_verified_under_any_option` tries four option combinations and asserts none yields `VERIFIED`; `test_expected_is_never_copied_into_observed_fields` and `test_derived_selection_does_not_overwrite_observed_count` guard the observed/expected separation; `test_manifest_is_deterministic_apart_from_timestamp` pins determinism.
>
> **41 manifest tests pass.** The remaining ~15% is materialising the South African candidate artifact and producing the combined 111,615 manifest.

### Original plan (session 1/2 text retained)

**Goal:** resolve the R3/R5 count conflict and produce stable, checksummed manifests for the actual starting corpora.

Session 2 built the tooling and ran it. The blocker is a data question, not an engineering one.

- [x] **Manifest generator implemented**: `src/banking_tasci/data/manifest.py` + `scripts/generate_source_manifest.py`. Records source file, row count, checksum, schema, source, region, bank distribution, year distribution, duplicate-group coverage, privacy status, candidate-status field, generation command, and pipeline version. Parquet reads use footer metadata and column projection so the 202 MB / 2.25M-row file is never fully loaded.
- [x] **International manifest: VERIFIED.** `artifacts/manifests/new_pipeline_v1/international_source_manifest.json` — 10,847 observed = 10,847 expected, `sha256 2a3435ad…52fd`, matching the checksum independently recorded in the pre-existing `outputs/international_prepared_pool_validation.json`.
- [x] **South African manifest: REQUIRES_DATA_CONFIRMATION.** `artifacts/manifests/new_pipeline_v1/south_africa_source_manifest.json` — 2,250,776 observed vs 100,768 expected (difference +2,150,008). The manifest additionally records that `customer_feedback_candidate` is True for 2,086,851 records and notes explicitly that this flag alone does not define the required corpus. The script exits non-zero.
- [ ] **BLOCKED — researcher decision required** (gap analysis Section 5, item 1): how is the 100,768-record corpus to be produced? Either (a) design and run a new, stricter candidate filter with full audit evidence, or (b) confirm the figure was computed elsewhere and import it with provenance.
- [ ] Combined 111,615-record manifest — depends on (a)/(b) above.

**Design constraint locked in by test.** The generator *reports* mismatches and never resolves them. `tests/test_new_pipeline_manifest.py` asserts this directly: `test_mismatch_never_reports_the_expected_count_as_observed`, `test_mismatch_does_not_alter_the_source_file` (byte and checksum comparison), and `test_candidate_flag_mismatch_is_flagged_as_insufficient`. There is no sampling, truncation, or row-dropping code path in the module. This implements Migration Principle 6 ("Do not fabricate … metrics") as an enforced property rather than a convention.

**Completion criteria:** unchanged from session 1 — both source manifests exist with record-identifier lists and checksums, a combined report shows 111,615 and reconciles against both sources, and tests assert the exact counts. Two of five items are done; the rest need the researcher's answer.

---

## Phase 3 — Sampling and annotation preparation — **PARTIAL; package/batching implementation complete, R20 validator incomplete (session 9)**

> Historical candidate-1 package/batch artifacts remain unchanged. Session 9 materialized candidate 2 after the full suite passed, then verified its package, 11 batches, manifests/checksums, lineage/diff, and static review. The recommendation is `READY_FOR_RESEARCHER_APPROVAL`, which is not approval. R20's new-schema annotation validator remains incomplete, and no researcher approval, annotation, or human adjudication has occurred; Phase 3 therefore remains PARTIAL.
>
> `annotation_batches.py` was restored in session 7 and verified in session 8. Session 9's full suite result was **1,018 passed, 1 skipped, 4 warnings**. Candidate-2 batch files and manifests now exist, with exact source targets/observations, 50 + 9×100 + 50 sizing, whole-group placement, and no unresolved balancing warnings. Candidate 1's prior review remains `NOT_READY_FOR_RESEARCHER_APPROVAL`; candidate 2 has a separate READY review, not approval.
>
> **A real repository defect was found and fixed while re-running the required baseline (R45):** the South African sampler's group-conflict check treated the shared NaN singleton produced by a pandas `apply()` dtype quirk as a real duplicate-group collision, which would have silently produced a 12-record selection instead of 500 on any real (non-dry-run) write. Fixed and re-verified against the real 100,768-record corpus.
>
> **Known limitation:** only `calibration_001` is diversity-selected across (source, context, length, bank); the nine main batches are source-homogeneous rather than mixed, because first-fit-decreasing places components sorted by `record_id` and canonical source prefixes sort alphabetically. Section 13 point 4's "where feasible" mixing is satisfied for calibration only — no test requires main-batch mixing, so this is a soft gap, not a defect.
>
> **Remaining for Phase 3:** implement/validate the new-schema annotation validator (R20), obtain an explicit separate researcher decision on candidate 2, and complete human annotation/adjudication. Do not approve or freeze automatically from the READY review. Context-aware experiments remain blocked because the sample has no verified context.

### Session 4 state (South African side, retained)

> **Session 4 added the South African side.** `src/banking_tasci/data/south_africa_sampler.py` + `scripts/sample_south_africa_gold.py`, verified against the real materialised corpus:
>
> | Property | Result |
> |---|---|
> | Selection | exactly **500**, all unique |
> | Per bank | **100 each** — FNB, Absa, Nedbank, Standard Bank, Capitec |
> | Length bands | q33=**132.0**, q66=**219.0** (n=100,768) |
> | Band balance | short 167 / medium 166 / long 167 |
> | Year coverage | 2018–2022 all represented |
> | v2 rule coverage | all six: A=153 B=100 C=193 D=32 E=14 F=8 |
> | Shortages | none |
>
> The three sources now have genuinely distinct quantile bands — SA 132/219, tweets 140/183, reviews 289/328 — which is the concrete justification for Requirements 7.4 and is asserted by test.
>
> **Still dry-run only.** No annotation file was written. A real write requires **both** `--write` and `--authorise-final-write`, so the authoritative gold input cannot be produced by one mistyped flag. The v2 rule is reported for coverage but never reaches the annotation view (Requirements 6.5).
>
> **Remaining for Phase 3:** calibration batching (50 + 9×100 + 50), then the authorised write once annotation begins.

### Session 3 state (international side, retained)

> **Session 3 update.** The international sampler is implemented, deterministic, and covered by **60 passing tests**. The South African 500-record side is deliberately **not** built, pending R3 materialisation.
>
> **Built:** `src/banking_tasci/data/international_sampler.py` + `scripts/sample_international_gold.py`.
>
> Measured on the real verified source (dry run, nothing written):
>
> | Property | Result |
> |---|---|
> | Selection | exactly **250 tweets + 250 reviews = 500**, all unique |
> | Tweet length bands | q33=**140.0**, q66=**183.0** (n=9,848) |
> | Review length bands | q33=**289.3**, q66=**327.7** (n=999) |
> | Strata | 25 review strata (length × rating × sentence), 3 tweet strata |
> | Shortages | none |
>
> The band figures are the concrete justification for Requirements 7.4: reviews' q33 (289.3) exceeds tweets' q66 (183.0), so a single shared character threshold would place essentially **every** review in one band. `test_no_shared_fixed_threshold_across_sources` asserts exactly this on real data.
>
> **Enforced by test:** determinism under seed 42 (including cross-process); no replacement; duplicate- and review-group integrity (no group ever split); rating used **only** for sampling diversity and never written to the annotation view nor turned into sentiment; `previous_text`/`context_available` carried through genuinely with no row-adjacency inference; explicit shortage and unsatisfied-strata reporting; label-hidden output (`opinions: []`, `primary_intent: null`, no target/category/sentiment/entity/attribute keys); source checksum recorded; source files byte-identical afterwards; and global RNG state never touched (`test_sampler_does_not_touch_global_rng`).
>
> **Scope guard:** the CLI is **dry-run by default** — writing annotation output requires an explicit `--write` — so the authoritative gold corpus cannot be produced by accident while the South African side is unverified. `test_sampler_only_handles_international_sources` asserts no South African records are ever selected. No annotation file was written this session.

### Original plan (session 1/2 text retained)

**Goal:** produce the 1,000-record label-hidden annotation input with correct stratification, replacing (not deleting) the role currently played by `create_annotation_sample.py` and `resample_south_africa_v2.py`.

1. Design a new sampler (or a substantially extended `resample_south_africa_v2.py` invoked with new arguments) implementing: 500 South African records balanced 100/bank across FNB/Absa/Nedbank/Standard Bank/Capitec; 250 international tweets; 250 international reviews. (Closes R6, R10.)
2. Add source-specific quantile-based length-band stratification (short/medium/long computed per source, not one global threshold). (Closes R11.)
3. Preserve the existing, correct label-hiding pattern (`to_annotation_records_v2`-style — aspects/opinions empty, no candidate-rule leakage into the annotation view). (Keeps R9's COMPLETE status.)
4. Add the missing sampler-output fields: source-data checksum, explicit unsatisfied-constraints reporting. (Closes R12.)
5. Implement calibration batching: a 50-record calibration batch, then 9×100 main batches, then a final 50-record batch (50+900+50=1,000). (Closes R19.)
6. Extend the annotation validator with the new schema's required checks: category composition, implicit-target nullness, duplicate/leakage-group consistency, review/conversation linkage consistency — following the existing collect-all-errors pattern in `annotations.py`'s `validate_record()` rather than inventing a new validation architecture. (Closes R20.)

**Completion criteria:** a new, distinctly-named label-hidden JSONL file with exactly 1,000 records in the correct allocation; a sample-composition report with all required fields; calibration/batch structure documented and enforced in tooling; validator extended and tested against hand-crafted valid/invalid new-schema records.

---

## Phase 4 — Gold freeze and split

**Goal:** once annotation (outside this repository's automation — this is human annotation work) produces a completed, adjudicated 1,000-record gold corpus, freeze and split it correctly.

1. Run the existing (unmodified) `annotations.validate_all()` — extended per Phase 3 — against the completed corpus; refuse to proceed on any validation failure.
2. Assign version, checksum, and an immutable manifest to the frozen corpus.
3. Invoke `scripts/create_splits.py` **explicitly** with `--train-ratio 0.80 --validation-ratio 0.10 --test-ratio 0.10 --seed 42` (never relying on its current legacy defaults — see gap analysis R21/R35). Reuse its grouping/allocation engine unchanged (R22 is already COMPLETE).
4. Extend `create_splits.py`'s output (or wrap it) to also emit the full set of required files per Section 15.3: `train.jsonl`/`validation.jsonl`/`test.jsonl` (full records, not just IDs), `split_manifest.json`, `split_distribution.json` + `.md`, `leakage_report.json` + `.md`. (Closes R23.)

**Completion criteria:** 800/100/100 split produced and checksummed; leakage report shows zero cross-split group violations; source-level allocation matches Section 15 (400/50/50 SA tweets, 200/25/25 intl tweets, 200/25/25 intl reviews); all required output files present.

---

## Phase 5 — Strict MLM corpus — **BUILDER READY, BLOCKED BY DESIGN (session 4)**

> **Session 4 built the machinery but deliberately did not build the corpus.**
>
> `src/banking_tasci/data/unlabelled_corpus.py` + `scripts/build_strict_unlabelled_corpus.py` implement two modes:
>
> - **PREPARATION** (default) — validates manifests and arithmetic, inspects gold-ID availability, writes a readiness report, and **never claims a corpus exists**.
> - **FINAL** — requires frozen gold identifiers (exactly 1,000: 500 SA, 250 intl tweets, 250 intl reviews).
>
> PREPARATION run output: all five arithmetic identities consistent, all three source manifests `VERIFIED`, then correctly **`BLOCKED_AWAITING_GOLD_IDS`** (exit 3).
>
> ```text
> 100,768 - 500   = 100,268      10,847 - 500 = 10,347
> 250 + 250       = 500          111,615 - 1,000 = 110,615
> 100,268 + 10,347 = 110,615     ✓ all consistent
> ```
>
> **Why it is not COMPLETE:** the 1,000 gold identifiers do not exist. Building a 110,615-record file today would mean removing 1,000 *arbitrary* records — precisely what Requirements Migration Principle 6 forbids. FINAL mode refuses an invalid gold set, refuses when gold IDs are absent from the corpus, and refuses on any count mismatch rather than trimming or padding.
>
> The Section 16 field policy is fully encoded by exclusion category (task labels, annotation metadata, partition labels, predictive shortcuts including source/bank/region/rating, candidate and sampling rules), retaining only `record_id` + `text`, with `previous_text` only when explicitly approved.

### Original plan (retained)

**Goal:** build the 110,615-record strict unlabelled corpus for domain adaptation, excluding all gold records and all prohibited predictive metadata.

1. Depends on Phase 2 and Phase 4 completing first (need the combined 111,615 manifest and the frozen 1,000-record gold corpus's stable IDs to exclude).
2. Implement a new corpus builder (e.g. `src/banking_tasci/data/mlm_corpus.py`) that takes the combined manifest, subtracts gold IDs by stable identifier and checksum-aware comparison, and strips every field Section 16 prohibits (labels, bank identity, region identity, ratings, candidate-rule metadata, sampling-rule metadata).
3. Re-apply `anonymise.py`'s privacy validation to the resulting text-only export (reuse unchanged).
4. Produce the required evidence: source manifest, final record count (expect 110,615 or a documented, justified correction), gold-exclusion report, duplicate report, checksum, text-field policy document.

**Completion criteria:** final count matches 110,615 or a documented correction is recorded; a test asserts zero overlap between gold IDs and MLM corpus IDs; a test asserts no label/bank/region fields are present in the MLM export; privacy validation passes.

---

## Phase 6 — Domain adaptation

**Goal:** train and verify banking-adapted BERT. **Do not start until Phase 5 passes.**

1. New modules required (per gap analysis R25): `src/banking_tasci/data/mlm_dataset.py` (tokenizer + masking policy, `masking_probability: 0.15`, `max_length: 128`), `src/banking_tasci/models/bert_mlm.py` (local checkpoint loading + MLM head), `src/banking_tasci/training/mlm_runner.py` (training loop with validation loss, checkpoint/resume, deterministic logging).
2. Re-run BERT dependency/checkpoint/device preflight (same discipline as `docs/bert_preflight_25sept.md` from the prior generation) before scheduling any actual training.
3. Extend `training/reproducibility.py`'s `RunArtifacts`/`write_run()` to additionally persist `pipeline_version`, `taxonomy_version`, and manifest checksums (closes part of R32), once Phase 1's config exists to supply real values.
4. Train original-vs-adapted BERT as the primary comparison; verify checkpoint reload and resume explicitly (do not assume the existing generic resume support is sufficient without a dedicated test for this specific MLM trainer).

**Completion criteria:** adapted checkpoint exists, reload-verified; environment, loss history, and training arguments are saved; both original and adapted conditions are ready to be used identically by every downstream task.

---

## Phase 7 — Target and category models

1. Implement a self-attention BIO aspect extractor (new model class) consuming the already-correct `src/banking_tasci/data/bio.py` conversion layer unchanged. (Closes R27.)
2. Implement entity-attribute category prediction (text-category-pair BERT condition, semantic category strings, related/unrelated pair sampling) against the new canonical taxonomy from Phase 1. (Closes R28.)
3. Update the existing BERT token-classification baseline to run on the new 800/100/100 split once available.

**Completion criteria:** token/exact-span precision/recall/F1 reported for both self-attention and BERT-baseline conditions; category classifier reports macro/weighted-F1 with confusion matrix; both support zero/multi-target and implicit-category cases.

---

## Phase 8 — Intent model

1. Implement a new GRU contextual intent model class, informed by the already-mostly-correct `configs/intent.yaml` design (`context_mode`, `no_context.token`) but with corrected `<PLACEHOLDER_*>` values and the corrected six-intent-plus-`public_warning` label set from Phase 1. (Closes part of R29.)
2. Re-point existing SVM/BiLSTM/BERT intent baselines at the corrected label set and the new split.
3. Implement current-only vs previous-plus-current as a matched ablation pair sharing partitions/seeds/architecture.

**Completion criteria:** context-available/no-context subgroup metrics reported for every condition; `public_warning` evaluated as a separate flag, not folded into the primary intent metric.

---

## Phase 9 — Sentiment and integration

1. Implement a GloVe loader with explicit OOV policy (new module). (Closes part of R30.)
2. Implement intent-projection and aspect-intent fusion modules, and a TASCI sentiment head consuming the fused representation. (Closes R30.)
3. Re-point existing SVM/BiLSTM/BERT sentiment baselines at the corrected four-label (including `conflict`) sentiment set.
4. Build a dedicated no-intent / predicted-intent / gold-intent ablation runner holding training records, validation records, test records, seeds, training budget, selection metric, and base architecture fixed across all three conditions except the intent input. (Closes R31's TASCI-integration gap.)
5. Test pipeline propagation: gold-target vs predicted-target, gold-category vs predicted-category.

**Completion criteria:** all three intent conditions report matched-partition metrics; propagation-loss report exists comparing gold vs predicted upstream inputs.

---

## Phase 10 — Evaluation and final reporting

1. Implement all Section 24 metrics (target extraction, category, intent, sentiment, end-to-end tuple matching) and subgroup reports (international/SA, tweets/reviews, context available/no-context, explicit/implicit target, zero/single/multi-opinion), labelling small subgroups exploratory.
2. Run main neural experiments across five random seeds; report per-run metrics, mean, standard deviation, and the selected checkpoint per run.
3. Freeze predictions and reports under the Section 25 recommended immutable run-directory pattern.
4. Update research documentation to reflect only what is actually executable and evidenced — consistent with this migration plan's own evidentiary standard.

**Completion criteria:** matches the full Section 33 "Definition of done" checklist in the requirements document.

---

## Suggested next concrete step (updated after session 5)

Phase 2 is complete. Phase 3's combination and batching engineering is implemented; what remains before human annotation can begin is execution evidence, not design. Priority order:

1. **Run the two new test files and the batching script against real data.** `tests/test_gold_sample_plan.py` and `tests/test_annotation_batches.py` were executed earlier in session 5 (21/24 passing respectively) against synthetic fixtures; the newest `annotation_batches.py` additions (`transition_batch_status`, `validate_submission`, `next_incomplete_record`, deterministic in-batch ordering) and their tests have not been executed yet. `scripts/build_annotation_batches.py` has not been run against the real `annotation_records.jsonl` written this session — no batch files exist on disk yet.

2. **Authorise and perform the gold write.** When the researcher is ready to begin annotating, the combined 1,000-record plan (`data/annotations/new_pipeline_v1/gold_sample_plan.jsonl`, already written and verified this session) is the single source of truth; freeze its selected identifiers into `artifacts/manifests/new_pipeline_v1/gold_ids.json` in the shape the strict-corpus builder already expects (`south_africa` / `international_tweets` / `international_reviews`). That single file unblocks Phase 5.

3. **Authorise the baseline Git commit.** Five sessions without one. Every manifest now carries the explicit `UNKNOWN_NO_COMMIT` marker, which makes the gap detectable but does not close it.

4. **De-duplicate `sa_candidate_filter.py` behind a compatibility plan** (finding R44). The canonical selection path is now safely isolated in `sa_candidates_v2.py`, so this is no longer urgent — but the module still has four shadowed symbols and a divergent `classify_candidate`, which will mislead the next person who reads it.

5. **Harden the two remaining fragile test modules** (`test_evaluation_phase3a1.py`, `test_near_duplicates.py`) — same class as R42.

6. **Then Phase 4** (gold freeze and 80/10/10 split), which requires completed annotation.

**Do not** build the strict unlabelled corpus, generate gold splits, or launch MLM training until real gold identifiers exist.

## Earlier guidance (session 4, retained)

Phase 2 is complete. Phase 3 has both sides in dry-run. The critical path now runs through human annotation, not engineering. Priority order:

1. **Add calibration batching to both samplers** (50 + 9×100 + 50 = 1,000, per Requirements 13.3). This is the last engineering step before annotation can begin, and it has no blockers. Note the requirement's own warning: 50 + 9×100 = 950, so the final 50-record batch must be explicit.

2. **Authorise and perform the gold write.** When the researcher is ready to begin annotating, run both samplers with `--write --authorise-final-write`, then freeze the selected identifiers into `artifacts/manifests/new_pipeline_v1/gold_ids.json` in the shape the strict-corpus builder already expects (`south_africa` / `international_tweets` / `international_reviews`). That single file unblocks Phase 5.

3. **Authorise the baseline Git commit.** Four sessions without one. Every manifest now carries the explicit `UNKNOWN_NO_COMMIT` marker, which makes the gap detectable but does not close it.

4. **De-duplicate `sa_candidate_filter.py` behind a compatibility plan** (finding R44). The canonical selection path is now safely isolated in `sa_candidates_v2.py`, so this is no longer urgent — but the module still has four shadowed symbols and a divergent `classify_candidate`, which will mislead the next person who reads it.

5. **Harden the two remaining fragile test modules** (`test_evaluation_phase3a1.py`, `test_near_duplicates.py`) — same class as R42.

6. **Then Phase 4** (gold freeze and 80/10/10 split), which requires completed annotation.

**Do not** build the strict unlabelled corpus, generate gold splits, or launch MLM training until real gold identifiers exist.

## Earlier guidance (session 3, retained)

Session 3 cleared all three of session 2's blockers except the Git commit, and the suite is now green (772 passed / 0 failed), making it a trustworthy gate. Next actions in priority order:

1. **Materialise the South African candidate artifact.** This is now a mechanical step, not a research decision. Write the v2 filter's 100,768-record selection to `data/interim/south_africa_candidates_v2.parquet` (the path the pre-existing `outputs/south_africa_candidates_v2_validation.json` already anticipates), preserving stable `record_id`s, then manifest it with `required_columns` and an expected count of 100,768. Expected outcome: `status: VERIFIED` and **R3 → COMPLETE**. The filter already exists and is verified; nothing is fabricated.

   *Recommended guard:* assert the materialised artifact's identifiers are a strict subset of the parent parquet's, so provenance is checkable rather than assumed.

2. **Produce the combined 111,615-record manifest** once step 1 lands (100,768 + 10,847). This completes Phase 2 and unblocks Phase 5's gold-exclusion arithmetic.

3. **Authorise the baseline Git commit.** Still outstanding and now three sessions deep: there is no `diff` isolating any phase, and every manifest and run artifact records `git_commit: "unknown (no commit or not a git repository)"`. This is the largest remaining provenance gap against Requirements Section 25.

4. **Harden the two remaining fragile test modules.** `tests/test_evaluation_phase3a1.py` and `tests/test_near_duplicates.py` have no `sys.path` setup and cannot be collected standalone — the same class of latent fragility as finding R42. Cheap to fix, and it prevents a future session chasing phantom failures.

5. **Then complete Phase 3's South African side** (500 records, 100 per bank across FNB/Absa/Nedbank/Standard Bank/Capitec) and the calibration/batching structure (50 + 9×100 + 50). The international sampler's `SamplerReport` and group-integrity logic are designed to serve both sources, so this is extension rather than new design.

**Do not** regenerate the final 1,000-record gold corpus or the 800/100/100 split until both source manifests are `VERIFIED` and the annotation work itself is complete.

## Revised representation phases

- **Phase 5A — U1 Banking MLM-BERT:** shared trainer, dynamic token MLM, validate-only complete; independent smoke and pilot remain.
- **Phase 5B — U2 Banking Span-BERT:** contiguous masking and simplified boundary-mean SBO forward/loss complete; authorised smoke must verify checkpoint/reload/resume.
- **Phase 5C — matched pilot comparison:** blocked pending both smoke gates and a frozen compute-matching policy.
- **Phase 5D — final U1/U2 adaptation:** blocked pending pilots, resource approval and frozen configurations.
- **Phase 8A — downstream U0/U1/U2 matrix:** blocked awaiting completed gold annotations and group-aware split.
- **Phase 8B — integrated TASCI comparison:** blocked by Phase 8A.

Rollback is configuration-scoped: U0 remains the untouched `bert-base-uncased` baseline, and U1/U2 use separate run roots. No phase may alter the strict corpus or frozen identities.
