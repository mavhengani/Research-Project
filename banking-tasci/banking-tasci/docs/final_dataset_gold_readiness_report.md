# Final Dataset and Gold-Data Readiness Report

**Project:** Banking TASCI
**Date:** 2026-09-06
**Scope:** Annotation, validation, agreement, adjudication, gold-data creation, data splitting, and supervised-training readiness

## Executive Summary

The project now has validated gold data for both prepared datasets:

1. The original 600-record pilot dataset.
2. The 196-record South African dataset.

Both datasets have completed annotation records, validated adjudicated gold files, leakage-safe train/validation/test manifests, and passing supervised-training readiness checks.

The datasets are technically ready for baseline model training. However, the perfect agreement scores must be interpreted cautiously because the available annotator files were identical apart from annotator metadata. This confirms that the annotation, validation, agreement, adjudication, and split tooling operates consistently, but it does not provide independent human-reliability evidence.

## 1. Project Data Workflow

The completed workflow was:

```text
raw data
  -> prepared annotation input
  -> independent annotation files
  -> annotation validation
  -> inter-annotator agreement
  -> disagreement review
  -> adjudicated gold dataset
  -> leakage-safe train/validation/test splits
  -> supervised-training readiness gate
```

The original source data was preserved. Annotation outputs were written separately from the raw and prepared inputs.

## 2. Original 600-Record Pilot Dataset

### Input and annotation files

| Artifact | Status |
|---|---|
| `data/annotations/pilot_unannotated.jsonl` | Original unannotated input preserved |
| `data/annotations/pilot_annotator_a.jsonl` | Completed annotation file |
| `data/annotations/pilot_annotator_b.jsonl` | Completed annotation file |
| `data/annotations/pilot_adjudicated.jsonl` | Validated adjudicated gold dataset |

### Gold validation

Validation was completed with the repository annotation validator. The final report is:

[outputs/annotated_gold_validation.json](../outputs/annotated_gold_validation.json)

| Metric | Result |
|---|---:|
| Gold records | 600 |
| Valid records | 600 |
| Invalid records | 0 |
| Annotation errors | None |
| Aspect annotations | 1,253 |
| Records without aspects | 174 |
| Ambiguous intent records | 0 |

The final intent distribution was:

- `general_feedback`: 273
- `complaint`: 174
- `request_for_assistance`: 117
- `compliment`: 36

An intermediate missing-intent issue affected 150 completed records. Those records were assigned `general_feedback` according to the documented fallback rule, and the gold file was revalidated successfully.

### Agreement

The agreement report is:

[outputs/inter_annotator_agreement.json](../outputs/inter_annotator_agreement.json)

| Measure | Result |
|---|---:|
| Joint records | 600 |
| Intent Cohen's kappa | 1.00 |
| Category Cohen's kappa | 1.00 |
| Sentiment Cohen's kappa | 1.00 |
| Exact-span agreement | 1.00 |
| Token-level F1 | 1.00 |
| Disagreements | 0 |

### Splits

The split report is:

[data/processed/split_report.json](../data/processed/split_report.json)

| Split | Records |
|---|---:|
| Train | 420 |
| Validation | 91 |
| Test | 89 |
| **Total** | **600** |

The split was created with seed 42 and proportions of 70% train, 15% validation, and 15% test.

Generated manifests:

- [data/processed/train_manifest.csv](../data/processed/train_manifest.csv)
- [data/processed/validation_manifest.csv](../data/processed/validation_manifest.csv)
- [data/processed/test_manifest.csv](../data/processed/test_manifest.csv)

## 3. South African Dataset

### Input and annotation files

The South African annotation input contains 196 records:

[data/annotations/south_african_annotation_input.jsonl](../data/annotations/south_african_annotation_input.jsonl)

The completed annotation files are:

- [data/annotations/south_african_annotator_a.jsonl](../data/annotations/south_african_annotator_a.jsonl)
- [data/annotations/south_african_annotator_b.jsonl](../data/annotations/south_african_annotator_b.jsonl)

Both files contain all 196 records with completed annotation status.

### Final annotation validation

The validation reports are:

- [outputs/south_african_annotator_a_final_validation.json](../outputs/south_african_annotator_a_final_validation.json)
- [outputs/south_african_annotator_b_final_validation.json](../outputs/south_african_annotator_b_final_validation.json)

Both files produced the same result:

| Metric | Result |
|---|---:|
| Records | 196 |
| Valid records | 196 |
| Invalid records | 0 |
| Aspect annotations | 414 |
| Records without aspects | 30 |
| Ambiguous intent records | 0 |

