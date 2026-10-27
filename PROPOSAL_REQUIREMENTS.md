# Research Proposal Requirements

**Project:** Semi-Supervised Intent-Aware Aspect-Based Sentiment Analysis of International and South African Banking Feedback  
**Student:** Rotondwa Mavhengani  
**Student number:** 2114834  
**Degree:** Honours in Computer Science  
**Supervisor:** Dr Seun Olukanmi  
**Institution:** University of the Witwatersrand, School of Computer Science and Applied Mathematics  
**Document status:** Authoritative requirements for rewriting and validating the research proposal

## 1. Purpose

The proposal must describe a feasible low-label research design that uses large unlabelled banking corpora for self-supervised domain adaptation and a smaller human-audited gold corpus for supervised fine-tuning, validation, and held-out testing.

The central research goal is:

> To determine whether self-supervised banking-domain adaptation and predicted customer intent improve aspect-level sentiment classification for international and South African banking feedback.

The proposal must keep these two research questions separate:

1. Does genuine preceding context improve customer-intent classification?
2. Does predicted customer intent improve aspect-level sentiment classification?

A positive result for one question must not be treated as proof of the other.

## 2. Required Proposal Title

Use the following title unless the supervisor requests another version:

**Semi-Supervised Intent-Aware Aspect-Based Sentiment Analysis of International and South African Banking Feedback**

The term **feedback** must be used instead of **reviews** because the study includes tweets and reviews.

## 3. Required Document Format

The proposal must be supplied as one compilable LaTeX file.

Required characteristics:

- A4 paper.
- 11-point or the current approved Wits template font size.
- Wits title page.
- Academic declaration.
- Wits-style generative AI declaration page in table form.
- Acknowledgements on a separate page.
- Abstract on a separate page.
- Table of contents on a separate page.
- Every main chapter must start on a new page.
- Author-year citations in the proposal body.
- No citations in the abstract.
- Embedded bibliography using `filecontents*`, unless the official Wits template requires an external BibTeX file.
- Tables must use valid LaTeX ampersands (`&`), not HTML entities such as `&amp;` or `&gt;`.
- The proposal must compile without missing citation keys.

## 4. Required Front Matter

The proposal must include:

1. Title page.
2. Abstract.
3. Academic declaration.
4. Generative AI declaration.
5. Acknowledgements.
6. Table of contents.
7. List of figures, if figures are included.
8. List of tables.

### 4.1 Abstract requirements

The abstract must:

- contain no citations;
- explain the banking problem;
- explain the scarcity of human labels;
- introduce the hybrid self-supervised and supervised design;
- identify the international and South African data components;
- summarise the three downstream TASCI stages;
- state the baseline models;
- state the primary hypothesis;
- state the intended evaluation strategy;
- avoid reporting unverified future results as completed findings.

### 4.2 AI declaration requirements

The AI declaration must use a Wits-style numbered table and truthfully mark the applicable categories.

AI tools currently requiring disclosure:

- Microsoft Copilot;
- GitHub Copilot;
- Kiro, if Kiro continues to be used in the submitted work.

AI-generated outputs must not be described as human annotation, gold labels, or independent research evidence.

## 5. Required Chapter Structure

The proposal must contain the following chapters or equivalent major sections:

1. Introduction and Background.
2. Literature Review.
3. Critical Review and Research Gap.
4. Research Methodology.
5. Project Plan and Expected Contributions.
6. References.
7. Appendices, where necessary.

## 6. Introduction Requirements

The introduction must explain:

- why banking feedback is operationally important;
- why document-level sentiment is insufficient;
- why ABSA is needed for messages containing multiple banking aspects;
- why customer intent adds information beyond sentiment;
- why international models may not transfer reliably to South African banking feedback;
- why full manual annotation is infeasible for one researcher;
- why self-supervised learning is used before supervised fine-tuning;
- why a small human-labelled validation and test set remains necessary.

The introduction must not call validation or test data “seen data.”

## 7. Research Aim

Use an aim equivalent to:

> To develop and evaluate a semi-supervised, intent-aware ABSA pipeline for international and South African banking feedback, and to determine whether predicted customer intent improves sentiment classification for explicit banking aspects.

