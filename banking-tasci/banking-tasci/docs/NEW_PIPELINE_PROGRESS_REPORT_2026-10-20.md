# Banking TASCI `new_pipeline_v1` progress report

> **Current update — 20 October 2026:** status `PILOTS_DEFERRED_CALIBRATION_IN_PROGRESS`. Candidate 2 calibration remains `in_progress` at 0/50; no human labels have been created. Cluster login was restored and pilot assets were staged under `/datasets/rmavhengani/banking_tasci_pilot_20261020`; every listed asset checksum passed. U1 job `72405` failed in GPU preflight before Python validation/training: `nvidia-smi` reported no devices/unknown GPU error; Slurm reports no GRES for `biggpu`/`mscluster112` and no GPU in the job allocation. GPU/cluster investigation is paused by researcher decision; no pilots, local CPU pilot, or jobs were run during this continuation. No real calibration workspace or protected artifact was written. New code offers dry-run-by-default, validated human calibration checkpoint save/restore with observed-checksum protection, atomic backups, and a hash-linked audit trail; explicit human-only adjudication CLI/scaffolding returns unresolved items as pending and never infers labels. The annotation validator now reports separate blocking-error and warning counts. Frozen Candidate 2 Revision 2 was inspected read-only (1,000 IDs, 500/250/250, checksum `fdee989ff1a5935b5404488b215ebda60da86cf0da2f9d81bb1f684d055cea4f`). Latest expanded local focused tests: **161 passed**. Python compilation, CLI help, and audit JSON parsing passed; full suite not run. This update supersedes conflicting historical statements below.

Date: 20 October 2026  
Git state: `main`, no commit exists; provenance marker `UNKNOWN_NO_COMMIT`

## Executive assessment

The project has completed its data-governance foundation and passed the U1/U2 self-supervised smoke stage. It is now ready for the one-epoch representation pilots, but pilot execution is blocked by compute access: this host has neither CUDA nor Apple MPS, and non-interactive SSH authentication to the configured cluster failed.

Estimated overall research-deliverable completion is **approximately 50–55%**. This percentage reflects the full revised workflow, including annotation, downstream training, multi-seed evaluation and reporting. It is not a measure of code volume.

| Workstream | Estimated progress | Evidence-based status |
| --- | ---: | --- |
| Requirements, audit, configuration and taxonomy | 100% | Complete, including the U0/U1/U2 amendment |
| Source preparation and provenance | 100% | 100,768 South African + 10,847 international records verified |
| Candidate 2 approval and identity freeze | 100% | 1,000 identities; Freeze Revision 2 valid |
| Strict unlabelled corpus | 100% | 110,615 records; privacy PASS; zero frozen-ID overlap |
| Annotation tooling and calibration preparation | ~95% | Candidate 2 approved/frozen; workflow safety utilities and human-only adjudication scaffolding implemented; focused tests pass; human annotation remains 0/50 |
| U0/U1/U2 self-supervised implementation | ~80% | Shared trainer, U1/U2 objectives, checkpoint safety and smoke matrix complete |
| U1/U2 one-epoch pilots | 0% | U1 job 72405 failed before training because no GPU was exposed; GPU/cluster work is deferred by researcher decision; U2 not submitted |
| Human annotation and adjudication | 0% | Not started |
| Supervised 800/100/100 split | 0% | Correctly blocked until annotation is complete |
| Downstream U0/U1/U2 experiments | ~10% | Registry and legacy components exist; new-pipeline runs not started |
| Five-seed evaluation, transfer, ablations and final reporting | 0% | Not started |

## Verified completed data state