### South African agreement

The final agreement report is:

[outputs/south_african_agreement_final.json](../outputs/south_african_agreement_final.json)

The final disagreement export is:

[outputs/south_african_disagreements_final.jsonl](../outputs/south_african_disagreements_final.jsonl)

| Measure | Result |
|---|---:|
| Joint records | 196 |
| Intent Cohen's kappa | 1.00 |
| Category Cohen's kappa | 1.00 |
| Sentiment Cohen's kappa | 1.00 |
| Exact-span agreement | 1.00 |
| Token-level F1 | 1.00 |
| Disagreements | 0 |

### South African adjudication and gold validation

The adjudicated South African gold file is:

[data/annotations/south_african_adjudicated.jsonl](../data/annotations/south_african_adjudicated.jsonl)

It was created from both complete annotation files using the adjudication script. Because the disagreement file was empty, no record required an interactive adjudication decision; the agreed records were preserved in the adjudicated output.

The gold validation report is:

[outputs/south_african_gold_validation.json](../outputs/south_african_gold_validation.json)

| Metric | Result |
|---|---:|
| Gold records | 196 |
| Valid records | 196 |
| Invalid records | 0 |
| Annotation errors | None |

### South African splits

South African-specific manifests were created in `data/processed/south_african/` using seed 42 and the same 70%/15%/15% proportions.

| Split | Records |
|---|---:|
| Train | 138 |
| Validation | 30 |
| Test | 28 |
| **Total** | **196** |

Generated artifacts:

- [data/processed/south_african/train_manifest.csv](../data/processed/south_african/train_manifest.csv)
- [data/processed/south_african/validation_manifest.csv](../data/processed/south_african/validation_manifest.csv)
- [data/processed/south_african/test_manifest.csv](../data/processed/south_african/test_manifest.csv)
- [data/processed/south_african/split_report.json](../data/processed/south_african/split_report.json)

## 4. Readiness-Gate Results

The South African readiness gate was run with:

```bash
python3 scripts/check_training_readiness.py \
  --annotations data/annotations/south_african_adjudicated.jsonl \
  --split-dir data/processed/south_african
```

All checks passed:

- adjudicated gold file exists;
- the unannotated input is not being used for training;
- split manifests exist;
- annotation statuses are valid;
- aspect spans are valid;
- aspect sentiment labels are valid;
- intent labels are present;
- no record appears in more than one split;
- leakage groups do not cross split boundaries;
- no unannotated record appears in a split;
- all required intent classes are present in training;
- validation and test labels are valid;
- test data is not used for model selection;
- all records pass schema validation.

The gate returned:

```text
READY: adjudicated gold + leakage-safe splits verified.
```

The original 600-record pilot had already passed the same readiness checks using its gold file and manifests.

## 5. Final Gold-Data Status

| Dataset | Records | Valid gold records | Invalid records | Splits | Readiness |
|---|---:|---:|---:|---|---|
| Original pilot | 600 | 600 | 0 | 420 / 91 / 89 | Ready |
| South African | 196 | 196 | 0 | 138 / 30 / 28 | Ready |
| **Combined total** | **796** | **796** | **0** | **558 / 121 / 117** | **Ready** |

The two adjudicated files are the authoritative gold datasets:

- `data/annotations/pilot_adjudicated.jsonl`
- `data/annotations/south_african_adjudicated.jsonl`

Together they contain 796 valid gold records.

## 6. Important Reliability Limitation

Both agreement reports show perfect agreement and zero disagreements. However, the available A/B annotation files were identical in their annotation content apart from annotator identifiers. This means:

- the schema and validation pipeline passed;
- the agreement calculation pipeline passed;
- adjudication completed without unresolved records;
- the gold files are technically valid;
- independent human reliability has not been demonstrated by these files.

For a publication-quality reliability claim, a future audit should use two genuinely independent annotation files created without copying or sharing labels. The current gold datasets may still be used for baseline experimentation, but agreement scores should not be presented as independent human agreement without this qualification.

## 7. Final Conclusion

All prepared datasets now have validated gold data:

- the original pilot gold dataset contains 600 valid records;
- the South African gold dataset contains 196 valid records;
- the combined total is 796 valid gold records;
- all split manifests exist;
- all readiness gates pass;
- no invalid records remain;
- no disagreement files contain unresolved cases.

The project is ready to proceed to baseline model training. Training should use the appropriate dataset-specific gold file and split directory, and model selection must use the validation split before one-time evaluation on the held-out test split.
