# Banking TASCI

**Aspect-Based Sentiment Analysis and Contextual Intent Extraction from
User-Generated Banking Customer Reviews**

A reproducible research codebase that adapts the TASCI architecture to
banking customer feedback. The system extracts explicit aspect terms,
predicts customer intent using contextual signals, and classifies
aspect-level sentiment using the predicted intent representation.

---

## Current Phase: 3B Baselines — Partial, with Corrections Outstanding

Phases 1 and 2 are complete. Phase 3A baseline infrastructure is implemented.
Combined Gold Version 2 and leakage-safe manifests exist, and the technical
readiness gate has passed for the combined data. SVM intent and sentiment
baselines have completed cluster runs with stored artifacts. The context-aware
SVM intent baseline remains outstanding; BiLSTM and BERT do not yet have
complete repository-verifiable run artifact sets. The full TASCI system is not
complete.

### Status as of 25 September 2026

- Combined Gold Version 2: 796 records, technically validated, with 556/122/118
  train/validation/test manifests.
- South African component: genuinely independently annotated and manually
  adjudicated; the original 600-record component was technically validated but
  did not have genuine independent annotation.
- SVM intent and sentiment: completed and reloadable; the completed intent run
  used current-text-only input.
- Context-aware SVM intent: not trained.
- BiLSTM and BERT: source infrastructure exists, but complete run artifacts were
  not verified in the repository audit.
- Research readiness remains limited by annotation provenance and minority-class
  support. Combined-model results must be interpreted with this limitation.

