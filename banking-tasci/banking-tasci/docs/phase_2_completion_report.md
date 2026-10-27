# Phase 2 Completion Report — Annotation Pipeline and Gold-Label Preparation

**Spec:** `banking-tasci-pipeline` (Phase 2, Requirements 11–23)
**Scope:** Annotation tooling and pilot sample preparation only. No neural model was trained and no predictions were generated.

---

## 1. Summary

Phase 2 built the complete annotation toolchain for the banking TASCI project and
produced an **unannotated** pilot sample of 600 records drawn from the Phase 1
canonical data. Concretely, this phase delivered:

- a corrected phone-number anonymisation pattern (with an amount/date guard pre-pass),
- the `Annotation_Record` schema plus a full set of validation rules,
- context construction for sentence-level review annotation,
- a deterministic, diversity-preserving pilot sampler,
- a local Streamlit annotation interface,
- deterministic offset ↔ BIO conversion,
- inter-annotator agreement calculation,
- an interactive adjudication tool,
- a leakage-safe train/validation/test split manager, and
- supporting documentation (annotation guidelines, data dictionary, workflow runbook).

**What Phase 2 did NOT do:** it did not train, fine-tune, or evaluate any model
(aspect extractor, intent extractor, sentiment classifier, or baseline), and it
did not produce any predictions or any labels. The pilot sample is unannotated —
every record has empty aspects, no intent, and `annotation_status="not_started"`.
The gold dataset does not yet exist; it requires the manual human annotation and
adjudication steps described in sections 7 and 8.

---

## 2. Files created or modified

### Configuration

| File | Status | Purpose |
| --- | --- | --- |
| `configs/base.yaml` | modified | Corrected `anonymise.phone_pattern` to match the required phone formats. |

### Source (`src/banking_tasci/data/`)

| File | Status | Purpose |
| --- | --- | --- |
| `anonymise.py` | modified | Added an amount-prefixed / ISO-date-shaped digit guard pre-pass so currency amounts and dates are not misclassified as phone numbers before the phone pattern runs. |
| `annotations.py` | new | `Annotation_Record` schema (`AspectSpan`, `AnnotationRecord`), label vocabularies, JSONL I/O, and all validation rules (`validate_record`, `check_offsets`, `check_overlap`, `check_labels`, `check_context_consistency`, `check_completed_intent`, `check_no_raw_identifiers`, `validate_all`). |
| `context.py` | new | `Context_Builder`: sentence splitting and sentence-/tweet-level context record construction. |
| `bio.py` | new | `BIO_Converter`: tokenizer-agnostic offset ↔ word/subword BIO conversion with round-trip. |

### Scripts (`scripts/`)

| File | Status | Purpose |
| --- | --- | --- |
| `create_annotation_sample.py` | new | `Annotation_Sampler`: expands `prepared.csv` into annotatable units and draws the deterministic diversity-preserving pilot sample. |
| `annotation_app.py` | new | Streamlit `Annotation_Interface` for independent per-annotator labeling. |
| `validate_annotations.py` | new | `Annotation_Validator` CLI: runs `validate_all` and writes a JSON validation report. |
| `calculate_agreement.py` | new | `Agreement_Calculator` CLI: Cohen's Kappa, exact-span agreement, token-level P/R/F1, and disagreement export. |
| `adjudicate_annotations.py` | new | `Adjudication_Tool`: interactive resolution of disagreements, preserving both annotators' original values. |
| `create_splits.py` | new | `Split_Manager`: leakage-safe, validation-gated train/validation/test manifests. |

### Documentation (`docs/`)

| File | Status | Purpose |
| --- | --- | --- |
| `annotation_guidelines.md` | new | Labeling rulebook: nine aspect categories, seven intent labels, and per-aspect sentiment rules with examples. |
| `data_dictionary.md` | new | Field-by-field description of the Canonical_Record (Phase 1) and Annotation_Record (Phase 2) schemas. |
| `annotation_workflow.md` | new | Operational runbook covering sampling → annotation → validation → agreement → adjudication → splits. |

### Tests (`tests/`)

The following test files exist and cover Phase 2 (verified by listing `tests/`):

