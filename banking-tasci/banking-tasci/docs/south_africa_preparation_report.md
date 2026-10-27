# South African Data Preparation Report

**Date:** 2026-09-05  
**Scope:** Cleaning, anonymisation, filtering, canonical-schema conversion, and 200-record annotation sample creation for the South African banking Twitter dataset.

---

## 1. Implementation Files

| File | Purpose |
|---|---|
| `src/banking_tasci/data/ingest_south_africa.py` | Core ingestion module: schema validation, record ID, date mapping, official-account classification, candidate strata, anonymisation, near-dup, annotation output |
| `scripts/prepare_south_africa_data.py` | CLI entry point: orchestrates incremental processing, deduplication, near-dup, sampling, and all report writes |
| `tests/test_ingest_south_africa.py` | 50 focused unit tests (all passing) |
| `docs/south_africa_source_data_analysis.md` | Static source analysis report |
| `docs/south_africa_preparation_report.md` | This report |
| `outputs/south_africa_source_provenance.json` | Machine-readable provenance record |

---

## 2. Exact Command Used

```bash
PYTHONPATH=src python3 scripts/prepare_south_africa_data.py \
  --input-dir data/raw/archive \
  --output data/interim/south_africa_prepared.parquet \
  --report outputs/south_africa_data_report.json \
  --annotation-output data/annotations/south_african_unannotated.jsonl \
  --sample-report outputs/south_africa_annotation_sample_report.json \
  --sample-size 200 \
  --start-date 2018-01-01 \
  --end-date 2022-12-31 \
  --seed 42
```

---

## 3. Source Files Processed

| File group | Files selected | Files with in-range data | Files skipped |
|---|---|---|---|
| `tweets_from_*.parquet` | 6 (2018–2022) | 5 | 1 (2017 file starts before 2018) |
| `updated_search_terms_tweets_from_*.parquet` | 6 (2018–2022) | 5 | 1 (2017 file starts before 2018) |
| **Total** | **12** | **10** | **2** |

Files used (in-range data):
- `tweets_from_2018-01-01_to_2019-01-01.parquet`
- `tweets_from_2019-01-01_to_2020-01-01.parquet`
- `tweets_from_2020-01-01_to_2021-01-01.parquet`
- `tweets_from_2021-01-01_to_2022-01-01.parquet`
- `tweets_from_2022-01-01_to_2023-01-01.parquet`
- `updated_search_terms_tweets_from_2018-01-01_to_2019-01-01.parquet`
- `updated_search_terms_tweets_from_2019-01-01_to_2020-01-01.parquet`
- `updated_search_terms_tweets_from_2020-01-01_to_2021-01-01.parquet`
- `updated_search_terms_tweets_from_2021-01-01_to_2022-01-01.parquet`
- `updated_search_terms_tweets_from_2022-01-01_to_2023-01-01.parquet`

---

## 4. Resource Usage

| Resource | Value |
|---|---|
| Input parquet size (selected files) | ~359 MB |
| Peak memory (estimated) | ~1.1 GB |
| Available RAM | ~16 GB |
| Available disk | ~6.5 GB |
| Processing time | ~8 minutes |
| Output parquet | 192.8 MB |
| Output CSV copy | 628.0 MB |
| Near-dup scan capped at | 10,000 candidates (OOM safety cap) |

**Memory safety note:** The first run was killed (SIGKILL) when near-duplicate detection was attempted on all 2.1M candidates simultaneously. Near-dup was rearchitected to scan only a capped 10,000-record sample of the prioritised annotation candidate pool. This is appropriate because near-dup in this pipeline is used for annotation sample diversity control, not corpus-wide deduplication. Exact text deduplication (which covers the key deduplication need) was applied to the full corpus without memory issues.

---

## 5. Cleaning Counts

