# BiLSTM Execution Report

**Date:** 25 September 2026

## Preflight

- Combined Gold Version 2: 796 records.
- Manifests: 556 train, 122 validation, 118 test; disjoint and gold-backed.
- Fixed label maps: intent and sentiment loaders matched the configured label spaces.
- Synthetic one-epoch smoke test: passed finite loss/metric, CPU device selection,
  deterministic seed 42, non-empty predictions, checkpoint creation, checkpoint
  reload equivalence, and label-map preservation.
- Focused tests: `81 passed, 0 failed, 0 skipped`.
- BiLSTM runner artifact path: locally compiled and focused-tested; it prepares
  best/last structured checkpoints, validation/test metrics, predictions,
  confusion matrix, subgroup metrics, training log, cluster metadata, and reload
  verification.

## Cluster Detection

The one authorized scheduler inspection reported:

- login host: `mscluster-login.ms.wits.ac.za`;
- `sbatch`: `/usr/bin/sbatch`;
- `biggpu`: all listed nodes down;
- `gpuexpress`: listed node down;
- other GPU-capable nodes: allocated;
- `nvidia-smi`: `Failed to initialize NVML: Driver/library version mismatch`;
- non-interactive `module avail`: unavailable because `module` was not defined.

The intent-only script was prepared at
`cluster/run_bilstm_intent_combined_v2.sh`. Intent job `60020` was submitted to
`biggpu` without a fixed node and is pending with Slurm reason `(Resources)`;
no node is assigned and training has not started. The login node was not used
for training, and no CPU fallback was submitted. There are no BiLSTM research
metrics, checkpoints, or completed cluster artifacts yet.

## Required Next Step

After a verified GPU node and compatible CUDA/PyTorch runtime become available,
submit the intent-only script first, verify its complete artifact set and
checkpoint reload, then submit sentiment separately. Do not report smoke-test
results as research-training results.

The South African component was genuinely independently annotated and manually
adjudicated. Pre-adjudication agreement was strong: intent Kappa 0.8736,
aspect-category Kappa 0.9904, aspect-sentiment Kappa 0.8750, and token-level
aspect F1 0.8966. The original 600-record component was technically validated
but did not have genuine independent annotation. Combined-model results must
therefore be interpreted with this provenance limitation.

BILSTM TRAINING BLOCKED BY CLUSTER OR ARTIFACT ISSUES