| File | Covers |
| --- | --- |
| `test_annotations.py` | Annotation_Record schema and every validation rule. |
| `test_context.py` | Context_Builder sentence splitting and context linkage. |
| `test_context_and_determinism.py` | Context/determinism behaviour. |
| `test_sampler.py` | Annotation_Sampler reproducibility, report fields, no gold-field use, diversity. |
| `test_bio.py` | The ten required BIO_Converter round-trip scenarios. |
| `test_agreement.py` | Agreement_Calculator (Kappa, span agreement, token F1, disagreements). |
| `test_adjudicate.py` | Adjudication_Tool merge/preservation behaviour. |
| `test_splits.py` | Split_Manager leakage prevention and refusal-to-run. |
| `test_anonymise.py` | Phone-pattern positive/negative cases (extended for the phone fix) plus prior anonymisation coverage. |
| `test_validate_annotations_cli.py` | Annotation_Validator CLI report structure and error handling. |
| `test_annotation_app.py` | Annotation_Interface support code. |

Phase 1 test files also remain present and passing: `test_clean.py`, `test_cli.py`,
`test_config.py`, `test_ingest.py`, `test_logging.py`, `test_raw_data_preserved.py`,
`test_scaffold.py`, `test_schema.py`, `test_seed.py`.

### Outputs / data artifacts

| File | Purpose |
| --- | --- |
| `data/annotations/pilot_unannotated.jsonl` | The 600-record unannotated pilot sample (verified: 600 lines). |
| `outputs/annotation_sample_report.json` | Sample composition report produced by the sampler. |
| `outputs/annotation_validation_report.json` | Validation report confirming all 600 records are schema-valid. |

---

## 3. Commands executed

All commands run from the project root (`banking-tasci/`) against real data:

```bash
# Generate the pilot sample from the Phase 1 canonical data
python3 scripts/create_annotation_sample.py \
  --input data/interim/prepared.csv \
  --output data/annotations/pilot_unannotated.jsonl \
  --size 600 \
  --seed 42

# Validate that every unannotated record is schema-valid
python3 scripts/validate_annotations.py \
  --input data/annotations/pilot_unannotated.jsonl \
  --output outputs/annotation_validation_report.json

# Run the full test suite
python3 -m pytest -q
```

---

## 4. Test results

The full suite passes:

```
220 passed, 1 warning in ~12s
```

- **Passed:** 220
- **Failed:** 0
- **Skipped:** 0
- **Warnings:** 1

The single warning is a pre-existing `pandas` `FutureWarning` about DataFrame
concatenation with empty or all-NA entries, emitted from
`src/banking_tasci/data/ingest.py` (Phase 1 code). It is unrelated to Phase 2 and
does not affect correctness.

---

## 5. Pilot sample composition

Read from `outputs/annotation_sample_report.json`:

- **Total records:** 600
- **Seed:** 42

**By source:**

| Source | Count |
| --- | --- |
| `international_bank_tweets` | 407 |
| `bank_reviews` | 193 |
| **Total** | **600** |

**By region:**

| Region | Count |
| --- | --- |
| `international` | 600 |

**Context availability:**

| Context available | Count |
| --- | --- |
| `true` | 152 |
| `false` | 448 |

**Text-length distribution (characters):**

| Statistic | Value |
| --- | --- |
| min | 1 |
| q1 | 80 |
| median | 140 |
| mean | 138.53 |
| q3 | 183 |
| max | 961 |

**Rating distribution (reviews only; sums to 193):**

| Rating | Count |
| --- | --- |
| 5.0 | 95 |
| 4.5 | 8 |
| 4.0 | 53 |
| 3.5 | 4 |
| 3.0 | 19 |
| 2.5 | 1 |
| 2.0 | 5 |
| 1.5 | 6 |
| 1.0 | 2 |
| **Total** | **193** |

- **Multi-sentence reviews represented:** 12

**Validation result** (from `outputs/annotation_validation_report.json`):

- **Valid:** 600
- **Invalid:** 0
- **Aspect count:** 0 / **Zero-aspect count:** 600 (as expected — the sample is unannotated)
- **Ambiguous-intent count:** 0
- No errors recorded; all label distributions empty (no labels exist yet).

---

## 6. Unresolved assumptions / known limitations

- **Streamlit availability.** `docs/annotation_workflow.md` and earlier planning
  noted that `streamlit` might not be installed and would need `pip install
  streamlit`. In the current environment `streamlit` **is** installed (verified
  version `1.62.0`), so the annotation app can be launched directly. On any fresh
  environment, install it first: `pip install streamlit`.
- **Pre-cleaned source data.** The raw source CSVs were already
  pre-tokenised/cleaned before this project received them, so the anonymisation
  audit found zero identifiers in this specific dataset (documented in the prior
  audit, `docs/prediction_pipeline_audit.md`). The corrected phone pattern is
  nonetheless verified against synthetic inputs in `tests/test_anonymise.py`, so
  the fix is exercised even though the real corpus contained nothing to mask.
