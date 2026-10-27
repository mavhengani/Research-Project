# Candidate annotation-package review (`new_pipeline_v1`)

**Review mode:** static inspection only. No tests were executed. No source or annotation data was regenerated, modified, or written. The package remains a candidate pending researcher review; this report does not approve or freeze it.

**Recommendation: `NOT_READY_FOR_RESEARCHER_APPROVAL`**

The candidate is structurally label-hidden and its stored checksums and record counts reconcile. Approval is not recommended yet because the required South African v2-rule coverage is unavailable in the saved sample plan, all five group/linkage fields are null (so group integrity cannot be established from this package), and the stored batches are substantially source-homogeneous. The international review bank field also contains the literal value `review` for 71 records and needs interpretation.

## Artifact identity and checksum verification

- **Sample plan:** `data/annotations/new_pipeline_v1/gold_sample_plan.jsonl`
- **Sample-plan SHA-256:** `6d16d48d8997753c6c02b632e6e6e8dcb8dd6facccbf6eae403803b7ebdbb9f3`. Matches `plan_output_sha256` in `artifacts/manifests/new_pipeline_v1/gold_sample_plan_manifest.json`.
- **Annotation-record package:** `data/annotations/new_pipeline_v1/annotation_records.jsonl`
- **Annotation-record SHA-256:** `600772affabf512734ac2c8b076b72e0b7f049b684fd7bb9c4e535ba78b4231e`. Matches its package manifest; the annotation manifest also records the matching input sample-plan checksum.
- **Batch manifest:** `artifacts/manifests/new_pipeline_v1/annotation_batch_manifest.json`
- **Batch-manifest SHA-256:** `e0925db9a0620da8198ce22bf38d4662a52854d303ee7bcf1e6d9f0e025015a3`
- **Batch files:** `data/annotations/new_pipeline_v1/batches/`. The SHA-256 of each of the 11 existing batch files matches the corresponding checksum recorded in the batch manifest.
- Git provenance in the manifests is `UNKNOWN_NO_COMMIT`.

## 1–8. Records, identifiers, sources, and regions

| Check | Static finding |
|---|---|
| Total records | 1,000 in the sample plan and annotation-record package; the batch manifest also reports 1,000. |
| Unique canonical IDs | 1,000. IDs use `<canonical_source>::<source_record_id>`; all inspected IDs have a matching source prefix. |
| Duplicate canonical IDs | 0. |
| Cross-source original-ID collisions | 0. |
| Source allocation | `south_africa_tweet`: 500; `international_tweet`: 250; `international_review`: 250. |
| Regional allocation | `south_africa`: 500; `international`: 500. No source/region mismatch was observed. |

## 9–14. Source attributes and label-hidden state

### Bank distribution

- South African tweets: `fnb` 100; `absa` 100; `nedbank` 100; `standard_bank` 100; `capitec` 100.
- International tweets: bank is null for all 250.
- International reviews: Axis Bank 27; Canara Bank 7; Citibank 3; HDFC Bank 60; IDBI 3; IndusInd Bank 4; Kotak 19; Punjab National Bank 5; SBI 51; literal value `review` 71.

The `review` value is retained exactly as found in the candidate records and requires researcher interpretation; this review did not infer a bank or rewrite the source value.

### Year distribution

- South African tweets: 2018: 82; 2019: 80; 2020: 134; 2021: 106; 2022: 98.
- International tweets: year is null for all 250.
- International reviews: 2019: 84; 2020: 166.
- Overall, including null year: 2018: 82; 2019: 164; 2020: 300; 2021: 106; 2022: 98; null: 250.

### Length-band distribution

Bands below are the source-specific short/medium/long classifications preserved in sample-plan selection reasons; they are not a shared global threshold.

| Source | Short | Medium | Long | Total |
|---|---:|---:|---:|---:|
| South African tweets | 167 | 166 | 167 | 500 |
| International tweets | 84 | 82 | 84 | 250 |
| International reviews | 82 | 83 | 85 | 250 |
| **Overall** | **333** | **331** | **336** | **1,000** |

### Context availability

`context_available` is false for all 1,000 records (SA 500, international tweets 250, international reviews 250); none has available previous text. Thus the package has no context-available calibration examples. Confirm that this reflects source availability and is acceptable for the planned context workflow.

### v2 candidate-rule coverage