| Stage | Rows |
|---|---|
| Total raw rows read (2018–2022) | 3,745,847 |
| Rows outside date range | 0 |
| Empty or too short (<15 chars) excluded | (counted per file) |
| Pure retweets excluded | (counted per file) |
| Tweet_Id duplicates removed | 106,251 |
| Exact text duplicates removed (cross-file) | 473,995 |
| Confirmed official accounts excluded | 482,337 |
| Possible official accounts flagged | (flagged but retained) |
| **Final canonical rows** | **2,250,776** |

---

## 6. Anonymisation Counts

Applied per the existing `anonymise_text()` pipeline with `replace_amounts: false`:

| Pattern | Description |
|---|---|
| `[USER]` | @username mentions in tweet text |
| `[URL]` | http/https URLs |
| `[EMAIL]` | Email addresses |
| `[PHONE]` | Phone-like digit strings |
| `[ACCOUNT_OR_REFERENCE]` | Account/reference-like 9+ digit strings |
| Amounts | **Preserved** (replace_amounts: false) |
| Hashtags | # stripped, body retained |

Exact counts available in `outputs/south_africa_data_report.json` under `anonymisation_counts`. The `Username` column was dropped from canonical output entirely. Raw Tweet_Id was not stored; it was hashed into `record_id`.

---

## 7. Filtering Counts

| Category | Count |
|---|---|
| Customer-feedback candidates | 2,086,851 (92.7% of cleaned rows) |
| Likely promotional records | 128,869 (5.7%) |

Note: The high candidate rate reflects that the corpus was pre-filtered by topic at collection time (tweets directed at SA banks). Most remaining tweets are at minimum bank-related, even if not all qualify as specific customer feedback.

---

## 8. Annotation Sample Composition

| Metric | Value |
|---|---|
| Sample size | 200 records |
| Seed | 42 |
| Source | south_african_bank_tweets (100%) |
| Region | south_africa (100%) |
| Context available | 0 records (all [NO_CONTEXT]) |
| Max records per bank | 60 (configurable cap) |
| Near-dup groups in sample | measured from 10K scan subset |

**Bank distribution:**

| Bank | Count |
|---|---|
| fnb | 60 (capped) |
| absa | 60 (capped) |
| standard_bank | ~27 |
| nedbank | ~27 |
| capitec | ~26 |

**Year distribution (approximate):**

| Year | Count |
|---|---|
| 2018 | ~34 |
| 2019 | ~34 |
| 2020 | ~40 |
| 2021 | ~46 |
| 2022 | ~46 |

Priority strata represented: `fees_candidate`, `fraud_security_candidate`, `churn_candidate`, `branch_service_candidate`, `suggestion_candidate`, `warning_candidate` — all given priority sampling before the remaining quota is filled proportionally.

---

## 9. Limitations

1. **No thread context available:** All 200 records use `previous_text = "[NO_CONTEXT]"` and `context_available = false`. The SA dataset contains no reply-chain or thread graph data.

2. **Near-dup scan limited to 10,000 records:** The full 2M+ candidate pool exceeded available memory for the MinHash/LSH scan. Near-dup was applied to the 10,000 prioritised annotation candidates. Exact text deduplication covered the full corpus.

3. **Bank imbalance:** FNB dominates the base collection (~30% of rows). The 60-per-bank cap in annotation sampling partially mitigates this but does not eliminate the underlying corpus imbalance.

4. **No language detection:** The corpus contains approximately 4% South African language markers (Afrikaans/Zulu/Sotho words), but no explicit language filtering was applied. Multi-lingual tweets are included in the annotation sample; annotators should note the language of each record.

5. **Official account classification:** The confirmed-official list includes known handles but may not be exhaustive. Additional official accounts may exist in the corpus with non-standard handles. These are flagged via `possible_official_account` but not deleted.

6. **Keyword-based strata:** Candidate strata are keyword heuristics. They are NOT gold labels. The annotation sample is labelled `not_started` and requires genuine independent human annotation.

---

## 10. Licence Status