See [Gold-Data Blocker](#gold-data-blocker) below.

---

## Research Goals

1. Accurately extract banking aspect terms using self-attention BIO labelling.
2. Classify customer intent using a GRU model with previous-sentence context.
3. Determine whether context improves intent prediction.
4. Determine whether intent integration improves aspect-level sentiment
   classification.
5. Compare the full TASCI pipeline with SVM, BiLSTM, and BERT baselines.
6. Report international and South African banking feedback separately.

---

## Repository Layout

```
banking-tasci/
├── configs/              YAML configuration files
│   ├── base.yaml         Base config (seed, anonymisation, near-dup, paths)
│   ├── baselines/        One config per baseline task (svm, bilstm, bert)
│   ├── aspect.yaml       Proposed aspect extractor config template
│   ├── intent.yaml       Proposed intent model config template
│   ├── sentiment.yaml    Proposed sentiment classifier config template
│   └── full_pipeline.yaml  End-to-end inference config template
├── data/
│   ├── raw/              Place original CSV files here (read-only)
│   ├── interim/          Prepared canonical data (prepared.csv)
│   ├── annotations/      Annotation JSONL files
│   └── processed/        Final train/validation/test split manifests
├── docs/                 Detailed documentation
├── outputs/              Experiment artifacts (reports, run directories)
├── scripts/              CLI entry points
├── src/banking_tasci/    Python package
│   ├── data/             Ingestion, cleaning, anonymisation, annotations, BIO
│   ├── models/           Baseline models (SVM, BiLSTM, BERT)
│   ├── training/         Shared loop, readiness gate, reproducibility
│   ├── evaluation/       Metric functions
│   └── inference/        (Planned) End-to-end inference pipeline
├── tests/                pytest test suite
└── cluster/              Cluster scheduler templates
```

---

## Data Directory Convention

| Directory | Contents |
|---|---|
| `data/raw/` | Original, unmodified CSV source files. Never overwritten. |
| `data/interim/` | `prepared.csv` — cleaned, anonymised, canonical records. |
| `data/annotations/` | Annotation JSONL files (unannotated pilot and, later, annotated files). |
| `data/processed/` | Split manifests (`train_manifest.csv`, etc.) created after adjudication. |
| `outputs/` | Data quality reports, sample reports, experiment run directories. |

Place the raw source files **exactly** at:
- `data/raw/sampledbanktweet.csv`
- `data/raw/bank_reviews3.csv`

Do not place them in the repository root.

---

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If the cluster blocks internet access, build a wheelhouse on another Linux
machine first. See [docs/cluster_guide.md](docs/cluster_guide.md).

---

## Data Preparation

```bash
python scripts/prepare_data.py \
  --tweets data/raw/sampledbanktweet.csv \
  --reviews data/raw/bank_reviews3.csv \
  --output data/interim/prepared.csv \
  --report outputs/data_report.json
```

This validates source schemas, normalises text, removes empty and exact-
duplicate records, detects near-duplicates (flagged by default, see
`configs/base.yaml` → `near_dup`), anonymises identifiers, and produces
a JSON data-quality report.

---

## Annotation Workflow

After data preparation, follow `docs/annotation_workflow.md`:

1. Generate the pilot sample (already done — `data/annotations/pilot_unannotated.jsonl`).
2. Two annotators label all 600 records independently using the Streamlit app:
   ```bash
   streamlit run scripts/annotation_app.py
   ```
3. Validate each annotator's output:
   ```bash
   python scripts/validate_annotations.py \
     --input data/annotations/pilot_annotator_a.jsonl \
     --output outputs/annotation_validation_report_a.json
   ```
4. Calculate inter-annotator agreement:
   ```bash
   python scripts/calculate_agreement.py \
     --annotator-a data/annotations/pilot_annotator_a.jsonl \
     --annotator-b data/annotations/pilot_annotator_b.jsonl \
     --output outputs/inter_annotator_agreement.json
   ```
5. Adjudicate disagreements interactively:
   ```bash
   python scripts/adjudicate_annotations.py \
     --annotator-a data/annotations/pilot_annotator_a.jsonl \
     --annotator-b data/annotations/pilot_annotator_b.jsonl \
     --adjudicator-id lead_annotator \
     --output data/annotations/pilot_adjudicated.jsonl
   ```
6. Create leakage-safe splits:
   ```bash
   python scripts/create_splits.py \
     --input data/annotations/pilot_adjudicated.jsonl \
     --output-dir data/processed \
     --train-ratio 0.70 --validation-ratio 0.15 --test-ratio 0.15 --seed 42
   ```

---

## Readiness Gate

Every training command checks the supervised-readiness gate before building
any model. To check readiness without training:

```bash
python scripts/check_training_readiness.py \
  --annotations data/annotations/pilot_adjudicated.jsonl \
  --split-dir data/processed
```

Training is blocked if the adjudicated gold file or split manifests are absent.

---

## Baseline Training

Once the readiness gate passes:

```bash
# SVM intent baseline
python scripts/train_baselines.py \
  --model svm --task intent \
  --config configs/baselines/svm_intent.yaml

# BiLSTM sentiment baseline
python scripts/train_baselines.py \
  --model bilstm --task sentiment \
  --config configs/baselines/bilstm_sentiment.yaml

# BERT BIO aspect baseline (requires local pretrained model directory)
python scripts/train_baselines.py \
  --model bert --task aspect \
  --config configs/baselines/bert_aspect.yaml
```

All baselines select the best checkpoint by **validation macro-F1 only**.
The test split is evaluated once, after selection, and never used for
model selection.

---

## Gold-Data Blocker

The 600-record pilot (`data/annotations/pilot_unannotated.jsonl`) is
**unannotated**. Every record has:
- `annotation_status: "not_started"`
- `intent: null`
- `aspects: []`

No research model has been trained. No predictions or metrics exist.
The readiness gate correctly blocks all training commands.

To unblock: complete steps 2–6 of the Annotation Workflow above.

---

## Future TASCI Phases

| Phase | Description | Status |
|---|---|---|
| 4 | Self-attention aspect extractor, GRU intent model, GloVe+Transformer sentiment classifier | Not started |
| 5 | Full integrated inference pipeline, batch prediction, structured output | Not started |
| 6 | Ablation experiments, regional analysis, error analysis, final reports | Not started |
| 7 | Cluster packaging (already partially ready — see `cluster/`) | Partial |

Configuration templates for Phases 4–5 are in `configs/aspect.yaml`,
`configs/intent.yaml`, `configs/sentiment.yaml`, and
`configs/full_pipeline.yaml`.

---

## Cluster Usage

Target cluster:
```
ssh rmavhengani@146.141.21.100
```

See [docs/cluster_guide.md](docs/cluster_guide.md) for:
- offline dependency installation (wheelhouse);
- data transfer commands;
- Slurm and PBS job templates (in `cluster/`);
- checkpoint resume instructions.

Do not commit credentials, private keys, or access tokens.

---

## Running Tests

```bash
pytest -q
```

Tests use only synthetic in-memory fixtures. No raw data files are read
and no research artifacts are generated. The BERT offline smoke test
requires `transformers` to be installed; it is skipped otherwise.

---

## Documentation Index

| Document | Purpose |
|---|---|
| [docs/annotation_guidelines.md](docs/annotation_guidelines.md) | Labelling rules for aspect spans, categories, sentiments, and intents |
| [docs/annotation_workflow.md](docs/annotation_workflow.md) | Step-by-step annotation and adjudication runbook |
| [docs/data_dictionary.md](docs/data_dictionary.md) | Field definitions for Canonical_Record and Annotation_Record |
| [docs/cluster_guide.md](docs/cluster_guide.md) | Cluster setup, job submission, and resume instructions |
| [docs/phase_2_completion_report.md](docs/phase_2_completion_report.md) | Phase 2 deliverables and test results |
| [docs/github_copilot_phase_3a_completion_report.md](docs/github_copilot_phase_3a_completion_report.md) | Phase 3A deliverables and test results |
