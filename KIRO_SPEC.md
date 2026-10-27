# Kiro Specification: Banking TASCI Pipeline

## 1. Project Title

**Aspect-Based Sentiment Analysis and Contextual Intent Extraction from User-Generated Banking Customer Reviews**

## 2. Purpose

Build a reproducible research codebase that adapts the TASCI architecture to banking customer feedback. The system must:

1. extract explicit banking aspect terms using self-attention and BIO sequence labelling;
2. predict customer intent using a GRU-based contextual sequence-to-sequence model;
3. classify sentiment for each extracted aspect using GloVe embeddings, a Transformer encoder, and the predicted intent representation;
4. compare the proposed pipeline with SVM, BiLSTM, and BERT baselines;
5. evaluate component-level, end-to-end, context-aware, regional, and ablation performance;
6. run locally and on the `mscluster` environment accessed through SSH as `rmavhengani@146.141.21.100`.

Do not store SSH passwords, private keys, API tokens, or credentials in the repository.

---

## 3. Research Questions Implemented by the Software

The codebase must support experiments answering:

1. How accurately can self-attention sequence labelling extract banking aspect terms?
2. How accurately can a GRU-based model classify customer intent?
3. Does previous-sentence or conversational context improve intent prediction?
4. Does intent integration improve aspect-level sentiment classification?
5. How does the full pipeline compare with SVM, BiLSTM, and BERT baselines?
6. Which model components make the largest contribution to performance?
7. How do international and South African banking feedback results differ?

---

## 4. Input Data

### 4.1 Existing files

The project starts with:

- `sampledbanktweet.csv`
  - approximately 10,000 rows;
  - required source column: `text`;
  - customer tweets are noisy and may contain mentions, URLs, transaction references, account-like numbers, hashtags, Nigerian Pidgin, abbreviations, and unrelated posts;
  - no gold aspect, sentiment, or intent labels.

- `bank_reviews3.csv`
  - approximately 1,000 rows;
  - expected columns:
    - `author`
    - `date`
    - `address`
    - `bank`
    - `rating`
    - `review_title_by_user`
    - `review`
    - `bank_image`
    - `rating_title_by_user`
    - `useful_count`
  - ratings are metadata and must not be treated as gold aspect-level sentiment labels;
  - no gold aspect spans or intent labels.

Additional sources may later include:

- South African bank tweets;
- ethically permitted and anonymised South African Hellopeter reviews.

### 4.2 Canonical prepared record

All source records must be converted to a common schema:

```json
{
  "record_id": "stable-hash",
  "source": "international_bank_tweets",
  "region": "international",
  "bank": null,
  "rating": null,
  "title": "",
  "text": "current sentence or review text",
  "previous_text": "[NO_CONTEXT]",
  "context_available": false,
  "thread_id": null,
  "created_at": null,
  "split": null
}
```

Requirements:

- `record_id` must be deterministic for the same source and normalised text.
- Preserve raw data in a read-only location.
- Write all transformed data to new files.
- Never overwrite original CSV files.
- Log counts before and after each data-cleaning stage.

---

## 5. Annotation Schema

The training pipeline must not invent labels. Models may only be trained on manually annotated gold labels or explicitly marked weak labels used in a separate weak-supervision experiment.

### 5.1 Aspect spans

Each explicit aspect must include character offsets:

```json
{
  "term": "mobile app",
  "start": 4,
  "end": 14,
  "category": "digital_banking",
  "sentiment": "negative"
}
```

Rules:

- `start` is inclusive.
- `end` is exclusive.
- `text[start:end]` must equal `term` after the agreed Unicode-normalisation policy.
- Multiple aspects are allowed per record.
- Overlapping aspect spans are not allowed in version 1.
- Implicit aspects may be stored separately but must not be included in BIO training unless a clear representation is defined.

### 5.2 BIO labels

Generate token-level labels:

- `B-ASP`: first token in an aspect span;
- `I-ASP`: following token in the same aspect span;
- `O`: token outside an aspect span;
- `-100`: ignored padded or non-first subword positions when required by the selected tokenizer policy.

The offset-to-BIO conversion must be deterministic and unit tested.

### 5.3 Aspect categories

Use these initial categories:

- `customer_support`
- `digital_banking`
- `transactions`
- `cards`
- `accounts`
- `fees`
- `fraud_security`
- `branch_service`
- `general_service`

Kiro must place label definitions and positive/negative examples in `docs/annotation_guidelines.md`.

### 5.4 Aspect sentiment

Allowed labels:

- `negative`
- `neutral`
- `positive`

Do not use `mixed` as an aspect label. A review with mixed opinions must be represented through separate aspect--sentiment pairs. If the same aspect term receives conflicting sentiment within one record, flag it for adjudication.

### 5.5 Customer intent

Use one dominant intent per sentence or review in version 1:

- `complaint`
- `compliment`
- `request_for_assistance`
- `suggestion`
- `warning`
- `churn_signal`
- `general_feedback`

Store ambiguous cases with:

```json
{
  "intent": "complaint",
  "intent_ambiguous": true,
  "alternative_intent": "request_for_assistance"
}
```

### 5.6 Context status

Every sample must have:

- `context_available=true` when a genuine preceding sentence or preceding post is available;
- `context_available=false` for isolated records;
- `previous_text="[NO_CONTEXT]"` for isolated records.

Do not create artificial preceding context by selecting an unrelated row.

---

## 6. Repository Structure

Create the following structure:

```text
banking-tasci/
├── README.md
├── pyproject.toml
├── requirements.txt
├── .gitignore
├── Makefile
├── configs/
│   ├── base.yaml
│   ├── aspect.yaml
│   ├── intent.yaml
│   ├── sentiment.yaml
│   ├── full_pipeline.yaml
│   └── cluster.yaml
├── data/
│   ├── raw/.gitkeep
│   ├── interim/.gitkeep
│   ├── processed/.gitkeep
│   └── annotations/.gitkeep
├── docs/
│   ├── annotation_guidelines.md
│   ├── data_dictionary.md
│   ├── experiment_protocol.md
│   └── cluster_guide.md
├── src/banking_tasci/
│   ├── __init__.py
│   ├── config.py
│   ├── logging_utils.py
│   ├── seed.py
│   ├── data/
│   │   ├── ingest.py
│   │   ├── clean.py
│   │   ├── anonymise.py
│   │   ├── context.py
│   │   ├── annotations.py
│   │   ├── bio.py
│   │   ├── split.py
│   │   ├── vocabulary.py
│   │   └── datasets.py
│   ├── models/
│   │   ├── aspect_self_attention.py
│   │   ├── intent_gru_seq2seq.py
│   │   ├── sentiment_transformer.py
│   │   ├── tasci_pipeline.py
│   │   ├── svm_baseline.py
│   │   ├── bilstm_baseline.py
│   │   └── bert_baseline.py
│   ├── training/
│   │   ├── losses.py
│   │   ├── trainer.py
│   │   ├── checkpoint.py
│   │   └── early_stopping.py
│   ├── evaluation/
│   │   ├── aspect_metrics.py
│   │   ├── classification_metrics.py
│   │   ├── end_to_end.py
│   │   ├── ablation.py
│   │   ├── regional.py
│   │   └── reports.py
│   └── inference/
│       ├── pipeline.py
│       └── schema.py
├── scripts/
│   ├── prepare_data.py
│   ├── create_annotation_sample.py
│   ├── validate_annotations.py
│   ├── calculate_agreement.py
│   ├── train_aspect.py
│   ├── train_intent.py
│   ├── train_sentiment.py
│   ├── train_full_pipeline.py
│   ├── train_baselines.py
│   ├── run_ablation.py
│   ├── evaluate.py
│   └── predict.py
├── cluster/
│   ├── slurm_train.sh
│   ├── pbs_train.sh
│   └── interactive_setup.sh
└── tests/
    ├── test_ingest.py
    ├── test_anonymise.py
    ├── test_context.py
    ├── test_bio.py
    ├── test_splits.py
    ├── test_aspect_model.py
    ├── test_intent_model.py
    ├── test_sentiment_model.py
    ├── test_pipeline.py
    └── test_metrics.py
```

---

## 7. Technology Requirements

Use:

- Python 3.10 or later;
- PyTorch;
- pandas and NumPy;
- scikit-learn;
- Hugging Face Transformers and tokenizers;
- seqeval for BIO evaluation;
- PyYAML;
- pytest;
- tqdm;
- standard Python logging.