## 8. Research Objectives

The objectives must be concise and aligned one-to-one with the research questions.

Required objectives:

1. Construct privacy-safe international and South African banking corpora with explicit source and regional provenance.
2. Adapt a pretrained language model to unlabelled banking text using self-supervised masked-language modelling.
3. Construct a smaller stratified human-audited gold corpus for aspect, sentiment, and intent tasks.
4. Develop the three-stage banking TASCI pipeline.
5. Compare SVM, BiLSTM, BERT, banking-adapted BERT, and TASCI using common labelled partitions.
6. Evaluate international-to-South-African transfer and mixed-domain learning.
7. Measure the contributions of context, intent, domain adaptation, gold aspects, and predicted aspects through controlled ablations.

## 9. Research Questions

The proposal must include questions equivalent to:

1. Does self-supervised banking-domain adaptation improve aspect, intent, and sentiment macro-F1?
2. How effectively can the proposed pipeline extract banking aspects, classify intent, and predict sentiment for each aspect?
3. Does genuine preceding context improve intent classification compared with current-text-only input?
4. Does predicted intent improve aspect-level sentiment macro-F1 compared with an otherwise equivalent no-intent model?
5. How do SVM, BiLSTM, BERT, banking-adapted BERT, and TASCI compare on common held-out data?
6. How well do internationally trained models generalise to independently labelled South African feedback?
7. Does mixed international and South African training improve South African performance?

## 10. Hypotheses

The proposal must state at least these hypotheses:

- **H1a:** Banking-domain self-supervised adaptation improves downstream macro-F1 over the same base model without banking adaptation.
- **H1b:** Predicted intent improves aspect-sentiment macro-F1 over an otherwise identical no-intent classifier.
- **H1c:** Genuine preceding context improves intent macro-F1 on the context-available subset.

Corresponding null hypotheses must be stated or clearly implied.

## 11. Dataset Provenance Requirements

Every dataset must be described separately.

### 11.1 International prepared pool

Authoritative source artifact:

`data/interim/prepared.csv`

Required reported count:

- 10,847 prepared records.

Raw sources include:

- `data/raw/sampledbanktweet.csv`, containing 10,000 rows;
- `data/raw/bank_reviews3.csv`, containing 1,000 rows.

The proposal must explain the difference between raw rows and the final prepared count.

### 11.2 South African prepared corpus

Authoritative source artifact:

`data/interim/south_africa_prepared.parquet`

Required reported count:

- 2,250,776 cleaned canonical records.

The proposal must state that the source is the **Tweets of Popular South African Banks** dataset and covers feedback associated with:

- FNB;
- Absa;
- Nedbank;
- Standard Bank;
- Capitec.

### 11.3 South African Version 2 candidate pool

The Version 2 candidate pool is derived from the prepared South African Parquet corpus using the evidence-based filter implemented by:

`scripts/resample_south_africa_v2.py`

Required expected count:

- 100,768 candidate records.

The proposal must explicitly distinguish this from the rejected Version 1 filter, which selected approximately 2,086,851 records because of an overly broad length-based rule.

### 11.4 Region and source labels

Every record must preserve:

- `record_id`;
- `source`;
- `region`;
- `bank`, where available;
- `year`, where available;
- `text`;
- `previous_text`;
- `context_available`;
- duplicate or leakage group;
- privacy status.

Allowed region values must include:

- `international`;
- `south_africa`.

Region must be assigned from source provenance, not inferred from bank names or predicted by a model.

Source, region, bank, year, title, and review rating must not be used as predictive features.

## 12. Data Cleaning Requirements

The proposal must explain why cleaning is required.

Cleaning must address:

- exact duplicates;
- near duplicates;
- overlapping source collections;
- empty text;
- official-bank marketing;
- competitions and promotional content;
- unrelated discussion;
- short or low-information records;
- usernames and handles;
- URLs;
- email addresses;
- phone numbers;
- account numbers;
- transaction or reference numbers;
- Unicode and whitespace inconsistencies.

Cleaning must preserve:

- negation;
- intensifiers;
- banking terminology;
- meaningful punctuation;
- meaningful hashtags;
- meaningful emojis;
- character offsets required for exact aspect spans.

