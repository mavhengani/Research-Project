# Banking TASCI Repository Audit

**Audit date:** 25 September 2026  
**Repository:** `banking-tasci`  
**Audit type:** read-only repository and artifact audit  
**Permitted change:** creation of this file only

## 1. Audit Scope and Method

This report is based on direct inspection of the repository rather than on the
previous conversation summary. The inspection covered the README, project
metadata, dependency list, configuration files, source package, scripts, tests,
annotation files, processed manifests, outputs and run artifacts, documentation,
cluster scripts, Git status, and Git history.

The audit used file listing, text reading, AST-level source/test inventory, and
lightweight parsing of existing JSON, JSONL, and CSV artifacts. It did **not**:

- run the full test suite;
- train or evaluate a model;
- submit or cancel a cluster job;
- modify source code, data, annotations, models, configurations, or existing
  reports.

The only repository file created by this audit is this report.

## 2. Repository and Git State

Observed repository root:

```text
/Users/rotondwa_janti/Documents/Research Project/banking-tasci/banking-tasci
```

Observed branch:

```text
main
```

`git log --oneline -n 20` produced no visible commit entries in the inspected
repository. Therefore this audit cannot use Git history to establish when a
feature was implemented or to attribute individual changes to commits.

`git status --short` showed no modified or deleted repository files. It did show
untracked entries expressed through parent-relative paths, including `.DS_Store`,
source/data files, PDFs, `KIRO_SPEC.md`, and a parent-level directory entry.
Those entries were not changed. The status output does not establish that all
files in the broader workspace are intended repository artifacts.

## 3. Project Metadata and Dependencies

### `pyproject.toml`

- Package name: `banking-tasci`
- Version: `0.1.0`
- Python requirement: `>=3.10`
- Build backend: setuptools with wheel
- Source layout: packages found under `src`
- Pytest test path: `tests`

### `requirements.txt`

Declared dependencies are pandas, PyYAML, NumPy, PyTorch, scikit-learn,
joblib, pytest, Hypothesis, and Streamlit 1.62.0. `transformers` is mentioned
as an optional dependency for the BERT baseline and is commented out of the
requirements file. The repository therefore does not guarantee a BERT runtime
from the default requirements installation.

### README status versus observed state

The README still describes the project as Phase 3A with supervised training
blocked pending annotation. That text is stale relative to the stored
combined-v2 data and SVM run artifacts inspected here. It remains useful as
project documentation, but it is not a current execution record.

## 4. Repository Structure

### Configuration files

The repository contains:

- `configs/base.yaml`
- `configs/aspect.yaml`
- `configs/intent.yaml`
- `configs/sentiment.yaml`
- `configs/full_pipeline.yaml`
- `configs/baselines/bert_aspect.yaml`
- `configs/baselines/bert_intent.yaml`
- `configs/baselines/bert_sentiment.yaml`
- `configs/baselines/bilstm_intent.yaml`
- `configs/baselines/bilstm_intent_combined_v2.yaml`
- `configs/baselines/bilstm_sentiment.yaml`
- `configs/baselines/bilstm_sentiment_combined_v2.yaml`
- `configs/baselines/svm_intent.yaml`
- `configs/baselines/svm_intent_combined_v2.yaml`
- `configs/baselines/svm_sentiment.yaml`
- `configs/baselines/svm_sentiment_combined_v2.yaml`

These define base data/preprocessing settings, proposed TASCI model settings,
and SVM, BiLSTM, and BERT baseline settings. The combined-v2 configs point to
the combined adjudicated data/split workflow. BERT configs specify a local
pretrained model path, offline loading, sequence length, and training options.

### Source package

The package is under `src/banking_tasci/`.

Implemented areas observed in source:

- **Configuration:** YAML loading, base inheritance, deep merging, required-key
  checks, and inheritance-cycle detection in `config.py`.
- **Logging and seeding:** shared logging setup and Python/NumPy/PyTorch seed
  handling in `logging_utils.py` and `seed.py`.
