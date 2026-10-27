# Context-Aware SVM Intent Baseline

**Status date:** 25 September 2026

## Status

The context-aware SVM configuration and single-task Slurm script were prepared,
locally validated, transferred, and submitted once.

**Slurm job:** `60002`  
**Partition:** `stampede`  
**Resources requested:** 1 node, 1 task, 4 CPUs, 8 GB memory, 30 minutes  
**Submission command:** `sbatch --partition=stampede cluster/run_svm_context_combined_v2.sh`

The job completed successfully on `mscluster32` with exit code `0:0` in 13
seconds. Readiness passed all checks. The run directory is
`outputs/runs/20260925_102023_336739_007e949d`. Its saved extractor is
`intent_context`, and its saved predictions contain all 118 test records.

The initial post-submission status check failed because of SSH authentication.
After interactive authentication, the completed job output and artifacts were
retrieved. No further result-retrieval action is required.

The run writer emitted 9/11 generic artifacts: the model-specific artifacts,
config, environment, labels, manifests, metrics, and predictions are present.
It emitted warnings for missing `best_checkpoint.pt` and `training_log.txt`,
which are SVM artifact-schema limitations rather than training failure.

## Prepared Configuration

`configs/baselines/svm_intent_context_combined_v2.yaml` uses:

- `data/annotations/combined_adjudicated_v2.jsonl`;
- `data/processed/combined_v2`;
- `intent_mode: previous_plus_current`;
- the same SVM settings and fixed intent label map as the current-only run.

The registered extractor is `intent_context`. It joins the genuine previous
text with current text and emits `[NO_CONTEXT] <current text>` when context is
unavailable. It uses text only; source, region, bank, year, title, and rating
are not features.

## Validation Before Submission

- Config loading: passed.
- Extractor registration and no-context rendering: passed.
- Label-map consistency: passed.
- Combined-v2 manifest consistency: passed; 556/122/118 disjoint records and
  all 796 IDs present in the gold file.
- Readiness CLI: passed with `READY: adjudicated gold + leakage-safe splits verified.`
- Shell syntax: passed.
- Script permission: executable.
- Focused tests: `54 passed, 0 failed, 0 skipped` across the selected baseline,
  readiness, BiLSTM, training-loop, and reproducibility tests.

## Results

| Metric | Context-aware SVM intent |
|---|---:|
| Training records | 556 |
| Validation records | 122 |
| Validation macro-F1 | 0.3966182666 |
| Test records | 118 |
| Test accuracy | 0.6186440678 |
| Test macro-precision | 0.4023809524 |
| Test macro-recall | 0.4343375648 |
| Test macro-F1 | 0.4163100023 |
| Test weighted-F1 | 0.6154657147 |

Predicted test-class counts were: complaint 36, compliment 9,
request_for_assistance 24, churn_signal 4, and general_feedback 45. Suggestion
and warning were not predicted. Gold test supports were complaint 34,
compliment 8, request_for_assistance 24, churn_signal 3, suggestion 1,
warning 1, and general_feedback 47.

The saved confusion matrix, in label order `complaint`, `compliment`,
`request_for_assistance`, `suggestion`, `warning`, `churn_signal`,
`general_feedback`, is:

```text
[[20, 3, 4, 0, 0, 1, 6],
 [ 2, 4, 0, 0, 0, 0, 2],
 [ 5, 0,14, 0, 0, 1, 4],
 [ 1, 0, 0, 0, 0, 0, 0],
 [ 1, 0, 0, 0, 0, 0, 0],
 [ 1, 0, 0, 0, 0, 2, 0],
 [ 6, 2, 6, 0, 0, 0,33]]
```

## Per-Class Metrics

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| complaint | 0.5555555556 | 0.5882352941 | 0.5714285714 | 34 |
| compliment | 0.4444444444 | 0.5000000000 | 0.4705882353 | 8 |
| request_for_assistance | 0.5833333333 | 0.5833333333 | 0.5833333333 | 24 |
| suggestion | 0.0000000000 | 0.0000000000 | 0.0000000000 | 1 |
| warning | 0.0000000000 | 0.0000000000 | 0.0000000000 | 1 |
| churn_signal | 0.5000000000 | 0.6666666667 | 0.5714285714 | 3 |
| general_feedback | 0.7333333333 | 0.7021276596 | 0.7173913043 | 47 |

## Subgroups

These are post-hoc metrics from the saved predictions. Small or imbalanced
groups are exploratory, especially context-available and South African groups.

| Group | N | Accuracy | Macro-precision | Macro-recall | Macro-F1 | Weighted-F1 |
|---|---:|---:|---:|---:|---:|---:|
| international | 89 | 0.7191011236 | 0.3815503876 | 0.3799058085 | 0.3806722689 | 0.7190570610 |
| South Africa | 29 | 0.3103448276 | 0.2669552670 | 0.2765873016 | 0.2581214942 | 0.3029297381 |
| context available | 24 | 0.6250000000 | 0.3766233766 | 0.3285714286 | 0.3333333333 | 0.6388888889 |
| no context | 94 | 0.6170212766 | 0.4185604677 | 0.4348016848 | 0.4236452570 | 0.6140403465 |
| tweets | 61 | 0.7540983607 | 0.3153661465 | 0.3255716058 | 0.3202043858 | 0.7486257350 |
| reviews | 28 | 0.6428571429 | 0.4093406593 | 0.3467532468 | 0.3636363636 | 0.6450216450 |

## Reload Verification

The saved SVM pipeline was copied to a temporary local directory and reloaded
without fitting. Using the fixed project intent label map and the same test
manifest order, all 118 reloaded predictions matched the saved predictions;
the first ten also matched. The saved extractor remained `intent_context`.

## Current-Only Comparison

The completed current-only baseline recorded validation macro-F1 `0.4612058704`,
test accuracy `0.6440677966`, test macro-F1 `0.4283948604`, and test weighted-F1
`0.6391079509`. The context-aware run recorded `0.3966182666`, `0.6186440678`,
`0.4163100023`, and `0.6154657147`, respectively.

Previous-plus-current input did not improve overall SVM intent. The
context-aware model was lower on every reported overall metric:

- validation macro-F1: `-0.0645876039`;
- test accuracy: `-0.0254237288`;
- test macro-F1: `-0.0110848581`;
- test weighted-F1: `-0.0236422363`.

The stored current-only subgroup report records macro-F1 values of 0.3200 for
international, 0.2800 for South Africa, 0.3253 for context available, 0.4468
for no context, 0.3200 for tweets, and 0.4065 for reviews. The context-aware
subgroups were 0.3807, 0.2581, 0.3333, 0.4236, 0.3202, and 0.3636,
respectively. Context improved the international and context-available
subgroup scores slightly, but decreased South African, no-context, and review
scores; the overall score decreased. Because all South African records are
no-context, no South African context benefit can be inferred.

**Conclusion:** Previous-plus-current input did not improve overall SVM intent
classification. The small improvement in the 24-record context-available
subgroup is exploratory. Because all South African records are no-context
records, no South African context benefit can be inferred. Suggestion and
warning each have only one test example and therefore have critically low
support.

## Result Retrieval Blocker

The transfer and submission completed successfully. The subsequent status/log
inspection failed authentication before retrieving `squeue`, `sacct`, logs, or
metrics. No alternate job was attempted, and no cluster job was cancelled.

After interactive authentication, retrieve job `60002` state and logs once,
then complete this report with only the artifacts actually present.