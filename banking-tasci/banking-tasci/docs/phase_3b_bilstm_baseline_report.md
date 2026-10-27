# Phase 3B BiLSTM Baseline Report

**Status date:** 25 September 2026

## Artifact Search

The local repository and synchronized output tree were searched for a complete
combined-v2 BiLSTM run. No artifact-backed run was found. In particular, no
complete matching set of checkpoints, validation/test metrics, predictions,
training log, cluster metadata, subgroup metrics, and reload verification was
present under `outputs/runs/`.

The BiLSTM source implementation and combined-v2 configuration files exist,
but source/configuration presence is not evidence of a completed research run.

## Smoke-Test Status

A one-epoch synthetic intent smoke test completed locally without using
combined research data:

- finite train loss and validation macro-F1: passed;
- non-empty predictions: passed;
- CPU device selection: passed;
- structured checkpoint creation: passed;
- checkpoint reload equivalence: passed;
- label-map preservation: passed.

The focused regression group after the artifact changes returned `30 passed,
0 failed, 0 skipped` for BiLSTM, training-loop, and reproducibility tests.

No full BiLSTM training job was started during this stage. No research BiLSTM
metrics, checkpoint, predictions, or cluster job ID are claimed.

## Artifact Path Prepared

The runner now prepares structured best/last checkpoints, explicit validation
and test metrics, a confusion matrix, subgroup metrics, cluster metadata,
training logs, and reload verification for future completed runs. This source
change is locally focused-tested but has not yet been exercised on the combined
research data.

## Required Next Step

The corrected tiny smoke test passed, and the runner now prepares the requested
artifact set. The intent-only script is prepared at
`cluster/run_bilstm_intent_combined_v2.sh`.

The live scheduler check on 2026-09-25 found no usable GPU allocation:
`biggpu` nodes were down, `gpuexpress` was down, and the other GPU-capable
nodes were allocated. `nvidia-smi` also reported an NVML driver/library
mismatch. Intent job `60020` was subsequently submitted to `biggpu` without a
fixed node and is pending with Slurm reason `(Resources)`; no node is assigned
and training has not started. The login node was not used, and no CPU fallback
was submitted.