- **Schema and ingestion:** canonical schema validation, tweet/review ingestion,
  date normalization, source record IDs, data-quality reporting, and raw-data
  provenance in `data/schema.py` and `data/ingest.py`.
- **Cleaning:** normalization, empty/exact duplicate handling, and near-duplicate
  detection in `data/clean.py`.
- **Anonymisation:** identifier masking and batch audit reporting in
  `data/anonymise.py`.
- **Context:** sentence splitting and context-aware record construction in
  `data/context.py`.
- **Annotations:** annotation dataclasses, JSONL serialization, offset/label/
  context/privacy validation, and batch validation in `data/annotations.py`.
- **BIO processing:** character-offset/BIO alignment, ignored positions,
  reconstruction, and round-trip helpers in `data/bio.py`.
- **Dataset loaders:** intent, aspect-sentiment, and BIO example construction;
  aspect marking; label maps; and context input modes in `data/datasets.py`.
- **South African ingestion:** parquet schema validation, source IDs, date and
  bank handling, candidate filtering, promotional-account flags, bounded
  near-duplicate scanning, stratified sample selection, and annotation-record
  conversion in `data/ingest_south_africa.py` and `data/sa_candidate_filter.py`.
- **Models:** SVM pipelines and reloadable extractor metadata in
  `models/svm_baseline.py`; mask-aware BiLSTM intent/sentiment components in
  `models/bilstm_baseline.py`; and local/offline BERT tokenizer/model,
  sequence-classification, BIO alignment, aspect marking, and span reconstruction
  helpers in `models/bert_baseline.py`.
- **Training:** shared PyTorch training loop, class-weighted loss, gradient
  clipping, validation macro-F1 selection, early stopping, structured
  checkpoint/resume support, readiness checks, and run-artifact writing in
  `training/loop.py`, `training/readiness.py`, `training/supervised_gate.py`,
  `training/reproducibility.py`, and `training/baseline_runner.py`.
- **Evaluation:** classification, BIO, span, subgroup/regional/source/context,
  end-to-end tuple, ablation, and report-writing utilities in `evaluation/`.

### Scripts

The CLI and workflow scripts present are:

- `prepare_data.py`
- `prepare_south_africa_data.py`
- `resample_south_africa_v2.py`
- `create_annotation_sample.py`
- `annotation_app.py`
- `start_annotation_sessions.sh`
- `validate_annotations.py`
- `calculate_agreement.py`
- `adjudicate_annotations.py`
- `create_combined_gold.py`
- `create_splits.py`
- `check_training_readiness.py`
- `train_baselines.py`
- `audit_gold_data.py`
- `audit_combined_labels.py`
- `review_svm_artifacts.py`
- `scaffold_project.py`

These cover preparation, annotation, validation, agreement, adjudication,
combination, splitting, readiness checks, baseline dispatch, audits, and
artifact review.

### Tests

The repository contains focused tests for annotation/adjudication/agreement,
the Streamlit workflow, anonymisation, BIO alignment, cleaning, CLI behavior,
configuration, context, dates, dataset construction, evaluation metrics,
ingestion including South Africa, intent modes, logging, near duplicates,
feature exclusion, raw-data preservation, readiness, reproducibility,
sampling, scaffolding, schema, seeding, splitting, SVM, BiLSTM, BERT helpers,
the training loop, and validation CLI behavior.

The audit counted test functions statically using AST inspection. No full test
run was performed for this report, so this report makes no new pass/fail claim.
Existing documentation records a historical full-suite result of `327 passed,
1 skipped, 2 warnings`; that is a recorded historical claim, not a result of
this audit.

### Cluster directory

The cluster directory contains:

- `interactive_setup.sh`
- `pbs_train.sh`
- `run_banking_tasci_cuda.sh`
- `run_bilstm_combined_v2.sh`
- `run_svm_combined_v2.sh`
- `slurm_train.sh`