The proposal must state that aggressive stemming and transformations that invalidate offsets will be avoided.

## 13. Revised Labelled and Unlabelled Allocation

The proposal must describe the following intended primary design:

### International

- Available prepared records: 10,847.
- Human-audited primary gold sample: 300.
- Unlabelled pool: 10,547.

### South African

- Evidence-based candidate records: 100,768.
- Human-labelled and adjudicated gold records: 196.
- Unlabelled pool: 100,572.

### Combined

- Human-audited gold records: 496.
- Unlabelled records: 111,119.

These numbers remain planned until the 300-record international audit is completed and the source pools are fully validated.

## 14. Human Annotation Requirements

The proposal must distinguish legacy annotations from the primary audited gold dataset.

### 14.1 Legacy international annotations

The repository contains a 600-record international component. Its paired annotation files were not genuinely independent, and the original `pilot_unannotated.jsonl` is not a pristine label-hidden source.

The proposal must not claim genuine independent agreement for all 600 records.

### 14.2 Primary international audit

A deterministic stratified sample of 300 international records must be selected and presented to the human auditor without existing labels.

The label-hidden input must have:

- empty aspects;
- null intent;
- no aspect sentiment;
- no aspect categories;
- no candidate strata;
- no annotator identity;
- `annotation_status = not_started`.

The 300-record sample must preserve diversity across:

- tweets and reviews;
- context and no-context records;
- text lengths;
- zero-aspect and multi-aspect records;
- available categories;
- available sentiments;
- available intents;
- duplicate and leakage groups.

### 14.3 South African annotation

The 196-record South African Gold Version 2 dataset must be reused without relabelling.

The proposal must disclose the genuine agreement statistics:

- intent Kappa: 0.8736;
- aspect-category Kappa: 0.9904;
- aspect-sentiment Kappa: 0.8750;
- exact-span agreement: 0.8010;
- token-level aspect F1: 0.8966;
- disagreement records: 48.

## 15. Primary Gold Split Requirements

After the international human audit is complete, the intended primary dataset contains 496 records.

Required planned partitions:

### International

- Training: 210.
- Validation: 45.
- Test: 45.

### South African

- Training: 138.
- Validation: 30.
- Test: 28.

### Combined

- Training: 348.
- Validation: 75.
- Test: 73.

All training, validation, and test records must have human reference labels.

The test set must remain unseen during training, hyperparameter selection, threshold selection, and checkpoint selection.

## 16. Self-Supervised Domain-Adaptation Requirements

### 16.1 Stage Zero

A pretrained BERT encoder must be adapted to unlabelled banking text using masked-language modelling.

Default configuration requirements:

- base model: local `bert-base-uncased`;
- `local_files_only = true`;
- seed: 42;
- maximum sequence length: 128;
- masking probability: 0.15;
- default policy: `strict_test_text_holdout = true`.

### 16.2 Strict holdout policy

Under the primary research policy, all primary validation and test records must be excluded from masked-language-model adaptation.

A secondary transductive policy may permit unlabelled test-text exposure only if:

- no test labels are exposed;
- the experiment is clearly labelled transductive;
- results are reported separately;
- the stricter result remains the primary result.

### 16.3 Unlabelled corpus schema

The MLM corpus may contain only:

- record ID;
- source;
- region;
- bank, where available;
- year, where available;
- text;
- previous text;
- context status;
- duplicate group;
- leakage group;
- privacy status.

It must exclude:

- aspect labels;
- category labels;
- sentiment labels;
- intent labels;
- human annotations;
- annotator names;
- adjudication data;
- ratings;
- candidate strata as model input;
- pseudo-labels.

## 17. Downstream Pipeline Requirements

### 17.1 Stage One: Aspect extraction

Input:

- current banking text.

Model:

- custom multi-head self-attention BIO classifier.

Baseline:

- BERT token classification.

Output:

- exact aspect terms;
- start and end offsets;
- BIO labels;
- aspect category.

Goal:

- identify the banking product, service, or process being discussed.

### 17.2 Stage Two: Contextual intent

Input:

- current text;
- genuine preceding text, where available;
- `[NO_CONTEXT]` otherwise.