- **Tweet context.** Tweets carry no genuine thread metadata, so all tweet
  records use `[NO_CONTEXT]`. Only multi-sentence reviews produce
  context-available records (152 of the 600 sampled units).
- **Split manifest shape.** The current `Split_Manager` emits `record_id`-keyed
  manifest CSVs (`train_manifest.csv` / `validation_manifest.csv` /
  `test_manifest.csv`) rather than writing a `split` column back into the records.

---

## 7. Instructions for two annotators

Two people annotate the pilot sample **independently**. Work from
`docs/annotation_workflow.md` (the runbook) and `docs/annotation_guidelines.md`
(the labeling rules). All commands run from the project root (`banking-tasci/`).

1. **Install Streamlit** if it is not already available in your environment:

   ```bash
   pip install streamlit
   ```

2. **Launch the annotation app** (local only, no internet required):

   ```bash
   streamlit run scripts/annotation_app.py
   ```

3. **Enter your own `annotator_id`** in the sidebar. Use `annotator_a` for the
   first annotator and `annotator_b` for the second. The id alone determines the
   output filename, so neither annotator can read or overwrite the other's file.

4. **Annotate all 600 records** per `docs/annotation_guidelines.md`: select exact
   aspect spans by character offset, assign each span a category and a per-aspect
   sentiment, choose the record's dominant intent, and set the ambiguity flag
   (with an alternative intent) where the intent is genuinely ambiguous. Marking a
   record "completed" requires an intent.

5. **Result.** Each annotator produces their own file:
   - `data/annotations/pilot_annotator_a.jsonl`
   - `data/annotations/pilot_annotator_b.jsonl`

This is manual human work; both annotators must complete the full sample
independently before proceeding to validation and adjudication.

---

## 8. Instructions for validation and adjudication

Run from the project root (`banking-tasci/`), in order. These are the commands
from `docs/annotation_workflow.md`.

```bash
# 1. Validate each annotator's file
python3 scripts/validate_annotations.py \
  --input data/annotations/pilot_annotator_a.jsonl \
  --output outputs/annotation_validation_report_a.json

python3 scripts/validate_annotations.py \
  --input data/annotations/pilot_annotator_b.jsonl \
  --output outputs/annotation_validation_report_b.json

# 2. Calculate inter-annotator agreement (Kappa, span agreement, token F1, disagreements)
python3 scripts/calculate_agreement.py \
  --annotator-a data/annotations/pilot_annotator_a.jsonl \
  --annotator-b data/annotations/pilot_annotator_b.jsonl \
  --output outputs/inter_annotator_agreement.json

# 3. Adjudicate disagreements (interactive; preserves both annotators' values)
python3 scripts/adjudicate_annotations.py \
  --annotator-a data/annotations/pilot_annotator_a.jsonl \
  --annotator-b data/annotations/pilot_annotator_b.jsonl \
  --adjudicator-id lead_annotator \
  --output data/annotations/pilot_adjudicated.jsonl

# 4. Validate the adjudicated gold file (must pass with zero invalid records)
python3 scripts/validate_annotations.py \
  --input data/annotations/pilot_adjudicated.jsonl \
  --output outputs/annotation_validation_report_adjudicated.json

# 5. Create leakage-safe splits (refuses to run if any record is invalid)
python3 scripts/create_splits.py \
  --input data/annotations/pilot_adjudicated.jsonl \
  --output-dir data/processed \
  --train-ratio 0.70 \
  --validation-ratio 0.15 \
  --test-ratio 0.15 \
  --seed 42
```

A low Cohen's Kappa in step 2 is a signal to refine `docs/annotation_guidelines.md`,
re-annotate, and re-measure before scaling annotation to the full dataset. The
agreement calculator and adjudication tool never auto-resolve a disagreement.

---

## 9. Explicit confirmation

- **No model was trained** in Phase 2 — no aspect extractor, intent extractor,
  sentiment classifier, or baseline was trained, fine-tuned, or evaluated.
- **No predictions were fabricated or generated.**
- **No synthetic or auto-generated gold annotations were produced.** The pilot
  sample is **UNANNOTATED**: every record has empty aspects, no intent, and
  `annotation_status="not_started"` (confirmed by the validation report:
  600 valid, 0 aspects, 600 zero-aspect).

**Closing status:** The validated annotation and split tooling is ready for
supervised model development, but the gold dataset does not yet exist — it
requires the manual human annotation and adjudication steps described above
before Phase 3 (baseline model development) can train on real labels.