The generic Slurm/PBS scripts remain templates with placeholders. The
combined-v2 SVM script is CPU-oriented and loads a cluster Anaconda module. The
combined-v2 BiLSTM script targets the `biggpu` partition and `mscluster108`,
activates `.venv`, checks CUDA, runs readiness, and dispatches intent and
sentiment jobs sequentially.

## 5. Data and Annotation State

### Original/international pilot

Observed JSONL counts:

| File | Records | Observed status |
|---|---:|---|
| `pilot_unannotated.jsonl` | 600 | `completed` in the stored file despite its historical name; 150 intent values are missing |
| `pilot_annotator_a.jsonl` | 600 | 150 intent values missing |
| `pilot_annotator_b.jsonl` | 600 | 150 intent values missing |
| `pilot_adjudicated.jsonl` | 600 | completed; four intent classes represented |

The pilot source records are all classified as `international`; 407 originate
from `international_bank_tweets` and 193 from `bank_reviews`. The stored gold
has 1,253 aspects and 174 zero-aspect records. The gold validation artifact
records 600 valid and 0 invalid records.

The gold-quality audit identifies important research limitations: the original
annotator files were byte-identical, 150 `general_feedback` labels were bulk
assigned after missing intents, and the configured `suggestion`, `warning`, and
`churn_signal` intent classes had no support in the original 600-record gold.
Those findings are documentation-supported audit findings, not new labels or
corrections made here.

### South African sample and gold

The repository contains two 200-record unannotated South African samples:
`south_african_unannotated.jsonl` and `south_african_unannotated_v2.jsonl`.
The selected annotation input was reduced to 196 records in the annotation
workflow. The prepared South African corpus is documented as much larger than
the manual sample: the preparation report records 2,250,776 final canonical
rows and 2,086,851 customer-feedback candidates after processing the selected
2018--2022 source window. The manual annotation cap was 200, not a claim that
the prepared corpus contained only 200 records.

The South African files have distinct roles:

**Label-hidden inputs:**

- `south_african_annotation_input.jsonl` (196 records)
- `south_african_independent_input.jsonl` (196 records)

**Completed annotation files:**

- `south_african_annotator_a.jsonl` (196 records)
- `south_african_annotator_b.jsonl` (196 records)
- `south_african_annotator_a_comparison.jsonl` (196 records)
- `south_african_independent_annotator.jsonl` (196 records)

**Adjudicated outputs:**

- `south_african_adjudicated.jsonl` (196 records)
- `south_african_genuine_adjudicated.jsonl` (196 records)
- `south_african_adjudicated_v2.jsonl` (196 records)

The unannotated South African sample files contain 200 `not_started` records.
The label-hidden 196-record input was created after four records were removed
for quality reasons. The combined v2 gold file contains 796 valid completed
records: 600 international and 196 South African.

### Validation, agreement, and provenance

Stored validation artifacts include the original pilot, annotator, combined,
and South African validation reports. The combined v2 validation artifacts
record 796 valid and 0 invalid records, with 1,667 aspect annotations in the
revalidation output.

The South African genuine-agreement report records a genuinely independent
comparison on 196 records before adjudication:

- intent kappa: 0.8736;
- aspect-category kappa: 0.9904;
- aspect-sentiment kappa: 0.8750;
- exact-span agreement: 0.8010;
- token-level aspect F1: 0.8966;
- 48 records in the disagreement queue.

Later stored combined/distribution reports contain other agreement values,
including perfect agreement for copied/identical files. These must not be
treated as interchangeable. The genuine South African comparison and the
original copied pilot comparison have different provenance.

### Processed splits

The audit found split manifests for:

- `data/processed/`
- `data/processed/south_african/`
- `data/processed/south_african_v2/`
- `data/processed/combined_v2/`

The combined-v2 manifests are present and the stored reports describe them as
leakage-safe. The combined-v2 research-readiness report records these counts:

| Split | Record count |
|---|---:|
| Train | 556 |
| Validation | 122 |
| Test | 118 |
| Total | 796 |

The sentiment task expands records into aspect examples; the stored SVM report
records 1,178 train, 251 validation, and 238 test aspect examples.