The saved sample plan does **not** contain usable v2-rule coverage. For the 500 South African records, every selection reason reports `v2_rule=unavailable`; the international selection reasons do not record a rule. Consequently, no observed rule counts can be reported for this candidate package. This is a required sampling-diversity indicator and needs review; this report does not reconstruct labels from source data.

### Group/linkage integrity

- `duplicate_group`: populated records 0; cross-batch violations observed 0.
- `leakage_group`: populated records 0; cross-batch violations observed 0.
- `review_id`: populated records 0; cross-batch violations observed 0.
- `thread_id`: populated records 0; cross-batch violations observed 0.
- `conversation_id`: populated records 0; cross-batch violations observed 0.

The zero-violation observations are **not proof of group integrity**: the package carries no values for any of these five grouping/linkage fields, so there are no represented groups to compare across batches. Review, thread, and conversation linkage integrity is therefore unverified from the generated package.

### Text, privacy, and task-label checks

| Check | Result |
|---|---:|
| Missing or blank current text | 0 |
| Privacy status outside the allowed new-pipeline statuses | 0 (`anonymised`: 1,000) |
| Prefilled `primary_intent` | 0 |
| Prefilled `public_warning` | 0 |
| Records with non-empty `opinions` | 0 |
| Records with `annotation_status` other than `not_started` | 0 |

No task labels are prefilled in the annotation-record package. The selection/provenance file is separate from the annotator-facing package.

## 15, 25. Stored batch distribution and calibration review

The on-disk batch files and their checksummed manifest are the earlier generated package. They have **not** been regenerated after a later batching-code change; this review reflects the persisted files only.

| Batch | Type | Records | Source distribution |
|---|---|---:|---|
| `calibration_001` | Calibration | 50 | International review 30; international tweet 5; South African tweet 15 |
| `main_001` | Main | 100 | International review 100 |
| `main_002` | Main | 100 | International review 100 |
| `main_003` | Main | 100 | International review 20; international tweet 80 |
| `main_004` | Main | 100 | International tweet 100 |
| `main_005` | Main | 100 | International tweet 65; South African tweet 35 |
| `main_006` | Main | 100 | South African tweet 100 |
| `main_007` | Main | 100 | South African tweet 100 |
| `main_008` | Main | 100 | South African tweet 100 |
| `main_009` | Main | 100 | South African tweet 100 |
| `final_001` | Final | 50 | South African tweet 50 |
| **Total** |  | **1,000** |  |

The stored manifest confirms the required 11 batches and exact sizes: calibration 50, nine main batches of 100 (900 total), final 50. Its `unresolved_balancing_warnings` list is empty.

### Calibration diversity

`calibration_001` covers all three sources: 30 international reviews, 5 international tweets, and 15 South African tweets (35 international / 15 South African). Using the source-specific bands recorded in the sample plan, it has 22 short, 10 medium, and 18 long examples. It includes 50 no-context records and zero context-available records. It includes South African representation from all five banks (3 each). No v2-rule coverage is available for the South African calibration examples, and international rule coverage is not recorded.

### Source-homogeneous main-batch limitation

Seven of nine stored main batches contain only one source (`main_001`, `main_002`, `main_004`, and `main_006`–`main_009`). `main_003` and `main_005` each contain two sources; neither covers all three. The final batch is South African-only. This is a material limitation against the requirement to preserve source and regional representation across batches where feasible. The calibration batch itself is mixed, but the main batches are not consistently source- or region-balanced.

## 28. Matters requiring researcher approval

Before approval, resolve or explicitly accept:

1. Missing South African v2-rule coverage and absent international rule-coverage metadata.
2. Null duplicate/leakage/review/thread/conversation group identifiers, which prevent package-level verification that linked records stay together.
3. The seven source-homogeneous main batches and the South African-only final batch.
4. The literal international-review bank value `review` for 71 records; confirm its meaning and whether the bank distribution is fit for review.
5. No context-available examples in calibration or in the full sample; confirm that this is an accepted property of the source data and sampling plan.
6. Whether the current checksummed batch files should remain the candidate batches despite the later batching-code change. This report intentionally does not regenerate or alter them.

No annotation has started. This report does not mark any artifact frozen or approved.

## Recommendation

`NOT_READY_FOR_RESEARCHER_APPROVAL`
