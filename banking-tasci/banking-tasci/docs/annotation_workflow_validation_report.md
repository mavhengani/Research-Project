# Annotation Workflow Validation Report

**Scope:** Phase 3A.1 annotation workflow CLI changes  
**Date:** 2026-09-03  
**Author:** Kiro

---

## 1. Command Executed

```bash
PYTHONPATH=src python3 -m pytest tests/test_annotation_workflow_cli.py -q
```

Working directory: `/home/fxvdev/Documents/reseach/banking-tasci/`

---

## 2. Results

| Metric | Value |
|---|---|
| Passed | 15 |
| Failed | 0 |
| Skipped | 0 |
| Errors | 0 |
| Duration | 2.08 s |

**Outcome: PASS**

---

## 3. Warnings

Two warnings were emitted — both are pre-existing sklearn warnings, identical in
kind to those noted in the Phase 3A completion report (`tests/test_agreement.py`).
They do not indicate a code defect.

```
UserWarning: A single label was found in 'y_true' and 'y_pred'.
  For the confusion matrix to have the correct shape, use the 'labels' parameter
  to pass all known labels.

RuntimeWarning: invalid value encountered in scalar divide
  k = np.sum(w_mat * confusion) / np.sum(w_mat * expected)
```

**Source:** `sklearn.metrics._classification` — triggered when a Cohen's Kappa
calculation is attempted on a single-label test fixture. This is an expected
property of small synthetic test cases where both annotators agree on every
record (only one label class is present). The `_cohens_kappa` function
correctly returns `None` (undefined kappa) in this situation.

**Action required:** None.

---

## 4. Test Coverage

| Test class / function | What is verified |
|---|---|
| `TestAnnotationAppCLI::test_parse_cli_args_all_flags` | `--input`, `--output`, `--annotator-id` are parsed correctly |
| `TestAnnotationAppCLI::test_parse_cli_args_no_args_returns_none` | Legacy sidebar mode returns None |
| `TestAnnotationAppCLI::test_load_session_records_explicit_path_used` | `explicit_output_path` loads from the given file, not the derived path |
| `TestAnnotationAppCLI::test_save_annotator_file_explicit_path` | `explicit_output_path` writes to the correct location |
| `TestAnnotationAppCLI::test_different_annotators_write_separate_files` | Annotator A and B produce distinct, non-overlapping files |
| `TestValidateAnnotationsCLI::test_completed_only_skips_not_started` | Only completed records are validated under `--completed-only` |
| `TestValidateAnnotationsCLI::test_require_complete_fails_when_incomplete` | `--require-complete` exits 1 when any record is unfinished |
| `TestValidateAnnotationsCLI::test_require_complete_passes_when_all_done` | `--require-complete` exits 0 when all records are completed |
| `TestValidateAnnotationsCLI::test_no_flags_validates_all_records` | Without flags, all records (including not_started) are counted |
| `TestCalculateAgreementCLI::test_completed_only_restricts_to_both_done` | `--completed-only` produces 0 joint records when one annotator has not finished |
| `TestCalculateAgreementCLI::test_require_complete_fails_with_incomplete` | `--require-complete` exits 1 when either file has incomplete records |
| `TestCalculateAgreementCLI::test_disagreements_alias` | `--disagreements` is accepted as an alias for `--disagreements-output` |
| `TestCreateSplitsNearDup::test_near_dup_csv_missing_column_is_ignored` | CSV without `near_dup_group_id` column returns empty mapping silently |
| `TestCreateSplitsNearDup::test_near_dup_csv_read_correctly` | `near_dup_group_id` values are read correctly, empty values skipped |
| `TestCreateSplitsNearDup::test_near_dup_absent_returns_empty` | Non-existent file returns empty dict without raising |

---

## 5. Code Changes Verified by These Tests

| File | Change | Verified |
|---|---|---|
| `scripts/annotation_app.py` | `_parse_cli_args()` added; `explicit_output_path` param on `load_session_records` and `save_annotator_file`; `main()` uses CLI args | ✅ |
| `scripts/validate_annotations.py` | `--completed-only` and `--require-complete` flags | ✅ |
| `scripts/calculate_agreement.py` | `--completed-only`, `--require-complete`, `--disagreements` alias | ✅ |
| `scripts/create_splits.py` | `--near-dup-csv` argument, `_read_near_dup_groups()` function | ✅ |

---

## 6. Requirements Not Verified by These Tests

The following requirements were implemented by static code inspection and
remain deferred to full regression testing or to human execution.

| Requirement | Reason for deferral |
|---|---|
| `adjudicate_annotations.py` `--disagreements` flag loads and applies a pre-computed disagreements file end-to-end | The interactive stdin loop cannot be tested without a live terminal; the merge logic was not exercised in this targeted run |
| Streamlit UI renders correctly with `--annotator-id` locked | Requires a live Streamlit session; not testable in headless pytest |
| `save_annotator_file` uses atomic writes | Python's `write_jsonl` calls are not atomic on all filesystems; deferred |
| Full regression: 327 + 15 + 35 + 35 + 30 = 452 tests all pass together | Full suite deliberately not run per credit-control rules |

---

## 7. No Research Artifacts Modified

- `data/annotations/pilot_unannotated.jsonl` was not touched.
- `data/interim/prepared.csv` was not regenerated.
- No model was trained.
- No annotation labels were generated or fabricated.
- The supervised-training readiness gate remains blocking.