Optional:

- spaCy for sentence segmentation only if its model is installed and version-pinned;
- TensorBoard or MLflow for experiment tracking if available on the cluster.

Do not require internet access during training. Pretrained assets must be downloaded lawfully in advance and copied to the cluster.

---

## 8. Privacy and Anonymisation

Create deterministic preprocessing that replaces:

- email addresses with `[EMAIL]`;
- URLs with `[URL]`;
- user mentions with `[USER]`;
- long account/reference-like digit strings with `[ACCOUNT_OR_REFERENCE]`;
- phone-like strings with `[PHONE]`;
- transaction amounts with `[AMOUNT]` only if amount information is not required by a later task.

Requirements:

- Do not remove negation or intensifiers.
- Retain meaningful hashtags after removing the `#` symbol or represent them consistently.
- Preserve emojis if they carry sentiment; map them consistently if an emoji library is added.
- Produce an anonymisation audit containing counts only, never the replaced values.
- Add unit tests for all anonymisation patterns.

---

## 9. Data Preparation

Implement CLI:

```bash
python scripts/prepare_data.py \
  --tweets data/raw/sampledbanktweet.csv \
  --reviews data/raw/bank_reviews3.csv \
  --output data/interim/prepared.csv \
  --report outputs/data_report.json
```

The script must:

1. validate required columns;
2. normalise encodings and whitespace;
3. anonymise sensitive values;
4. remove empty records;
5. remove exact duplicates;
6. identify near duplicates using a configurable threshold;
7. retain provenance fields;
8. create deterministic IDs;
9. segment multi-sentence reviews without destroying the full review;
10. assign `[NO_CONTEXT]` only where genuine context is absent;
11. emit a JSON data-quality report;
12. fail with a helpful message when the schema is invalid.

---

## 10. Annotation Tooling

Implement:

```bash
python scripts/create_annotation_sample.py \
  --input data/interim/prepared.csv \
  --output data/annotations/pilot.csv \
  --size 600 \
  --seed 42
```

Sampling must preserve source diversity and, where available, region and rating diversity.

Implement:

```bash
python scripts/validate_annotations.py \
  --input data/annotations/pilot_annotated.jsonl
```

Validation must check:

- allowed labels;
- valid character offsets;
- matching aspect text;
- equal numbers of aspect terms, categories, and sentiments;
- non-overlapping spans;
- valid context fields;
- one dominant intent;
- absence of raw identifiers after anonymisation.

Implement inter-annotator agreement:

```bash
python scripts/calculate_agreement.py \
  --annotator-a data/annotations/pilot_a.jsonl \
  --annotator-b data/annotations/pilot_b.jsonl \
  --output outputs/agreement.json
```

Report:

- Cohen's Kappa for intent;
- Cohen's Kappa for aspect category;
- Cohen's Kappa for sentiment;
- exact-span agreement;
- token-level aspect F1;
- disagreement counts by label.

---

## 11. Split Strategy and Leakage Prevention

Create train, validation, and test splits only after annotation validation.

Default ratios:

- train: 70%;
- validation: 15%;
- test: 15%.

Requirements:

- stratify by intent and sentiment where possible;
- preserve region/source distributions where possible;
- keep duplicate and near-duplicate groups in one split;
- keep sentences from the same review or thread in one split;
- keep records from the same identifiable author in one split when author IDs are lawfully retained as hashed grouping IDs;
- save split manifests containing record IDs;
- never tune models on the test set.

---

## 12. Model A: Self-Attention Aspect Extractor

Implement a PyTorch token classifier based on the TASCI aspect-extraction stage.

Inputs:

- `input_ids`: `[batch, sequence]`;
- `attention_mask`: `[batch, sequence]`;
- `bio_labels`: `[batch, sequence]`.

Architecture:

1. token embedding layer;
2. positional encoding;
3. configurable Transformer encoder using multi-head self-attention;
4. dropout;
5. linear token-classification head;
6. softmax only for inference, not before `CrossEntropyLoss`.

Output labels:

- `O`
- `B-ASP`
- `I-ASP`

Loss:

- masked cross entropy, ignoring `-100`.

Evaluation:

