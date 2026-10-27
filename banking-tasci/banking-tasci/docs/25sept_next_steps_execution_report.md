# 25 September Next-Steps Execution Report

**Date:** 25 September 2026

## Git-State Findings

The audited folder is inside the parent Git worktree
`/Users/rotondwa_janti/Documents/Research Project`; the repository subfolder
does not have its own `.git` root. The active branch is `main`. No commit
entries were visible in the inspected `git log --all --oneline -n 20` output.
Untracked parent/workspace entries were preserved. The two completed SVM
artifact `git_commit.txt` files were inspected as part of the audit; no valid
repository commit could be established from the local Git history.
The requested `25septreport 1.md` was not present; the available prior audit
was `25septreport.md`.

## Pilot Provenance

`pilot_unannotated.jsonl` is not pristine: it is annotated, byte-identical to
pilot annotator A, and shares canonical label content with annotator B. The
authoritative adjudicated file was not changed. Evidence is in
`outputs/pilot_annotation_input_provenance_audit.json` and
`docs/pilot_annotation_input_provenance_audit.md`.

## South African Filter History

The v1 broad filter produced 2,086,851 candidates (approximately 92.7% of
2,250,776 cleaned rows). The v2 evidence-based filter produced 100,768
candidates (approximately 4.5%). Version 2 sampled 200, then four records were
removed for quality reasons, yielding the 196-record label-hidden annotation
input. Evidence is in `docs/south_africa_filter_history.md`.

## Documentation Corrections

Updated:

- `README.md` with dated 25 September status;
- `25septreport.md` with separate South African input/output roles;
- `docs/south_africa_filter_history.md`;
- `docs/pilot_annotation_input_provenance_audit.md`;
- `docs/project_status_25_september_2026.md`;
- `docs/bert_preflight_25sept.md`;
- `docs/tasci_implementation_gap_analysis.md`.

Created machine-readable audit/preflight outputs:

- `outputs/pilot_annotation_input_provenance_audit.json`;
- `outputs/bert_preflight_25sept.json`.

## Context-Aware SVM

Prepared and locally validated:

- `configs/baselines/svm_intent_context_combined_v2.yaml`;
- `cluster/run_svm_context_combined_v2.sh`;
- `docs/svm_context_baseline_report.md`.

The context extractor is `intent_context`; no-context formatting uses the
`[NO_CONTEXT]` sentinel. Readiness passed and manifests were verified as
556/122/118 disjoint records. The single authorized job was transferred and
submitted as Slurm job `60002` on `stampede` with 1 node, 1 task, 4 CPUs, 8 GB
memory, and a 30-minute limit. It completed on `mscluster32` with exit code
`0:0` in 13 seconds. The run directory is
`outputs/runs/20260925_102023_336739_007e949d`; exact metrics and post-hoc
subgroups are in `docs/svm_context_baseline_report.md`.

## BiLSTM

The artifact search found no complete repository-verifiable BiLSTM run. The
source/configuration path exists. The local one-epoch synthetic smoke test
passed finite loss/metric, non-empty predictions, checkpoint creation,
checkpoint reload, CPU selection, and label-map preservation. Focused tests
after the artifact-path change returned:

```text
30 passed, 0 failed, 0 skipped
```

This focused test/smoke result is not a combined-v2 cluster training result.
The runner now prepares the requested explicit BiLSTM artifacts, but no
artifact-backed BiLSTM intent/sentiment run was completed during this stage.
An intent-only Slurm script was prepared and submitted as job `60020` to
`biggpu` without a fixed node. The one status check reported `PENDING` with
reason `(Resources)` and no node assigned. The live scheduler check found
`gpuexpress` down and other GPU nodes allocated; `nvidia-smi` reported an NVML
driver/library mismatch. No BiLSTM training has started and no results are
claimed.
The detailed search and smoke-test status are recorded in
`docs/phase_3b_bilstm_baseline_report.md`.

## BERT Preflight

The local-only preflight found:

- `transformers` unavailable;
- configured local checkpoint absent;
- PyTorch 2.14.0;
- local CUDA unavailable;
- project helper imports and BIO label-map definitions present.

Status: **BERT BLOCKED BY MISSING DEPENDENCY**. No package was installed, no
checkpoint was downloaded, and no BERT job was submitted.

The BERT asset plan remains: provide a cluster-compatible `transformers` and
`tokenizers` pair in the approved offline environment, verify the local model
and tokenizer directory plus SHA-256 checksums, confirm the cluster PyTorch/
CUDA combination, run a one-epoch offline smoke test, and keep
`local_files_only=True`. No compatibility version is claimed until that
environment can be inspected successfully.

## TASCI Gap Analysis

`docs/tasci_implementation_gap_analysis.md` records the missing self-attention
BIO model, GRU/context model, no-context masking implementation, GloVe/OOV
loader, Transformer aspect integration, projection/fusion, integrated
sentiment head, ablation runners, predicted-aspect pipeline, end-to-end
inference, unified reload/resume, and TASCI-specific subgroup evaluation.
No TASCI code was implemented or trained.

## Files Created or Modified

Created during this continuation:

- `outputs/pilot_annotation_input_provenance_audit.json`;
- `docs/pilot_annotation_input_provenance_audit.md`;
- `docs/south_africa_filter_history.md`;
- `configs/baselines/svm_intent_context_combined_v2.yaml`;
- `cluster/run_svm_context_combined_v2.sh`;
- `outputs/bert_preflight_25sept.json`;
- `docs/bert_preflight_25sept.md`;
- `docs/project_status_25_september_2026.md`;
- `docs/tasci_implementation_gap_analysis.md`;
- `docs/svm_context_baseline_report.md`;
- `docs/25sept_next_steps_execution_report.md`.

Updated during this continuation:

- `README.md`;
- `25septreport.md`.

No validated gold file, split manifest, completed model run, historical report,
source dataset, or model artifact was overwritten.

## Tests and Commands

No full test suite was run. Focused tests returned `54 passed, 0 failed, 0
skipped`. Readiness, configuration, context formatting, manifest consistency,
label-map consistency, and shell syntax checks passed. The BERT preflight was
local-only and did not install/download/run a model.

## Cluster Jobs

One context-SVM job was submitted: **job 60002**, partition `stampede`, and it
completed successfully. No other job was submitted and no job was cancelled.

## Remaining Blockers

- The context-SVM run emitted no generic best checkpoint or training log;
	these are known SVM artifact-writer limitations. The model artifacts,
	predictions, metrics, labels, and manifests were present.
- The context-aware model underperformed the current-only model overall; no
	context-improves claim is supported.
- Current cluster scheduler verification is blocked by SSH authentication, so
-  intent job `60020` is pending for resources; no BiLSTM results are available.
- No artifact-backed BiLSTM run exists yet.
- BERT lacks its dependency, local checkpoint, and local CUDA runtime.
- TASCI implementation remains intentionally out of scope for this stage.

BILSTM TRAINING BLOCKED BY CLUSTER OR ARTIFACT ISSUES