- **GitHub repository licence:** MIT (applies to collection software only)
- **Kaggle dataset licence:** Requires independent confirmation before publication
- **Twitter/X content:** Redistribution governed by Twitter/X Terms of Service — must be assessed independently

**This is an unresolved blocker for publication.** The research team must identify the Kaggle dataset licence and confirm Twitter/X content reuse rights before submitting any paper that uses this data.

---

## 11. Confirmation: No Gold Labels Created

No aspect categories, sentiments, intents, or BIO labels were created, inferred, or assigned. Every record in `data/annotations/south_african_unannotated.jsonl` has:
- `aspects: []`
- `intent: null`
- `annotation_status: "not_started"`

Candidate strata are keyword-matching heuristics used for sampling only. They are not present in the annotation output file.

---

## 12. Confirmation: No Model Training Occurred

No SVM, BiLSTM, BERT, or TASCI model was trained, fine-tuned, evaluated, or loaded during this preparation stage.

---

## 13. Confirmation: International Gold Dataset Not Modified

All six protected files are confirmed unchanged:

| File | Status |
|---|---|
| `data/annotations/pilot_adjudicated.jsonl` | UNCHANGED |
| `data/annotations/pilot_annotator_a.jsonl` | UNCHANGED |
| `data/annotations/pilot_annotator_b.jsonl` | UNCHANGED |
| `data/processed/train_manifest.csv` | UNCHANGED |
| `data/processed/validation_manifest.csv` | UNCHANGED |
| `data/processed/test_manifest.csv` | UNCHANGED |

The South African data remains entirely separate at `data/interim/south_africa_prepared.parquet` and `data/annotations/south_african_unannotated.jsonl`.

---

## 14. Test Results

```
PYTHONPATH=src python3 -m pytest tests/test_ingest_south_africa.py -v
50 passed, 0 failed, 0 skipped in 1.22s
```

Two failures were found and fixed before final run:
1. `"capitec"` was missing from `CONFIRMED_OFFICIAL_HANDLES` — added.
2. Short keyword `"app"` matched `"h-app-y"` as a substring — keywords refined to use multi-word phrases and space-padded single words to prevent false positives.

---

## 15. Next Human Annotation Commands

Once the research team is ready, launch independent annotation sessions:

```bash
# Annotator A
streamlit run scripts/annotation_app.py -- \
  --input data/annotations/south_african_unannotated.jsonl \
  --output data/annotations/south_african_annotator_a.jsonl \
  --annotator-id sa_annotator_a

# Annotator B (independent)
streamlit run scripts/annotation_app.py \
  --server.port 8502 -- \
  --input data/annotations/south_african_unannotated.jsonl \
  --output data/annotations/south_african_annotator_b.jsonl \
  --annotator-id sa_annotator_b
```

After annotation:

```bash
# Validate both files
python scripts/validate_annotations.py \
  --input data/annotations/south_african_annotator_a.jsonl \
  --require-complete \
  --output outputs/sa_validation_a.json

python scripts/validate_annotations.py \
  --input data/annotations/south_african_annotator_b.jsonl \
  --require-complete \
  --output outputs/sa_validation_b.json

# Calculate agreement
python scripts/calculate_agreement.py \
  --annotator-a data/annotations/south_african_annotator_a.jsonl \
  --annotator-b data/annotations/south_african_annotator_b.jsonl \
  --require-complete \
  --output outputs/sa_inter_annotator_agreement.json \
  --disagreements outputs/sa_annotation_disagreements.jsonl

# Adjudicate
python scripts/adjudicate_annotations.py \
  --annotator-a data/annotations/south_african_annotator_a.jsonl \
  --annotator-b data/annotations/south_african_annotator_b.jsonl \
  --disagreements outputs/sa_annotation_disagreements.jsonl \
  --output data/annotations/south_african_adjudicated.jsonl \
  --adjudicator-id sa_adjudicator_1
```

---

South African data preparation is complete. The 200-record sample remains unannotated and must undergo independent human annotation, validation, and adjudication before it can be merged into gold dataset version 2.