- token precision, recall, and F1;
- exact-span precision, recall, and F1;
- seqeval classification report;
- examples of false boundary predictions.

Acceptance criteria:

- forward pass works for variable batch and sequence sizes;
- padded tokens are ignored;
- subword-to-word alignment is deterministic;
- extracted spans convert back to correct character offsets;
- overfit test on a tiny batch succeeds.

---

## 13. Model B: GRU Contextual Intent Extractor

Implement the TASCI-style contextual intent model.

Inputs:

- current sentence IDs and mask;
- previous sentence IDs and mask;
- `context_available` flag;
- intent label.

Architecture:

1. shared or separately configurable embedding layer;
2. GRU encoder for previous context;
3. GRU encoder for current sentence;
4. attention from the current representation over previous hidden states;
5. context vector;
6. concatenation of current summary and context vector;
7. projection and dropout;
8. intent classification head.

No-context handling:

- isolated records must use a trainable `[NO_CONTEXT]` representation or a masked zero-context vector;
- no attention softmax may be computed over an entirely masked row in a way that produces NaN values;
- compare current-only and context-aware modes.

Output labels:

- seven intent categories defined earlier.

Evaluation:

- accuracy;
- macro and weighted precision, recall, and F1;
- confusion matrix;
- context-available metrics;
- no-context metrics.

Acceptance criteria:

- no NaN values on no-context batches;
- model supports mixed context/no-context samples in one batch;
- overfit test on a tiny sample succeeds;
- saved checkpoint reloads with identical predictions in evaluation mode.

---

## 14. Model C: Intent-Aware Aspect Sentiment Classifier

Implement the TASCI-style sentiment stage.

Inputs:

- current sentence token IDs and mask;
- one aspect mask or span per instance;
- predicted or gold intent vector;
- sentiment label.

Architecture:

1. initialise embedding table from GloVe when configured;
2. allow embeddings to be frozen or fine-tuned;
3. aggregate aspect token embeddings;
4. process sentence/aspect representation through a Transformer encoder;
5. project intent representation to a compatible dimension;
6. concatenate aspect and intent representations;
7. apply dropout and linear sentiment classifier.

Output labels:

- negative;
- neutral;
- positive.

Requirements:

- support multiple aspects by expanding one review into one model instance per aspect;
- permit gold intent, predicted intent, or no intent;
- permit gold aspect spans or predicted aspect spans;
- never add incompatible vectors without an explicit projection;
- use logits with `CrossEntropyLoss`.

Evaluation:

- accuracy;
- macro and weighted precision, recall, and F1;
- class-specific metrics;
- gold-aspect performance;
- predicted-aspect performance;
- gold-intent versus predicted-intent performance.

---

## 15. Full TASCI-Style Pipeline

Implement an orchestration class that performs:

```text
raw text
  -> preprocessing and tokenisation
  -> aspect extraction
  -> context construction
  -> intent extraction
  -> one instance per extracted aspect
  -> intent-aware aspect sentiment classification
  -> structured predictions
```

Output schema:

```json
{
  "record_id": "abc123",
  "intent": {
    "label": "request_for_assistance",
    "confidence": 0.82,
    "context_available": true
  },
  "aspects": [
    {
      "term": "mobile app",
      "start": 4,
      "end": 14,
      "category": "digital_banking",
      "sentiment": "negative",
      "confidence": 0.91
    }
  ]
}
```

Requirements:

- confidence scores must be calibrated probabilities or clearly labelled uncalibrated softmax scores;
- preserve original record IDs;
- batch inference must be supported;
- inference must not require gold labels;
- empty-aspect results must be valid outputs rather than errors;
- ambiguous or low-confidence results must be flaggable using configurable thresholds.

---

## 16. Baseline Models

### 16.1 SVM

Implement TF--IDF plus linear SVM baselines for:

- intent classification;
- document sentiment or aspect sentiment when one instance per aspect is available.

### 16.2 BiLSTM

Implement a BiLSTM baseline for:

- intent classification;
- aspect sentiment classification.

### 16.3 BERT

Implement a Hugging Face BERT baseline for:

- BIO token classification;
- intent sequence classification;
- aspect sentiment classification using marked aspect spans.

All baselines must use the same split manifests as the proposed model.

---

## 17. Training Requirements

Configuration must control:

- random seed;
- batch size;
- learning rate;
- epochs;
- optimiser;
- weight decay;
- dropout;
- hidden size;
- number of attention heads;
- number of Transformer layers;
- maximum sequence length;
- gradient clipping;
- early stopping patience;
- label mappings;
- GloVe path;
- pretrained-model path;
- output directory;
- device.

Training requirements:

- deterministic seeds where supported;
- GPU if available, otherwise CPU;
- automatic checkpointing by validation macro-F1;
- early stopping;
- gradient clipping;
- class weights configurable for imbalanced classes;
- progress logging per epoch;
- save complete config with each run;
- save label mappings with checkpoints;
- resume from checkpoint;
- do not overwrite previous runs;
- produce machine-readable metrics JSON and human-readable Markdown reports.

---

## 18. Evaluation and Ablation Experiments

Implement these experiments:

1. full pipeline;
2. no intent integration;
3. current-sentence-only intent;
4. previous plus current context;
5. no Transformer sentiment encoder;
6. gold aspect spans;
7. predicted aspect spans;
8. gold intent;
9. predicted intent;
10. international-only test subset;
11. South-African-only test subset;
12. context-available test subset;
13. no-context test subset.

End-to-end metrics:

- exact aspect span plus correct sentiment;
- exact aspect span, correct aspect category, and correct sentiment;
- complete aspect, sentiment, and intent tuple;
- record-level percentage with all tuples correct.

Export:

- `metrics.json`;
- `classification_report.md`;
- `confusion_matrix.csv`;
- `errors.jsonl`;
- `predictions.jsonl`;
- comparison summary for all experiments.

---

## 19. Cluster Support

Target login:

```bash
ssh rmavhengani@146.141.21.100
```

Kiro must not attempt to make the SSH connection automatically or request credentials. It must generate instructions and scheduler templates.

### 19.1 Scheduler detection

Document:

```bash
command -v sbatch || command -v qsub || echo "No supported scheduler detected"
```

### 19.2 Slurm template

Create `cluster/slurm_train.sh` with configurable placeholders for:

- job name;
- partition;
- GPU count;
- CPU count;
- memory;
- wall time;
- log directory;
- virtual environment path;
- config path.

Do not assume the actual partition name.

### 19.3 PBS template

Create `cluster/pbs_train.sh` with equivalent placeholders. Do not assume queue or GPU resource syntax beyond clearly marked variables.

### 19.4 Environment

Document:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If the cluster blocks internet access, document how to build a wheelhouse on another Linux machine and copy it with `scp`.

### 19.5 Data transfer

Document commands to run from the local machine:

```bash
scp -r banking-tasci rmavhengani@146.141.21.100:~/
```

Do not hard-code local Windows paths.

---

## 20. CLI Commands

The following commands must work:

```bash
python scripts/prepare_data.py --config configs/base.yaml
python scripts/create_annotation_sample.py --config configs/base.yaml
python scripts/validate_annotations.py --input data/annotations/pilot.jsonl
python scripts/calculate_agreement.py --config configs/base.yaml
python scripts/train_aspect.py --config configs/aspect.yaml
python scripts/train_intent.py --config configs/intent.yaml
python scripts/train_sentiment.py --config configs/sentiment.yaml
python scripts/train_full_pipeline.py --config configs/full_pipeline.yaml
python scripts/train_baselines.py --config configs/base.yaml
python scripts/run_ablation.py --config configs/full_pipeline.yaml
python scripts/evaluate.py --run-dir outputs/runs/<run-id>
python scripts/predict.py --checkpoint outputs/runs/<run-id>/best.pt --input data/example.jsonl
```

Each CLI must:

- have `--help`;
- validate paths;
- return a non-zero exit code for invalid inputs;
- use logging instead of uncontrolled print statements;
- write outputs under a configured directory.

---

## 21. Testing Requirements

Use pytest.

Minimum tests:

1. source CSV schema validation;
2. anonymisation patterns;
3. deterministic record IDs;
4. sentence-context construction;
5. `[NO_CONTEXT]` handling;
6. character-offset validation;
7. character-offset-to-BIO conversion;
8. BIO-to-span reconstruction;
9. split leakage prevention;
10. aspect model tensor shapes;
11. no-context intent model without NaNs;
12. sentiment model with multiple aspects;
13. full-pipeline inference with no aspects;
14. checkpoint save/reload consistency;
15. metric correctness on known examples;
16. tiny-batch overfit tests for all neural components.