- South African candidate corpus: 100,768 records.
- International prepared corpus: 10,847 records.
- Combined relevant corpus: 111,615 records.
- Candidate 2: 1,000 approved and frozen identities, allocated 500 South African tweets, 250 international tweets and 250 international reviews.
- Regional allocation: 500 South African and 500 international records.
- Frozen identity checksum: `fdee989ff1a5935b5404488b215ebda60da86cf0da2f9d81bb1f684d055cea4f`.
- Strict unlabelled corpus: 110,615 unique records containing only `record_id` and `text`.
- Strict corpus checksum: `5ea719ec528510ddd8566410a1b533ff294093c2ce87538f472dae789cf9e3ea`.
- Frozen-ID overlap: zero.
- Privacy validation: PASS.

The strict corpus and frozen identity checksum remained unchanged after all self-supervised implementation and smoke work.

## Representation pipeline findings

The revised comparison is now defined as:

- U0: original `bert-base-uncased`, with no continued banking pretraining.
- U1: Banking MLM-BERT using dynamic BERT-style 80/10/10 token masking.
- U2: Banking Span-BERT using contiguous span masking plus a project-specific span-boundary objective.

U1 and U2 share the same base-model revision, tokenizer, strict corpus, train/monitor partition, maximum length, masking probability, seed, optimiser policy and planned pilot budget. They have separate output roots and representation-safe checkpoint metadata.

The U2 objective is executable and includes left and right boundary states plus a learned within-span relative-position embedding. It should be described as a **project-specific SpanBERT-style SBO variant**, not a verbatim reproduction of the original SpanBERT implementation.

## Smoke results

Both smoke runs used the same deterministic 3,000-record identity set with checksum `e4c21733c09cd1b9d9b8a86b80f077476bf9f3e46554f0c884985f04adb1e0de`.

| Result | U1 | U2 |
| --- | ---: | ---: |
| Status | PASS | PASS |
| CPU runtime | 69.61 s | 75.43 s |
| Initial total loss | 4.0688 | 12.5571 |
| Step-50 total loss | 3.2338 | 8.7429 |
| Step-55 total loss | 2.1767 | 9.3596 |
| Reload | PASS | PASS |
| Resume from 50 to 55 | PASS | PASS |
| Original checkpoint unchanged | Yes | Yes |
| Run storage | ~2.9 GiB | ~3.5 GiB |

U2’s final smoke batch recorded 14.652% realised masking, 13 valid spans, mean span length 3.077, zero invalid spans and zero truncated spans. Its final SBO loss was finite at 8.0494.

The loss values establish execution integrity only. U1 and U2 losses are not directly comparable because their objectives differ, and neither smoke result demonstrates downstream improvement.

## Pilot readiness and compute finding

The matched pilot policy is prepared:

- 109,509 training records and 1,106 monitoring records;
- one epoch;
- effective batch size 32 from microbatch 8 and gradient accumulation 4;
- 3,423 optimiser updates;
- evaluation and checkpointing every 500 updates;
- maximum two retained checkpoints;
- identical policy for U1 and U2.

Measured smoke throughput projects approximately 4.81 CPU hours for U1 and 5.22 CPU hours for U2 before overhead. With a 50% allowance for full monitoring, checkpointing, data loading and sequence variation, the planning estimates are approximately 7.22 and 7.82 hours.

This host has approximately 43.96 GiB free disk, no CUDA device and no available Apple MPS device. The storage gate passes, but the local pilot route is not yet classified resumable because the pilot CLI does not accept a checkpoint-resume argument.

Cluster access is available at `146.141.21.100`. The pilot code and required assets were staged separately under `/datasets/rmavhengani/banking_tasci_pilot_20261020`; all supplied asset checksums passed. U1 Slurm job `72405` failed after 2 seconds with exit code `6:0`. Its script stopped at `nvidia-smi` (`No devices were found`; GPU0 returned `Unknown Error`), before Python validation or model loading. Slurm reports `GRES=(null)` for partition `biggpu` and node `mscluster112`; `sacct` lists CPU/memory/node only and no GPU in `AllocTRES`. The script requested `--exclusive` but did not request a GPU GRES. No training updates or pilot artifacts were produced. GPU GRES syntax/availability and node health require cluster-administrator confirmation before resubmission.

## Annotation readiness

