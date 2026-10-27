# Phase 3B SVM Baseline Report

**Dataset:** Combined Gold Version 2
**Slurm job:** 50823
**Partition/node:** `stampede` / `mscluster22`
**Status:** SVM review complete; neural training not started

## Provenance

The South African component was genuinely independently annotated and manually adjudicated. Pre-adjudication agreement was strong: intent Kappa 0.8736, aspect-category Kappa 0.9904, aspect-sentiment Kappa 0.8750, and token-level aspect F1 0.8966. The original 600-record component was technically validated but did not have genuine independent annotation. Combined-model results must therefore be interpreted with this provenance limitation.

## Job 50823

The earlier job 50817 failed before training because the batch shell did not define `module`. Job 50823 ran after the environment and SVM dependency corrections and completed successfully:

- State: `COMPLETED`
- Exit code: `0:0`
- Elapsed: 22 seconds
- Start: `2026-09-08T05:45:31`
- End: `2026-09-08T05:45:53`
- Node: `mscluster22`
- Readiness gate: passed all checks

The original job 50753 remains pending in the unavailable `batch` partition and duplicates job 50823. It should be cancelled by the project owner to prevent duplicate training; it was not cancelled automatically.

## Results

### SVM intent

Run: `outputs/runs/20260908_054534_901414_1bd8b19a`

- Validation macro-F1: `0.4612058704`
- Test records: 118
- Test accuracy: `0.6440677966`
- Test macro-F1: `0.4283948604`
- Test weighted-F1: `0.6391079509`
- Test macro-precision: `0.4135173020`
- Test macro-recall: `0.4481196734`

Gold supports: complaint 34, compliment 8, request_for_assistance 24, suggestion 1, warning 1, churn_signal 3, general_feedback 47.

Predicted counts: complaint 31, compliment 9, request_for_assistance 27, suggestion 0, warning 0, churn_signal 4, general_feedback 47. The predictions are not collapsed, but suggestion and warning are exploratory because each has one test example and neither was predicted.

### SVM sentiment

Run: `outputs/runs/20260908_054546_120350_0d9ac5db`

- Validation macro-F1: `0.6474400365`
- Test aspect examples: 238
- Test accuracy: `0.5714285714`
- Test macro-F1: `0.5061415921`
- Test weighted-F1: `0.5591080086`
- Test macro-precision: `0.5591119839`
- Test macro-recall: `0.4945279779`

Gold supports: positive 34, negative 97, neutral 107. Predicted counts: positive 15, negative 97, neutral 126. All three classes were predicted.

## Selection and Extractors

The intent config is `intent_mode: current_only`. The successful intent model therefore uses current record text only. The context-aware `previous_plus_current` SVM was not trained and remains outstanding; it must not be described as complete.

The sentiment extractor uses explicit `[ASP]` and `[/ASP]` target markers around each aspect. The registered metadata is stored in each run's `extractor.json`:

- Intent: `intent_current_text`
- Sentiment: `sentiment_marked_aspect_text`

Only one intent SVM was trained. No second context-aware intent model was submitted in this review.

## Reloadability

Both fitted SVM pipelines are reloadable from nested `svm/` artifacts:

- `svm/model.joblib`
- `svm/vectorizer.joblib`
- `svm/label_encoder.joblib`
- `svm/config.json`
- `svm/metrics.json`
- `svm/extractor.json`

A post-hoc reload check on 10 fixed saved test examples per model reproduced the saved predictions exactly. No new or external data was used, and the saved predictions were not modified.

## Subgroup Evaluation

Subgroup results were generated post-hoc from saved predictions, Gold Version 2 annotations, the saved test manifest, and saved label maps. No retraining, threshold tuning, or model-selection recalculation was performed.

Detailed metrics and confusion matrices are in each run's `subgroup_metrics.json` and `confusion_matrix_*.csv` files.

| Task | Group | N | Macro-F1 |
|---|---|---:|---:|
| Intent | combined | 118 | 0.4284 |
| Intent | international | 61 | 0.3200 |
| Intent | South African | 29 | 0.2800 |
| Intent | context available | 24 | 0.3253 |
| Intent | no context | 94 | 0.4468 |
| Intent | reviews | 28 | 0.4065 |
| Sentiment | combined | 238 | 0.5061 |
| Sentiment | international | 149 | 0.4312 |
| Sentiment | South African | 47 | 0.3259 |
| Sentiment | context available | 30 | 0.3505 |
| Sentiment | no context | 208 | 0.5310 |
| Sentiment | reviews | 42 | 0.5469 |

Subgroups with small or imbalanced support should be treated as exploratory. The complete JSON files retain per-class support, precision, recall, F1, and confusion matrices.

## Error Analysis

Generated from saved predictions only:

- Intent errors: `outputs/runs/20260908_054534_901414_1bd8b19a/intent_errors.jsonl` (42 errors)
- Sentiment errors: `outputs/runs/20260908_054546_120350_0d9ac5db/sentiment_errors.jsonl` (102 errors)

Error files use hashed record IDs and preserve source, region, context availability, gold/predicted labels, and the relevant text/aspect fields under existing anonymisation controls. They do not expose raw customer identifiers.

## Artifact Inventory

Present for both runs:

- `config.yaml`
- `environment.txt`
- `label_maps.json`
- `train_manifest.csv`
- `validation_manifest.csv`
- `test_manifest.csv`
- nested reloadable SVM artifacts
- `extractor.json`
- `metrics.json`
- `predictions.jsonl`
- `cluster_job_metadata.json`
- `training_log.txt`
- subgroup metrics
- confusion matrices

The current run writer does not produce standalone `validation_metrics.json`, `test_metrics.json`, or an epoch-style training log; selection/test metrics are stored in `metrics.json`, and the preserved `training_log.txt` contains the Slurm stdout section. Confusion matrices are exported post-hoc. Future improvement should make the writer emit these named files directly and record log-path metadata, without changing the completed predictions.

## Recommendation

SVM baselines are valid and ready for review. Before neural training, review the subgroup and minority-class results, especially suggestion/warning support, and decide whether to train the outstanding context-aware intent SVM separately. Do not claim the context-aware baseline is complete. Do not begin BiLSTM, BERT, or TASCI training until this review is approved.