## 6. Implemented versus Executed Model Work

### SVM

**Implemented:** TF-IDF/LinearSVC intent and aspect-sentiment baselines,
current-text and context-aware intent extractors, validation macro-F1 model
selection, reloadable artifacts, prediction writing, error analysis, subgroup
reports, and confusion matrices.

**Executed and evidenced:** the stored Phase 3B report and run artifacts record
Slurm job 50823 completing on 8 September 2026 on `stampede`/`mscluster22`.
The readiness gate passed before training. The two stored runs are:

- intent: `outputs/runs/20260908_054534_901414_1bd8b19a`
- sentiment: `outputs/runs/20260908_054546_120350_0d9ac5db`

Recorded SVM results:

| Task | Validation macro-F1 | Test accuracy | Test macro-F1 | Test n |
|---|---:|---:|---:|---:|
| Intent | 0.4612058704 | 0.6440677966 | 0.4283948604 | 118 |
| Sentiment | 0.6474400365 | 0.5714285714 | 0.5061415921 | 238 |

The stored report says test data was used after selection only. It also records
that the successful intent run used `current_only`; the context-aware intent
SVM was not trained. The report identifies minority-class and subgroup results
as exploratory.

### BiLSTM

**Implemented in source:** BiLSTM intent and marked-aspect sentiment models,
collation, vocabulary/encoding, shared training-loop integration, class weights,
gradient clipping, early stopping, and checkpoint support.

**Executed evidence:** documentation and prior session records state that the
combined-v2 BiLSTM job completed on the cluster and reached validation scores in
the approximate 0.51 range. The repository inventory inspected for this report
did not show BiLSTM run directories comparable to the two stored SVM runs, nor
stored BiLSTM metrics that can be independently quoted here. Accordingly, this
report classifies BiLSTM as **source-implemented and historically reported as
executed, but not independently artifact-verified by this audit**.

### BERT

**Implemented in source:** local/offline tokenizer and model loading, BIO token
alignment and span reconstruction, intent sequence classification, marked
sentiment sequence classification, and a `_train_bert` orchestration path in
`training/baseline_runner.py` using the shared PyTorch loop and artifact writer.

**Environment evidence:** prior stored execution output recorded successful
local tokenizer loading and a readiness-gate pass on combined v2, followed by an
older `NotImplementedError` in the BERT dispatcher. The current source contains
the orchestration implementation, but the inspected repository has no BERT run
directory, BERT metrics, BERT predictions, or BERT checkpoint proving a
completed training run.

Therefore BERT is classified as **implemented in current source but not
completed or validated as a research training run**. The optional
`transformers` dependency and local pretrained model remain environment
requirements.

### Proposed TASCI system

The repository contains configuration templates and evaluation utilities for
aspect extraction, contextual intent, sentiment, ablation, and end-to-end
metrics. The full proposed self-attention/BIO + GRU/context + integrated
sentiment TASCI training and inference system is **not evidenced as completed**.
The README marks the corresponding phases as not started or partial.

## 7. Cluster Execution State

The stored cluster documentation records:

- job 50753 remained pending in an unavailable `batch` partition;
- job 50817 failed before SVM training because `module` was unavailable in the
  batch shell;
- job 50823 completed successfully and produced the stored SVM artifacts;
- the BiLSTM script was later adjusted to target `biggpu`/`mscluster108`.

Those are historical recorded outcomes, not commands run during this audit.
No cluster job was submitted, cancelled, or queried during this audit.

The generic scheduler templates still contain placeholders and should not be
submitted unchanged. Cluster credentials are not stored in the repository.

## 8. Artifact and Reproducibility State

The two stored SVM run directories contain run configuration, environment,
label maps, split manifests, metrics, predictions, nested model/vectorizer/
encoder artifacts, extractor metadata, cluster metadata, error files, subgroup
metrics, confusion matrices, and reloadability records.

The stored SVM report notes artifact-schema gaps in the current writer: some
expected standalone files, such as separate validation/test metric files, are
not present, and some generic optional artifact warnings were logged. The
actual SVM model and prediction artifacts are present and the report records a
reload check on ten fixed test examples per model.