The new-pipeline annotation validator supports label-hidden input, completed-gold validation, immutable provenance checks, batch membership, privacy rules, target/opinion offsets, taxonomy validation and privacy-safe JSON/Markdown reports. The latest local change additionally rejects completed-gold submissions that omit approved source records and checks duplicate/review/thread/conversation links across the full approved source package for a present, consistent `leakage_group`.

The approved calibration batch contains 50 label-hidden, `not_started` Candidate 2 records. The approved path is `data/annotations/new_pipeline_v1_candidate_2/batches/calibration_001.jsonl` with checksum `7665366000c4b95b6c57fac91a2bd786098f16848001bf59a5c2c5a0b8700e66`.

A similarly named file under `data/annotations/new_pipeline_v1/batches/` does not match the approved Candidate 2 membership and must not be used for calibration.

No human labels have been created. The isolated calibration workspace status is `in_progress`; the immutable approved batch remains `not_started` and unchanged.

## Test evidence

- Latest expanded local focused run: calibration workspace, activation, adjudication, new-pipeline validator/schema, annotation workflow and batches — **161 passed** (20 October 2026).
- The latest run uses synthetic annotations for save/restore/adjudication; no human labels were generated and no real calibration/frozen artifact was modified.
- Earlier local validator/schema/batch run: **134 passed** (20 October 2026), before calibration-workspace and adjudication scaffolding was added.
- The 134-pass result is focused evidence only; the full suite was not run after the validator changes.
- U1 cluster job `72405`: failed GPU preflight, exit code `6:0`; training did not start.
- Earlier strict-corpus, freeze, schema and batching focused set: 174 passed.
- Current U0/U1/U2 focused set: 12 passed.
- Post-smoke focused set: passed.
- Full suite was not run in the latest sessions: `FULL_SUITE_NOT_RUN_CREDIT_SAVING`.

## Main findings and risks

1. The data-governance chain is the strongest completed part of the project. The gold identities and strict corpus are stable and independently checksummed.
2. U1/U2 smoke gates passed earlier, but neither full one-epoch pilot has run. The U1 cluster attempt failed before Python validation because Slurm/GPU did not expose a device; GPU allocation and node health must be confirmed by administrators.
3. GPU/cluster work is deferred by explicit researcher decision. Preserve the staged assets and failed-job evidence; do not investigate or resubmit until the researcher resumes that workstream.
4. Human annotation is the largest remaining research dependency. Until the 1,000 records are annotated and adjudicated, the supervised split and downstream representation comparison cannot begin.
5. U2 adds parameters, runtime and storage. These differences must remain visible in later comparisons.
6. The repository still has no Git commit. `UNKNOWN_NO_COMMIT` is recorded honestly, but it remains a provenance weakness.
7. The project contains stale historical documentation that describes the strict corpus as absent or blocked. The newest handover and audit amendment hold the current state, but old sections should not be read as the latest status.

## Critical path

1. Continue implementation-only work on calibration validation/adjudication and downstream preparation using synthetic fixtures.
2. Keep human calibration decisions researcher-led; do not generate labels or unlock main/final batches automatically.
3. Resume GPU/cluster pilot work only after a separate researcher decision.
3. Freeze the matched final-training policy and obtain resource approval.
4. Begin the authorised 50-record human calibration workflow and refine/freeze the annotation guide.
5. Complete annotation and adjudication of all 1,000 frozen identities.
6. Create the group-aware 800/100/100 supervised split.
7. Run U0/U1/U2 downstream tasks, integrated TASCI comparisons, transfer experiments, ablations and five-seed evaluation.

## Current status

`PILOTS_DEFERRED_CALIBRATION_IN_PROGRESS` (workspace status: `in_progress`, 0/50; no labels created)

No pilot, final adaptation, supervised partitioning or downstream training is in progress. Cluster/GPU work is paused by researcher decision. Human calibration awaits researcher-provided annotation decisions; no software utility creates or infers these labels.