Run:

```bash
pytest -q
```

Acceptance threshold:

- all unit tests pass;
- no failing lint/type checks if configured;
- model smoke tests pass on CPU;
- CUDA smoke test runs when GPU is available.

---

## 22. Reproducibility

Every experiment directory must contain:

```text
config.yaml
environment.txt
git_commit.txt
label_maps.json
train_manifest.csv
validation_manifest.csv
test_manifest.csv
metrics.json
best_checkpoint.pt
training_log.txt
predictions.jsonl
```

Record:

- Python version;
- PyTorch version;
- CUDA version where applicable;
- GPU model;
- package versions;
- seed;
- start and end times;
- hostname;
- source-data checksums.

Do not record personal credentials or raw sensitive values.

---

## 23. Coding Standards

- Use type hints on public functions.
- Add docstrings to modules, classes, and public methods.
- Keep functions focused and testable.
- Separate data, model, training, and evaluation logic.
- Do not place business logic only in notebooks.
- Notebooks may be added for exploration but must call reusable package functions.
- Follow PEP 8.
- Use explicit exceptions with actionable messages.
- Do not silently continue after malformed annotations.
- Avoid data leakage from ratings, titles, source names, or future context unless explicitly included in an experiment.
- Do not use the review rating as an input feature for the primary text model.

---

## 24. Implementation Phases

### Phase 1: Foundation

Deliver:

- repository structure;
- configuration system;
- logging and seed utilities;
- data ingestion;
- anonymisation;
- data-quality report;
- tests.

### Phase 2: Annotation Pipeline

Deliver:

- annotation sample generator;
- annotation guidelines;
- annotation validator;
- BIO conversion;
- agreement calculation;
- split manifests;
- tests.

### Phase 3: Baselines

Deliver:

- SVM;
- BiLSTM;
- BERT;
- common evaluation reports.

### Phase 4: Proposed Components

Deliver in order:

1. self-attention aspect extractor;
2. GRU contextual intent extractor;
3. intent-aware aspect sentiment classifier;
4. component training scripts;
5. tests and overfit checks.

### Phase 5: Integration

Deliver:

- full TASCI-style pipeline;
- checkpoint composition;
- batch inference;
- structured prediction output;
- end-to-end metrics.

### Phase 6: Experiments

Deliver:

- all ablations;
- regional comparisons;
- context comparisons;
- error analysis;
- final report files.

### Phase 7: Cluster Packaging

Deliver:

- Slurm and PBS templates;
- cluster guide;
- offline dependency guidance;
- resume-from-checkpoint instructions.

---

## 25. Required Kiro Workflow

Kiro must work incrementally.

For each phase:

1. describe the files to create or modify;
2. implement only that phase;
3. run unit tests;
4. report commands executed and results;
5. list assumptions or blockers;
6. do not continue to the next phase while tests fail;
7. never fabricate training metrics;
8. never generate synthetic gold annotations unless explicitly requested and clearly marked as synthetic.

Kiro should begin with **Phase 1: Foundation**, not full model training.

---

## 26. Definition of Done

The project is complete when:

- all data preparation and privacy tests pass;
- annotation files validate successfully;
- inter-annotator agreement reports are generated;
- all three proposed model components train and evaluate;
- all baselines train on the same splits;
- full pipeline produces structured predictions;
- gold-aspect and predicted-aspect metrics are reported;
- context and no-context metrics are reported;
- no-intent ablation is reported;
- international and South African subsets are reported separately;
- experiments are reproducible from saved configs and manifests;
- cluster templates and documentation are complete;
- no credentials or raw sensitive identifiers are committed.

---

## 27. First Task for Kiro

Start with the following request:

> Implement Phase 1 of `KIRO_SPEC.md`. Create the repository structure, configuration loader, deterministic seed utility, logging utility, source CSV schema validation, anonymisation module, canonical data-ingestion pipeline, data-quality report, CLI entry point, and pytest coverage. Do not implement the neural models yet. Use the exact input schemas in this specification, preserve original files, and ensure all tests pass before proceeding.
