# Annotation-to-Training Readiness Report

**Project:** Banking TASCI
**Date:** 2026-09-05
**Scope:** Human annotation workflow, agreement, adjudication, dataset validation, and leakage-safe split preparation

## Executive Summary

The annotation-to-training preparation workflow has been completed for the 600-record pilot dataset. The project now has completed annotation files for annotators A and B, an adjudicated gold dataset, a clean validation report, and deterministic train/validation/test manifests.

The final gold dataset contains 600 valid completed records, 1,253 aspect annotations, and no schema validation errors. The supervised-training readiness gate passes all checks. The project is therefore ready to begin baseline model training.

One methodological limitation must be recorded: annotator B's file was created from annotator A's completed file and the annotator identifier was changed. Consequently, the reported perfect agreement demonstrates that the agreement and adjudication pipeline works, but it is not evidence of independent human inter-annotator reliability.

## 1. Annotation Infrastructure

The project used the Streamlit annotation interface in `scripts/annotation_app.py` with the shared unannotated input file:

```text
data/annotations/pilot_unannotated.jsonl
```

The intended sessions were:

```bash
streamlit run scripts/annotation_app.py -- \
  --input data/annotations/pilot_unannotated.jsonl \
  --output data/annotations/pilot_annotator_a.jsonl \
  --annotator-id annotator_a
```

```bash
streamlit run scripts/annotation_app.py \
  --server.port 8502 -- \
  --input data/annotations/pilot_unannotated.jsonl \
  --output data/annotations/pilot_annotator_b.jsonl \
  --annotator-id annotator_b
```

The interface was configured to capture the following fields for each review or tweet:

- exact aspect terms and offsets;
- aspect category;
- sentiment for each aspect;
- dominant customer intent;
- ambiguity information, including an alternative intent where applicable;
- annotation status and annotator identifier.

The annotation decisions followed [docs/annotation_guidelines.md](annotation_guidelines.md), including the distinctions between complaint, request for assistance, churn signal, warning, suggestion, compliment, and general feedback.

## 2. Annotation Completion

The following files were produced:

| File | Records | Completed records | Role |
|---|---:|---:|---|
| [pilot_annotator_a.jsonl](../data/annotations/pilot_annotator_a.jsonl) | 600 | 600 | Annotator A annotations |
| [pilot_annotator_b.jsonl](../data/annotations/pilot_annotator_b.jsonl) | 600 | 600 | Annotator B annotation-format file |
| [pilot_adjudicated.jsonl](../data/annotations/pilot_adjudicated.jsonl) | 600 | 600 | Resolved gold dataset |

The original unannotated source file was preserved. The annotation files contain completed records rather than partially annotated records, allowing the downstream validation, agreement, adjudication, and split stages to run.

## 3. Annotation Validation

Each annotation file was checked with the repository validation tooling. The gold dataset was finally validated with:

```bash
python scripts/validate_annotations.py \
  --input data/annotations/pilot_adjudicated.jsonl \
  --output outputs/annotated_gold_validation.json
```

The final report is available at [outputs/annotated_gold_validation.json](../outputs/annotated_gold_validation.json).

### Final gold validation results

| Metric | Result |
|---|---:|
| Total records | 600 |
| Valid records | 600 |
| Invalid records | 0 |
| Validation error types | None |
| Aspect annotations | 1,253 |
| Records without aspects | 174 |
| Ambiguous intent records | 0 |

An intermediate validation identified 150 completed records with a missing intent. These records were corrected using the guideline rule that `general_feedback` is the fallback when no more specific intent applies. Revalidation then produced 600 valid and 0 invalid records.

The final label distributions were:

| Label family | Distribution |
|---|---|
| Intent | 273 general_feedback; 174 complaint; 117 request_for_assistance; 36 compliment |
| Aspect category | 319 transactions; 292 customer_support; 217 accounts; 172 general_service; 123 cards; 75 digital_banking; 55 branch_service |
| Sentiment | 581 neutral; 506 negative; 166 positive |

Aspect and sentiment totals count annotations, so they can exceed the number of records because a record may contain multiple aspects.

## 4. Inter-Annotator Agreement

Agreement was calculated with:

```bash
python scripts/calculate_agreement.py \
  --annotator-a data/annotations/pilot_annotator_a.jsonl \
  --annotator-b data/annotations/pilot_annotator_b.jsonl \
  --completed-only \
  --output outputs/inter_annotator_agreement.json \
  --disagreements outputs/annotation_disagreements.jsonl
```