Model:

- current-sentence GRU encoder;
- previous-sentence GRU encoder;
- attention over previous hidden states;
- seven-class intent head.

Required intents:

- complaint;
- compliment;
- request for assistance;
- suggestion;
- warning;
- churn signal;
- general feedback.

Goal:

- identify the customer’s communicative purpose.

### 17.3 Stage Three: Intent-aware aspect sentiment

Input:

- current text;
- target aspect;
- predicted intent.

Model:

- GloVe aspect representation;
- Transformer encoder;
- intent projection;
- aspect-intent fusion;
- three-class sentiment head.

Output:

- positive;
- neutral;
- negative.

Goal:

- predict sentiment towards each aspect while testing whether intent adds useful context.

## 18. Baseline Requirements

The proposal must include:

- SVM with TF--IDF;
- BiLSTM;
- original BERT;
- banking-adapted BERT;
- proposed TASCI pipeline.

All comparable models must use the same labelled manifests, label maps, and evaluation protocol.

Existing SVM results from the legacy 796-record combined Version 2 dataset must not be presented as results from the future primary 496-record dataset.

## 19. Required Experiments

### Experiment A: Cross-domain transfer

- Self-supervised adaptation: unlabelled international and South African text.
- Supervised training and validation: international labelled data only.
- In-domain test: international held-out data.
- External target test: independently labelled South African data.
- South African labels must not influence model selection.

### Experiment B: Mixed-domain model

- Training: combined 348-record training set.
- Validation: combined 75-record validation set.
- Test: combined 73-record held-out set.
- Results must be reported separately for each region.

### Experiment C: Domain-adaptation ablation

Compare:

- original BERT;
- banking-adapted BERT.

Everything except the pretrained checkpoint must remain identical.

### Experiment D: Context ablation

Compare:

- current-text-only intent;
- previous-plus-current intent.

### Experiment E: Intent-fusion ablation

Compare:

- aspect sentiment without intent;
- sentiment with predicted intent;
- sentiment with gold intent.

### Experiment F: Pipeline-error analysis

Compare:

- gold aspects;
- predicted aspects;
- component evaluation;
- end-to-end evaluation.

## 20. Evaluation Requirements

### Aspect extraction

Report:

- token precision;
- token recall;
- token F1;
- exact-span precision;
- exact-span recall;
- exact-span F1;
- boundary-error categories.

### Intent and sentiment

Report:

- accuracy;
- macro precision;
- macro recall;
- macro-F1;
- weighted-F1;
- per-class precision;
- per-class recall;
- per-class F1;
- class support;
- confusion matrices.

### End-to-end

Report:

- exact aspect-sentiment pairs;
- aspect-category-sentiment tuples;
- aspect-sentiment-intent tuples.

### Subgroups

Where support permits, report:

- international;
- South African;
- context available;
- no context;
- tweets;
- reviews.

Small or single-class subgroups must be labelled exploratory.

Macro-F1 must be the primary model-selection metric for intent and sentiment because of class imbalance.

## 21. Context-Selection Requirements

The proposal must acknowledge that additional context may help or introduce noise.

The pipeline must:

- compare current-only and previous-plus-current input;
- never use neighbouring dataset rows as context;
- use only genuine review or conversation context;
- represent unavailable context explicitly;
- consider dynamic or shorter context selection as an optional experiment;
- avoid assuming that longer context automatically improves performance.

## 22. Model Artifact Requirements

Every completed research run must preserve:

- configuration;
- environment details;
- source checksums;
- Git commit or reproducibility identifier;
- seed;
- label maps;
- train manifest;
- validation manifest;
- test manifest;
- best checkpoint;
- last checkpoint;
- validation metrics;
- held-out test metrics;
- predictions;
- confusion matrices or span reports;
- subgroup metrics;
- training log;
- cluster job metadata;
- reload verification.

No model may be reported as completed until the selected checkpoint reloads and reproduces fixed predictions.

## 23. Ethics and Privacy Requirements

The proposal must state that:

- only public data is used;
- direct identifiers are removed;
- raw usernames and raw Tweet IDs are not published;
- account and transaction references are anonymised;
- the complete raw archive will not be redistributed;
- Kaggle and Twitter/X reuse conditions will be documented;
- candidate keywords are not treated as gold labels;
- review ratings are not converted to aspect sentiment;
- pseudo-labels are weak training labels and are excluded from validation and testing;
- AI outputs are not human annotation;
- the research does not attempt to identify customers or employees.

## 24. Reproducibility Requirements

The proposal must require:

- deterministic seeds;
- versioned data artifacts;
- immutable manifests;
- checksums;
- explicit source and region provenance;
- offline model loading;
- no model downloads inside scheduled jobs;
- checkpoint resume;
- validation-only model selection;
- one-time held-out test evaluation;
- documented cluster environment;
- fixed output directories;
- no overwriting of completed runs.

## 25. Implementation Versioning Requirements

The legacy supervised experiment version must remain frozen:

- gold: `combined_adjudicated_v2.jsonl`;
- manifests: `data/processed/combined_v2/`;
- completed SVM runs: existing 20260908 run directories.

The revised pipeline must use new versioned paths:

- `data/annotations/primary_v1/`;
- `data/processed/primary_v1/`;
- `data/processed/self_supervised/`;
- `outputs/runs/domain_adaptation/`;
- `models/domain_adapted/banking-bert-v1/`.

Metrics from different dataset versions must not be directly compared without clearly identifying the dataset and manifests used.

## 26. Required Proposal Tables

The proposal must include tables for:

1. Dataset source and regional provenance.
2. Labelled and unlabelled allocation.
3. Human-labelled train, validation, and test partitions.
4. Annotation scheme.
5. Pipeline stages, models, inputs, outputs, and goals.
6. Objective-question-evidence alignment.
7. Critical literature synthesis.
8. Research timeline.

## 27. Required Proposal Consistency Checks

Before submission, verify that:

- the abstract has no citations;
- all bibliography keys resolve;
- all data counts are consistent;
- planned counts are labelled as planned;
- completed results are labelled as completed;
- future work uses future tense;
- legacy and primary dataset versions are distinguished;
- international and South African sources are described separately;
- annotation responsibilities are stated truthfully;
- SVM, BiLSTM, BERT, and TASCI roles are distinct;
- context improvement and intent-fusion improvement are separate hypotheses;
- no unverified result is presented as evidence;
- Wits AI usage is declared accurately.

## 28. Stop Conditions for Implementation

Implementation must stop if:

- the authoritative proposal is missing;
- source-pool counts cannot be reproduced;
- privacy checks fail;
- regional provenance is ambiguous;
- cross-region record-ID collisions exist;
- the 300-record international audit is incomplete;
- validation or test labels leak into training;
- the South African Version 2 count differs from 100,768;
- a completed artifact would be overwritten;
- a checkpoint cannot reload;
- the local pretrained model is missing;
- a scheduled job attempts an internet download.

## 29. Acceptance Criteria

The proposal requirements are satisfied when:

1. The source pools are verified.
2. The 100,768-record South African Version 2 pool is reproducible.
3. The 300-record international label-hidden audit input exists.
4. The human international audit is completed and validated.
5. The 496-record primary gold dataset exists.
6. The 348/75/73 manifests pass leakage checks.
7. The strict self-supervised corpus excludes protected test text.
8. Banking BERT domain adaptation completes and reloads.
9. SVM, BiLSTM, BERT, adapted BERT, and TASCI run on common manifests.
10. Context and intent ablations are complete.
11. Cross-domain and mixed-domain evaluations are complete.
12. Final checkpoints reproduce saved predictions.
13. The final proposal and dissertation accurately reflect verified implementation and results.

## 30. Authoritative Status

At the time these requirements were written:

- the international 10,847-record pool has been located;
- the South African 2,250,776-record prepared corpus has been located;
- the 100,768-record South African Version 2 pool is reproducible but not stored separately;
- the South African 196-record gold dataset exists;
- the legacy 796-record combined dataset and SVM experiments exist;
- the 300-record international human audit is not complete;
- the primary 496-record gold dataset does not yet exist;
- self-supervised banking-domain adaptation is not yet implemented;
- the complete TASCI architecture is not yet implemented.