No BERT or BiLSTM run artifact set was found in the inspected `outputs/runs/`
tree. No claim of completed BERT/BiLSTM artifact reproducibility is made here.

## 9. Completed Work

The following are supported by source files and/or stored artifacts:

1. Repository scaffolding, packaging metadata, configuration loading, logging,
   seeding, and raw/prepared data conventions.
2. International and South African ingestion, cleaning, anonymisation, schema,
   annotation, BIO, context, and dataset-loader infrastructure.
3. Annotation UI and validation/agreement/adjudication/split CLI workflow.
4. South African sample preparation and a separate manual annotation workflow.
5. Combined v2 gold creation, stored validation, and leakage-safe manifests.
6. Readiness-gate implementation and recorded passing combined-v2 readiness.
7. SVM intent and sentiment implementation, cluster execution, metrics, and
   reloadable artifacts.
8. BiLSTM and BERT model/training infrastructure in source, with the execution
   qualifications documented above.
9. Focused test coverage across the major data, model, training, and CLI
   components. Historical test results are recorded but were not rerun here.

## 10. Partially Completed or Limited Work

- Research readiness is weaker than technical readiness. Stored audit reports
  distinguish a passing mechanical gate from insufficient class support and
  annotation-independence evidence in parts of the data.
- The original 600-record pilot has copied/identical annotator provenance and
  bulk-filled intent labels; it should not be presented as independent human
  reliability evidence.
- The South African independent comparison is stronger, but its 196-record gold
  is still a small sample relative to the prepared corpus.
- The context-aware intent SVM remains untrained in the stored Phase 3B result.
- BiLSTM execution is reported in prior records but lacks stored run artifacts
  in the inspected tree.
- BERT orchestration is present in source but lacks a completed, artifact-backed
  training run.
- The full TASCI model and end-to-end inference workflow are not evidenced as
  completed.
- Generic cluster scripts retain placeholders, and the default requirements do
  not install `transformers`.
- The README and some earlier completion reports retain historical “blocked”
  language that conflicts with the later combined-v2 and SVM artifacts.

## 11. Outstanding Work

The following items remain outstanding or require explicit research approval:

1. Decide whether the current gold data meets the study's research-quality
   requirements, especially minority intent/category support and provenance.
2. Expand and/or review annotations if reliable coverage of all configured
   intent and aspect-category labels is required.
3. Complete a properly artifact-backed BiLSTM run record if BiLSTM results are
   to be reported formally.
4. Execute and independently verify BERT intent and sentiment training only
   after confirming the local checkpoint, `transformers`, CUDA/device behavior,
   and artifact outputs.
5. Train the outstanding context-aware intent baseline if the context ablation
   is part of the research claims.
6. Implement and validate the proposed TASCI models and the end-to-end inference
   pipeline if the project scope includes Phases 4--5.
7. Perform planned ablations, regional analysis, error analysis, and final
   reporting using research-approved data and documented splits.
8. Reconcile stale README and historical status documents with the current
   combined-v2/SVM state without overwriting historical reports.
9. Improve artifact naming/metadata where the stored SVM report identifies
   schema gaps, while preserving completed model outputs.
10. Use the full prepared South African corpus for unsupervised/domain-adaptive
    work only through a separately specified pipeline; the present supervised
    gold labels cover only the manually annotated sample.

## 12. Final Status as of 25 September 2026

The Banking TASCI repository has a substantial and tested data/annotation/
baseline infrastructure. The combined v2 gold and split artifacts are present,
and SVM intent and sentiment baselines have recorded successful cluster runs
with stored metrics and reloadable artifacts.

The project is **not complete as a full TASCI research system**. The proposed
TASCI model, full inference workflow, context-aware intent comparison, and
artifact-backed BERT/BiLSTM research runs are not all complete. Technical
readiness should not be presented as proof of research readiness, especially
given the documented annotation provenance and minority-class limitations.