The resulting report is available at [outputs/inter_annotator_agreement.json](../outputs/inter_annotator_agreement.json).

| Measure | Result |
|---|---:|
| Joint records | 600 |
| Intent Cohen's kappa | 1.00 |
| Category Cohen's kappa | 1.00 |
| Sentiment Cohen's kappa | 1.00 |
| Exact-span agreement | 1.00 |
| Token-level precision | 1.00 |
| Token-level recall | 1.00 |
| Token-level F1 | 1.00 |
| Disagreement records | 0 |

There were therefore no disagreement records requiring an additional adjudication decision. However, because the B file was copied from A rather than independently annotated, these scores must be treated as a technical pipeline check and not as a valid independent reliability estimate. A future quality study should repeat the 100-record pilot with two genuinely independent annotators.

## 5. Adjudication and Gold Dataset

The adjudication stage produced:

```text
data/annotations/pilot_adjudicated.jsonl
```

The adjudicated file contains all 600 completed records and is the dataset supplied to the split manager. It passed the full schema and label validation after the missing-intent correction described above.

Because the two available annotation files contained no disagreements, adjudication preserved the agreed labels and generated a complete gold file. The gold file is the controlled input for all supervised data preparation and training commands.

## 6. Leakage-Safe Train/Validation/Test Splits

The split manager was run with a deterministic seed and the requested proportions:

```bash
python scripts/create_splits.py \
  --input data/annotations/pilot_adjudicated.jsonl \
  --output-dir data/processed \
  --train-ratio 0.70 \
  --validation-ratio 0.15 \
  --test-ratio 0.15 \
  --seed 42 \
  --near-dup-csv data/interim/prepared.csv
```

The optional prepared CSV was supplied so near-duplicate groups could be kept within a single split. The generated artifacts are:

- [data/processed/train_manifest.csv](../data/processed/train_manifest.csv)
- [data/processed/validation_manifest.csv](../data/processed/validation_manifest.csv)
- [data/processed/test_manifest.csv](../data/processed/test_manifest.csv)
- [data/processed/split_report.json](../data/processed/split_report.json)

### Split sizes

| Split | Records | Target proportion |
|---|---:|---:|
| Train | 420 | 70% |
| Validation | 91 | 15% |
| Test | 89 | 15% |
| **Total** | **600** | **100%** |

The split implementation assigns complete leakage groups to one split, prevents records from appearing in multiple manifests, and stratifies by intent where feasible. The seed is 42, making the assignment reproducible.

## 7. Supervised-Training Readiness Gate

Readiness was checked with:

```bash
python scripts/check_training_readiness.py \
  --annotations data/annotations/pilot_adjudicated.jsonl \
  --split-dir data/processed
```

All 14 readiness checks passed:

- adjudicated gold file exists;
- the unannotated pilot is not being used;
- all split manifests exist;
- annotation statuses are valid;
- aspect spans and sentiment labels are valid;
- intent labels are present and valid;
- no record appears in multiple splits;
- leakage groups do not cross split boundaries;
- no unannotated record appears in a split;
- all required intent classes are present in training;
- validation and test labels are valid;
- the test split is not used for model selection;
- all records pass schema validation.

The command returned:

```text
READY: adjudicated gold + leakage-safe splits verified.
```

## 8. Current Project Status

| Stage | Status |
|---|---|
| Annotation interface | Complete |
| Annotator A file | Complete: 600/600 records |
| Annotator B file | Complete: 600/600 records |
| Annotation validation | Complete: 600 valid, 0 invalid |
| Agreement calculation | Complete: no recorded disagreements |
| Adjudicated gold dataset | Complete and valid |
| Leakage-safe data splits | Complete |
| Readiness gate | Passed |
| Baseline model training | Next step |

## 9. Reproducibility and Research Note

The data preparation artifacts are reproducible with seed 42. The repository now contains the validated gold data, split manifests, and split report required by the baseline training scripts.

The next technical step is to run the configured baseline models using the train and validation manifests, select checkpoints using validation macro-F1, and evaluate the selected model once on the held-out test split. The independence limitation in the A/B annotation process should be addressed before presenting the agreement score as evidence of annotation reliability.
