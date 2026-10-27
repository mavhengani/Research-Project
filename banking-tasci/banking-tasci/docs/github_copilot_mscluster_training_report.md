# mscluster Training Report — Phase 3B SVM Baselines

## Job Submission

- **Job ID:** 50753
- **Script:** `cluster/run_svm_combined_v2.sh`
- **Partition:** `batch`
- **Data:** `data/annotations/combined_adjudicated_v2.jsonl`, `data/processed/combined_v2/`
- **Models queued:** SVM intent (`configs/baselines/svm_intent_combined_v2.yaml`), SVM sentiment (`configs/baselines/svm_sentiment_combined_v2.yaml`)

## Status Checks

### Check 1 — 2026-09-07

Command: `squeue -j 50753`

```
             JOBID PARTITION     NAME     USER ST       TIME  NODES NODELIST(REASON)
             50753     batch run_svm_ rmavheng PD       0:00      1 (ReqNodeNotAvail, UnavailableNodes:mscluster[120-219])
```

- **State:** `PENDING`
- **Reason:** `ReqNodeNotAvail` — the requested `batch` partition nodes (`mscluster[120-219]`) are currently unavailable to the scheduler. This is a cluster capacity/availability condition, not a job configuration error.
- **Action taken:** none. Job left queued as-is; not cancelled or resubmitted.
- **Next step:** re-check `squeue -j 50753` later; once state becomes `RUNNING` or `COMPLETED`, proceed to log inspection / artifact verification per the standing checklist below.

### Check 2 — 2026-09-07

Command: `squeue -j 50753`

```
             JOBID PARTITION     NAME     USER ST       TIME  NODES NODELIST(REASON)
             50753     batch run_svm_ rmavheng PD       0:00      1 (ReqNodeNotAvail, UnavailableNodes:mscluster[120-219])
```

- **State:** `PENDING` (unchanged since Check 1)
- **Reason:** `ReqNodeNotAvail` — same nodes still unavailable to the scheduler.
- **Action taken:** none. Not cancelled or resubmitted.

### Alternate attempt — Job 50817 — 2026-09-07

Job `50817` was submitted separately to the available `stampede` partition,
leaving job `50753` unchanged. Slurm accounting reported:

```text
50817 stampede FAILED 127:0 00:00:00
```

The located stdout log was `/home-mscluster/rmavhengani/banking-tasci/slurm-50817.out`.
Its final message was:

```text
/var/lib/slurm/slurmd/job50817/slurm_script: line 32: module: command not found
```

No SVM training started and no model artifacts or metrics were produced. The
smallest correction is to initialize the cluster module function in the batch
script (for example by sourcing the site module initialization script before
`module load anaconda/anaconda-2025-12-2`). The failed job was not retried
automatically.

---

### Successful SVM run — Job 50823 — 2026-09-08

Job `50823` ran on `stampede` and completed with exit code `0:0` in 22
seconds. The readiness gate passed before both models trained. No BiLSTM,
BERT, or TASCI model was started.

Run directories:

- Intent: `outputs/runs/20260908_054534_901414_1bd8b19a`
- Sentiment: `outputs/runs/20260908_054546_120350_0d9ac5db`

#### SVM intent

- Training records: 556
- Validation records: 122
- Selected by validation macro-F1: `0.4612058704`
- Held-out test records: 118
- Test accuracy: `0.6440677966`
- Test macro-F1: `0.4283948604`
- Test weighted-F1: `0.6391079509`
- Test macro-precision: `0.4135173020`
- Test macro-recall: `0.4481196734`
- Predicted classes: complaint, compliment, request_for_assistance,
    churn_signal, general_feedback
- Prediction collapse: no; five classes were predicted. Suggestion and
    warning had zero predicted instances, while each had one test example.

#### SVM sentiment

- Training records: 1,178 aspect examples
- Validation records: 251 aspect examples
- Selected by validation macro-F1: `0.6474400365`
- Held-out test records: 238 aspect examples
- Test accuracy: `0.5714285714`
- Test macro-F1: `0.5061415921`
- Test weighted-F1: `0.5591080086`
- Test macro-precision: `0.5591119839`
- Test macro-recall: `0.4945279779`
- Predicted classes: positive, negative, neutral
- Prediction collapse: no; all three sentiment classes were predicted.

The SVM implementation selects candidates using validation macro-F1 only;
the test split is used only for final evaluation after selection. The run
reports provide combined metrics only, with no separate international, South
African, context-available, or no-context breakdowns.

#### Artifact verification

Present for both run directories: `config.yaml`, `environment.txt`,
`label_maps.json`, `train_manifest.csv`, `validation_manifest.csv`,
`test_manifest.csv`, `metrics.json`, `predictions.jsonl`, and
`git_commit.txt`.

Not written by the current SVM artifact writer: `best_checkpoint.pt`,
`training_log.txt`, standalone extractor metadata, and standalone
`confusion_matrix.csv`. The confusion matrices are embedded in
`metrics.json`; Slurm stdout contains the training log and stderr was empty.
These are SVM artifact-schema gaps, not training failures.

## Pending Verification Checklist (for the next COMPLETED check)

For each SVM model (intent, sentiment), confirm the run directory contains:

- `config.yaml`
- `environment.txt`
- `label_maps.json`
- `train_manifest.csv`
- `validation_manifest.csv`
- `test_manifest.csv`
- model artifact
- extractor metadata
- validation metrics
- test metrics
- `predictions.jsonl`
- `confusion_matrix.csv`
- training log

And summarise:
- validation and held-out test metrics
- confirmation predictions are not collapsed into a single class
- confirmation the test set was used only for final evaluation (not selection)
- combined / international / South African / context-available / no-context breakdowns where available

## Status

3. SVM BASELINES COMPLETED AND READY FOR REVIEW
