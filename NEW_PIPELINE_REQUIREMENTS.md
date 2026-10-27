# Banking TASCI New Pipeline Requirements

**Document version:** `new_pipeline_v1`  
**Status:** Authoritative requirements baseline  
**Last updated:** 12 October 2026  
**Researcher:** Rotondwa Mavhengani  
**Project:** Semi-Supervised Intent-Aware Aspect-Based Sentiment Analysis of International and South African Banking Feedback

---

## 1. Purpose of this document

This document is the authoritative requirements baseline for the revised Banking TASCI research pipeline. It is designed to provide complete continuity when work begins in a new Kiro, Copilot, or developer session.

Any implementation, code audit, migration plan, data preparation step, annotation export, training job, evaluation script, report, or presentation must align with this document.

If the repository contains logic that conflicts with this document, the conflicting logic must be reported as legacy behaviour. It must not silently override these requirements.

The new pipeline must be introduced under a versioned configuration such as:

```yaml
pipeline_version: new_pipeline_v1
```

Existing working code and artifacts must be preserved until the revised pipeline has passed its tests and reproducibility checks.

---

## 2. Research aim

The research aims to develop and evaluate a semi-supervised, intent-aware Aspect-Based Sentiment Analysis pipeline for international and South African banking feedback.

The system must identify:

1. what banking target is discussed;
2. which property of the target is evaluated;
3. the opinion expression associated with the target, where explicit;
4. the sentiment directed towards the target;
5. the dominant communicative intent of the complete feedback record;
6. whether genuine preceding context is available and useful.

The study must determine whether the following improve downstream performance:

- banking-domain masked-language adaptation;
- South African supervised data;
- genuine preceding context;
- predicted communicative intent;
- entity-attribute category information.

---

## 3. Core research questions

The implementation must support experiments that answer the following questions:

1. Does banking-domain masked-language adaptation improve target, category, intent, and sentiment macro-F1 compared with the original pretrained model?
2. How accurately can the pipeline extract banking targets and assign entity-attribute categories?
3. Does genuine preceding context improve communicative-intent classification?
4. Does predicted intent improve aspect-level sentiment compared with an equivalent no-intent condition?
5. How well do internationally trained models generalise to South African banking feedback?
6. Does mixed international and South African supervision improve South African performance?
7. How much performance is lost when predicted targets and categories replace gold targets and categories?

---

## 4. Authoritative dataset counts

### 4.1 South African research corpus

The South African starting dataset for the revised research pipeline is:

```text
100,768 customer-feedback candidate records
```

This corpus has already passed the broader data-preparation process, which includes:

- deduplication;
- content cleaning;
- privacy processing;
- removal of promotional and unrelated content;
- customer-feedback relevance selection.

The earlier broader collection of approximately 2.25 million records is provenance information only. It is not the starting dataset for modelling, sampling, or domain adaptation in `new_pipeline_v1`.

Do not calculate downstream counts using 2,250,776 records.

### 4.2 International research corpus

The prepared international corpus contains:

```text
10,847 records
```

It contains international banking tweets and bank reviews.

### 4.3 Combined relevant corpus

```text
South African candidate corpus: 100,768
International prepared corpus:   10,847
                                --------
Combined relevant corpus:        111,615
```

### 4.4 Gold annotation corpus

The manually annotated gold corpus contains:

```text
1,000 records
```

Allocation:

```text
South African banking tweets: 500
International banking tweets: 250
International bank reviews:   250
                              ---
Total:                       1,000
```

Regional allocation:

```text
South African: 500
International: 500
```

### 4.5 Strict unlabelled corpus

The strict unlabelled corpus excludes all 1,000 gold records.

```text
Combined relevant corpus: 111,615
Gold corpus excluded:       1,000
                           -------
Strict unlabelled corpus:  110,615
```

Source-level calculation:

```text
South African:
100,768 - 500 = 100,268 unlabelled records

International:
10,847 - 500 = 10,347 unlabelled records

Combined:
100,268 + 10,347 = 110,615 unlabelled records
```

These counts must be validated using record identifiers and manifests, not only arithmetic assumptions.

---

## 5. Data-source roles

### 5.1 South African banking tweets

Roles:

- provide 100,268 unlabelled records for strict domain adaptation;
- provide 500 records for human annotation;
- provide South African target-domain evaluation data;
- support bank-aware sampling, but bank identity must not be a predictive model feature.

Represented banks include:

- FNB;
- Absa;
- Nedbank;
- Standard Bank;
- Capitec.

### 5.2 International banking tweets

Roles:

- contribute to unlabelled domain adaptation;
- provide 250 annotated records;
- provide source-domain supervised data;
- represent short, informal banking feedback.

### 5.3 International bank reviews

Roles:

- contribute to unlabelled domain adaptation;
- provide 250 annotated records;
- provide longer feedback records;
- provide genuine preceding-sentence context where available;
- support context-aware intent experiments.

---

## 6. South African data-preparation requirements

The revised pipeline begins with the final 100,768-record South African customer-feedback candidate corpus.

The repository must document or preserve evidence that the corpus underwent:

### 6.1 Deduplication

- duplicate tweet identifiers removed;
- exact normalised-text duplicates removed;
- repeated imports removed;
- near-duplicate groups identified where possible;
- duplicate and related groups assigned stable group identifiers.

### 6.2 Content cleaning

Exclude or mark as ineligible:

- official bank marketing;
- competitions and giveaways;
- sponsorship campaigns;
- product advertisements;
- corporate announcements;
- unrelated news;
- records containing only a bank name;
- content without a customer banking experience;
- empty records;
- unusable low-information records.

### 6.3 Privacy processing

Anonymise or replace:

- usernames and handles;
- URLs;
- email addresses;
- telephone numbers;
- account numbers;
- transaction or case references;
- other direct identifiers.

Preserve information important to language modelling and ABSA:

- negation;
- intensifiers;
- banking terminology;
- meaningful punctuation;
- meaningful emojis;
- casing where the selected model and preprocessing policy permit it.

### 6.4 Customer-feedback evidence

Eligible records should contain a banking product, service, channel, or process together with customer-experience evidence.

Banking evidence may include:

- account;
- card;
- mobile application;
- online banking;
- transfer;
- payment;
- debit order;
- ATM;
- withdrawal;
- deposit;
- fees;
- loan;
- branch;
- consultant;
- fraud;
- refund;
- transaction;
- beneficiary;
- PIN;
- password or profile access.

Customer-experience evidence may include:

- problem or failure expressions;
- requests for assistance;
- first-person banking experiences;
- praise or appreciation;
- suggestions or feature requests;
- security concerns;
- exit, closure, cancellation, or switching language.

A bank name or single banking keyword is not sufficient on its own.

### 6.5 Candidate rules are not task labels

Data-preparation rules must never be copied into the final gold fields as if they were human labels.

Candidate rules may support sampling reports only. They must not automatically assign:

- target;
- category;
- opinion phrase;
- sentiment;
- communicative intent.

---

## 7. Gold-corpus sampling requirements

Sampling must be reproducible, source-aware, group-aware, and auditable.

### 7.1 South African sample

Select 500 records.

Initial bank allocation:

```text
FNB:             100
Absa:            100
Nedbank:         100
Standard Bank:   100
Capitec:         100
Total:           500
```

The sampler must cover, where fields are available:

- bank;
- year;
- short, medium, and long text;
- candidate-rule group;
- duplicate or leakage group;
- likely zero-opinion, single-opinion, and multi-opinion records;
- varied customer-feedback language.

### 7.2 International tweet sample

Select 250 records.

Cover:

- short, medium, and long text;
- candidate types;
- duplicate groups;
- varied banking products and customer-experience expressions.

### 7.3 International review sample

Select 250 records.

Cover:

- short, medium, and long reviews;
- low, middle, and high rating bands where ratings are available;
- number of sentences;
- context availability;
- duplicate or review groups.

Review rating is sampling metadata only. It must never automatically become a sentiment label.

### 7.4 Length bands

Short, medium, and long boundaries must be calculated using source-specific quantiles.

Do not apply one arbitrary global character threshold across tweets and reviews.

### 7.5 Sampling outputs

The sampler must produce:

- a label-hidden annotation file;
- a sample manifest;
- source-level counts;
- bank-level counts;
- length-band counts;
- context counts;
- duplicate-group checks;
- shortages or unsatisfied constraints;
- the random seed;
- the source-data checksum;
- reasons or strata used for each selected record.

The sampler must not silently use replacement sampling.

---

## 8. Annotation schema

Each record may contain:

- zero opinion structures;
- one opinion structure;
- multiple opinion structures.

### 8.1 Record-level fields

Required fields:

```text
record_id
source
region
bank
review_id
thread_id
conversation_id
publish_year
text
previous_text
context_available
duplicate_group
leakage_group
privacy_status
primary_intent
public_warning
opinions
annotation_status
annotation_version
annotation_notes
```

Fields not available from the source may be `null`, but required keys must remain structurally consistent.

### 8.2 Opinion-level fields

Each item in `opinions` must support:

```text
target
target_start
target_end
target_type
entity
attribute
category
opinion_phrase
opinion_start
opinion_end
sentiment
annotation_notes
```

### 8.3 Explicit targets

For an explicit target:

```text
target_type = explicit
text[target_start:target_end] == target
```

Offsets use:

```text
start = inclusive
end = exclusive
```

### 8.4 Implicit targets

For an implicit target:

```text
target = null
target_start = null
target_end = null
target_type = implicit
```

The entity, attribute, category, sentiment, and any explicit opinion phrase remain annotated.

### 8.5 Explicit opinion phrases

Where an opinion phrase is explicit:

```text
text[opinion_start:opinion_end] == opinion_phrase
```

Where no explicit phrase is available, phrase and offsets may be `null` according to the annotation guide.

### 8.6 Zero-opinion records

A valid zero-opinion record contains:

```json
"opinions": []
```

Such records must remain possible. The system must not assume that every candidate contains an annotatable opinion.

### 8.7 Multi-opinion records

Multiple linked opinions are allowed, including multiple sentiments towards different targets in one record.

One document-level sentiment must not overwrite target-level sentiment.

---

## 9. Entity-attribute banking taxonomy

The taxonomy must be stored in one canonical configuration used by:

- annotation exports;
- annotation validation;
- preprocessing;
- training;
- evaluation;
- reporting.

Do not duplicate independent category lists across scripts.

Canonical format:

```text
ENTITY#ATTRIBUTE
```

### 9.1 Application

```text
APP#USABILITY
APP#RELIABILITY
APP#ACCESS
APP#SECURITY
APP#UPDATES
APP#GENERAL
```

### 9.2 Online banking

```text
ONLINE_BANKING#USABILITY
ONLINE_BANKING#RELIABILITY
ONLINE_BANKING#ACCESS
ONLINE_BANKING#SECURITY
ONLINE_BANKING#GENERAL
```

### 9.3 Cards

```text
CARD#DELIVERY
CARD#ACTIVATION
CARD#FUNCTIONALITY
CARD#PAYMENT
CARD#FEES
CARD#SECURITY
CARD#GENERAL
```

### 9.4 Accounts

```text
ACCOUNT#OPENING
ACCOUNT#ACCESS
ACCOUNT#BALANCE
ACCOUNT#STATEMENT
ACCOUNT#CLOSURE
ACCOUNT#FEES
ACCOUNT#GENERAL
```

### 9.5 Transfers

```text
TRANSFER#SPEED
TRANSFER#RELIABILITY
TRANSFER#REVERSAL
TRANSFER#FEES
TRANSFER#BENEFICIARY
TRANSFER#GENERAL
```

### 9.6 Payments

```text
PAYMENT#RELIABILITY
PAYMENT#REVERSAL
PAYMENT#FEES
PAYMENT#GENERAL
```

### 9.7 ATM and cash services

```text
ATM#AVAILABILITY
ATM#WITHDRAWAL
ATM#DEPOSIT
ATM#RELIABILITY
ATM#FEES
ATM#GENERAL
```

### 9.8 Customer support

```text
SUPPORT#RESPONSIVENESS
SUPPORT#COMPETENCE
SUPPORT#PROBLEM_RESOLUTION
SUPPORT#COMMUNICATION
SUPPORT#GENERAL
```

### 9.9 Branch service

```text
BRANCH#ACCESSIBILITY
BRANCH#WAITING_TIME
BRANCH#STAFF
BRANCH#OPERATING_HOURS
BRANCH#GENERAL
```

### 9.10 Security

```text
SECURITY#ACCOUNT
SECURITY#CARD
SECURITY#TRANSACTION
SECURITY#IDENTITY_VERIFICATION
SECURITY#GENERAL
```

### 9.11 Fraud and disputes

```text
FRAUD#UNAUTHORISED_ACTIVITY
FRAUD#INVESTIGATION
FRAUD#RESOLUTION
FRAUD#GENERAL
```

### 9.12 Loans and credit

```text
LOAN#APPLICATION
LOAN#APPROVAL
LOAN#INTEREST_RATE
LOAN#REPAYMENT
LOAN#CREDIT_LIMIT
LOAN#GENERAL
```

### 9.13 Bank-level evaluation

```text
BANK#OVERALL_SERVICE
BANK#REPUTATION
BANK#GENERAL
```

### 9.14 General-category rule

A `GENERAL` attribute is allowed only when the text evaluates the entity without enough evidence for a more specific attribute.

The validator and annotation reports must monitor excessive use of `GENERAL`.

---

## 10. Sentiment labels

Allowed sentiment labels:

```text
positive
neutral
negative
conflict
```

Sentiment is assigned to each linked opinion, not as one mandatory label for the complete record.

The annotation guide must define `conflict` carefully. It must not become a substitute for uncertainty or annotation difficulty.

---

## 11. Communicative-intent taxonomy

Each record receives one primary communicative intent.

Allowed values:

```text
complaint
request_for_assistance
praise_or_appreciation
suggestion_or_feature_request
exit_or_switch_intention
general_feedback
```

### 11.1 Complaint

The customer expresses dissatisfaction with a banking service, product, process, employee, or outcome.

### 11.2 Request for assistance

The customer asks the bank to provide information, investigate, explain, or perform corrective action.

### 11.3 Praise or appreciation

The customer expresses approval, satisfaction, gratitude, or appreciation without another dominant function.

### 11.4 Suggestion or feature request

The customer proposes an improvement, new feature, change, or alternative service design.

### 11.5 Exit or switch intention

The customer explicitly states an intention to leave, close, cancel, reduce, or move the banking relationship.

Strong negative sentiment without explicit exit or switching language is not sufficient.

### 11.6 General feedback

The customer reports an experience, evaluation, or observation that does not have another more specific dominant communicative function.

This label must not become an unrestricted miscellaneous class.

### 11.7 Public warning

Warning is not a primary intent.

Use:

```text
public_warning = true | false
```

The flag preserves warnings directed to other customers while allowing the primary intent to remain complaint, assistance, or another dominant function.

---

## 12. Context requirements

Allowed context status:

```text
context_available = true | false
```

Where context is available:

- `previous_text` must contain genuine preceding text;
- source linkage must be verifiable through review, thread, or conversation identifiers.

Where context is unavailable:

- `previous_text` must use a consistent null representation in the data schema;
- the model input must use `[NO_CONTEXT]` where required by the experiment.

Never use the previous physical dataset row as context unless the source proves that the records are linked.

---

## 13. Annotation workflow

### 13.1 Label-hidden export

The annotation file must not expose:

- candidate-rule predictions as gold labels;
- automatically inferred sentiment;
- automatically inferred intent;
- review rating as sentiment;
- model suggestions unless a separate, explicitly documented assisted-annotation experiment is approved.

### 13.2 Calibration

The first 50 records form the calibration batch.

The calibration stage must refine:

- span-boundary rules;
- explicit versus implicit target rules;
- category definitions;
- intent precedence rules;
- sentiment rules;
- opinion-phrase rules;
- handling of multiple opinions;
- handling of zero-opinion records;
- context rules.

After calibration, the annotation guide is versioned and frozen for the main annotation stage.

### 13.3 Remaining annotation

After the 50-record calibration batch, 950 records remain.

A valid batching plan is:

```text
Calibration batch:       50
Main batches:       9 x 100 = 900
Final batch:             50
                         ---
Total:                1,000
```

Do not claim that `50 + 9 x 100 = 1,000`; that equals 950. The final 50-record batch must be represented explicitly unless another batching plan is configured.

### 13.4 Resumption

Annotation tooling must support:

- autosave or explicit safe save;
- batch-level checkpointing;
- safe resumption;
- immutable record identifiers;
- annotation-status tracking;
- annotation-version tracking;
- audit history where practical.

### 13.5 Final freeze

Before splitting, the complete gold corpus must be:

- schema-valid;
- offset-valid;
- privacy-valid;
- group-valid;
- manually reviewed;
- assigned a version;
- assigned a checksum;
- described by an immutable manifest.

---

## 14. Annotation validation requirements

Validation must fail on material schema or integrity errors.

Required checks:

- unique `record_id`;
- allowed source values;
- allowed region values;
- allowed intent values;
- allowed sentiment values;
- allowed target types;
- valid entity and attribute combinations;
- `category == entity + "#" + attribute`;
- explicit target offsets match target text;
- explicit opinion offsets match opinion text;
- implicit target fields are null;
- valid context fields;
- valid privacy status;
- no direct identifiers after privacy processing;
- no invalid overlapping spans unless the guide explicitly permits them;
- no missing mandatory keys;
- valid arrays for zero, one, or multiple opinions;
- duplicate-group consistency;
- review and conversation linkage consistency;
- valid annotation status and version.

Validation outputs must include:

- error count;
- warning count;
- affected record IDs;
- rule identifiers;
- fix guidance;
- machine-readable JSON report;
- human-readable Markdown report.

---

## 15. Gold-corpus split

The frozen 1,000-record gold corpus uses:

```text
Training:   800 records, 80%
Validation: 100 records, 10%
Test:       100 records, 10%
```

Source-level allocation:

```text
                         Train  Validation  Test  Total
South African tweets      400      50       50    500
International tweets      200      25       25    250
International reviews     200      25       25    250
-------------------------------------------------------
Total                     800     100      100  1,000
```

### 15.1 Partition roles

Training:

- updates model parameters;
- fits SVM, BiLSTM, BERT, and TASCI components.

Validation:

- controls early stopping;
- compares hyperparameters;
- selects checkpoints;
- selects thresholds;
- selects model configurations.

Test:

- remains protected until model and experiment decisions are fixed;
- provides final generalisation results.

### 15.2 Group-aware leakage constraints

Records sharing any of the following remain in one partition:

- `duplicate_group`;
- `leakage_group`;
- `review_id`;
- verified `thread_id`;
- verified `conversation_id`;
- other configured related-record groups.

The splitter should preserve, where feasible:

- source;
- region;
- sentiment;
- intent;
- entity;
- category;
- target type;
- zero-opinion records;
- single-opinion records;
- multi-opinion records;
- context availability.

Rare combinations may make perfect stratification impossible. The splitter must report unsatisfied constraints rather than silently violating grouping rules.

### 15.3 Split outputs

Required files:

```text
train.jsonl
validation.jsonl
test.jsonl
split_manifest.json
split_distribution.json
split_distribution.md
leakage_report.json
leakage_report.md
```

The split must be deterministic under a fixed seed.

Default seed:

```text
42
```

---

## 16. Strict unlabelled corpus for domain adaptation

The unlabelled corpus contains 110,615 records.

It must exclude all 1,000 gold records by stable identifier and checksum-aware comparison.

The MLM corpus must exclude:

- target labels;
- opinion labels;
- category labels;
- sentiment labels;
- intent labels;
- annotation notes;
- annotation status;
- partition labels;
- review ratings as predictive content;
- bank identity as a predictive feature;
- region identity as a predictive feature;
- sampling-rule metadata;
- candidate-rule metadata.

Approved text fields must be specified in configuration.

Required output evidence:

- source manifest;
- final record count of 110,615;
- gold-exclusion report;
- duplicate report;
- checksum;
- text-field policy;
- privacy-validation result.

---

## 17. Domain-adaptation requirements

Default configuration:

```yaml
base_model: bert-base-uncased
max_length: 128
masking_probability: 0.15
seed: 42
exclude_all_gold_records: true
```

The implementation must support:

- locally approved base checkpoint;
- saved tokenizer;
- saved model checkpoint;
- saved training arguments;
- saved loss history;
- deterministic configuration where technically possible;
- resumable checkpoints;
- reload verification;
- unlabelled-corpus manifest;
- environment capture;
- run-level output directory;
- immutable completed outputs.

The main comparison is:

```text
Original BERT
versus
Banking-adapted BERT
```

Both conditions must use the same labelled partitions and downstream settings.

---

## 18. Stage 1: Explicit target extraction

Requirements:

- BIO sequence tagging;
- support `B-ASP`, `I-ASP`, and `O`;
- support zero-target records;
- support multiple targets;
- preserve character-offset reconstruction;
- self-attention model;
- BERT token-classification baseline;
- no assumption of one target per record.

Evaluation:

- token precision, recall, and F1;
- exact-span precision, recall, and F1;
- boundary-error report.

Implicit targets are not extracted as token spans. They are handled through category prediction and gold annotation analysis.

---

## 19. Stage 1B: Entity-attribute category prediction

Requirements:

- predict canonical `ENTITY#ATTRIBUTE` categories;
- support more than one category per record;
- support categories with implicit targets;
- implement a BERT text-category pair condition;
- represent categories semantically, not only as arbitrary numeric IDs;
- create related and unrelated text-category training pairs;
- control unrelated-pair imbalance through weighting or sampling;
- use the canonical taxonomy configuration.

Example semantic mapping:

```text
APP#RELIABILITY -> "mobile application, reliability"
CARD#FEES -> "card, fees"
SUPPORT#RESPONSIVENESS -> "customer support, responsiveness"
```

Evaluation:

- accuracy where applicable;
- macro precision, recall, and F1;
- weighted-F1;
- per-class support;
- confusion matrix or multilabel equivalent;
- region and source breakdowns.

---

## 20. Stage 2: Communicative-intent classification

Required conditions:

1. current text only;
2. genuine previous context plus current text.

Model requirements:

- GRU-based contextual condition;
- an attention mechanism over context where retained by the design;
- `[NO_CONTEXT]` handling;
- one primary intent output;
- separate `public_warning` flag;
- no arbitrary previous-row context;
- baseline BERT intent classifier;
- baseline SVM and BiLSTM conditions where defined.

Evaluation:

- accuracy;
- macro precision, recall, and F1;
- weighted-F1;
- per-class support;
- confusion matrix;
- context-available subgroup;
- no-context subgroup;
- regional and source subgroups.

---

## 21. Stage 3: Aspect-level sentiment

Inputs may include:

- current text;
- target;
- target type;
- category;
- predicted or gold intent according to the experiment.

Required conditions:

1. no intent;
2. predicted intent;
3. gold intent upper bound.

Required baselines and models:

- TF-IDF plus linear SVM;
- BiLSTM;
- original BERT;
- banking-adapted BERT;
- GloVe plus Transformer condition if retained;
- TASCI-style intent-fusion condition.

The no-intent and predicted-intent conditions must keep the same:

- training records;
- validation records;
- test records;
- random seeds;
- training budget;
- selection metric;
- base architecture, except for the intent input.

Evaluation:

- accuracy;
- macro precision, recall, and F1;
- weighted-F1;
- per-class support;
- confusion matrix;
- gold-target condition;
- predicted-target condition;
- predicted-intent condition;
- gold-intent condition.

---

## 22. Baselines

Required baseline families:

### 22.1 SVM

- TF-IDF features;
- linear SVM;
- deterministic configuration;
- class weighting where justified;
- current-text input for standard tasks;
- target-marked sentiment input where applicable.

### 22.2 BiLSTM

- bidirectional sequence encoding;
- controlled embeddings and vocabulary;
- comparable train, validation, and test partitions;
- early stopping using validation macro-F1.

### 22.3 Original BERT

- token classification for target extraction;
- sequence or pair classification for category, intent, and sentiment;
- same downstream settings as adapted BERT.

### 22.4 Banking-adapted BERT

- initialised from the MLM checkpoint;
- same labelled partitions and downstream settings as original BERT.

### 22.5 TASCI-style integrated pipeline

- target and category stage;
- contextual intent stage;
- intent-aware aspect-sentiment stage;
- component and end-to-end evaluation.

---

## 23. Required experiments

### A. Domain adaptation

```text
Original BERT vs banking-adapted BERT
```

### B. Cross-domain transfer

```text
Train and select using international labelled data
Evaluate using South African labelled data
```

South African labels must not select the source-only model.

### C. Mixed-domain learning

```text
Train using international + South African training records
Report combined, international, and South African results
```

### D. Context ablation

```text
Current text only
vs
Previous context + current text
```

### E. Intent ablation

```text
No intent
vs
Predicted intent
vs
Gold intent
```

### F. Pipeline propagation

```text
Gold targets vs predicted targets
Gold categories vs predicted categories, where applicable
```

All comparable conditions use aligned partitions, seeds, selection metrics, and reporting logic.

---

## 24. Evaluation requirements

### 24.1 Target extraction

- token precision;
- token recall;
- token F1;
- exact-span precision;
- exact-span recall;
- exact-span F1;
- boundary-error analysis.

### 24.2 Category classification

- accuracy where suitable;
- macro precision;
- macro recall;
- macro-F1;
- weighted-F1;
- per-class support;
- confusion matrix or multilabel equivalent.

### 24.3 Intent classification

- accuracy;
- macro precision;
- macro recall;
- macro-F1;
- weighted-F1;
- per-class support;
- confusion matrix.

### 24.4 Sentiment classification

- accuracy;
- macro precision;
- macro recall;
- macro-F1;
- weighted-F1;
- per-class support;
- confusion matrix.

### 24.5 End-to-end evaluation

- exact target-category-sentiment tuple precision, recall, and F1;
- exact target-sentiment-intent tuple precision, recall, and F1;
- component metrics;
- gold-target versus predicted-target results;
- gold-intent versus predicted-intent results.

### 24.6 Subgroups

Report, where support is adequate:

- international;
- South African;
- tweets;
- reviews;
- context available;
- no context;
- source bank where ethically and statistically appropriate;
- explicit targets;
- implicit targets;
- zero-, single-, and multi-opinion records.

Small subgroups must be labelled exploratory.

### 24.7 Random seeds

Main neural experiments support five random seeds.

Report:

- per-run metrics;
- mean;
- standard deviation;
- selected checkpoint per run.

---

## 25. Reproducibility requirements

Each run must preserve:

- pipeline version;
- Git commit hash;
- configuration file;
- environment or dependency lock;
- random seed;
- data checksums;
- source manifest;
- split manifest;
- taxonomy version;
- label maps;
- training arguments;
- checkpoints;
- logs;
- predictions;
- metrics;
- subgroup reports;
- reload verification;
- start and completion timestamps.

Completed run directories must be immutable or protected from silent overwrite.

Recommended directory pattern:

```text
artifacts/runs/<pipeline_version>/<task>/<model>/<timestamp_or_run_id>/
```

---

## 26. Ethics and privacy

The implementation must:

- use public data according to applicable source terms;
- remove direct identifiers;
- avoid redistributing the unrestricted raw social-media archive;
- paraphrase examples where publication risk exists;
- document privacy transformations;
- preserve only required provenance fields;
- exclude bank and region metadata as predictive shortcuts;
- avoid treating AI-generated labels as human gold labels.

---

## 27. Prohibited assumptions and legacy behaviours

The revised pipeline must not silently use:

- 2,250,776 records as the modelling starting corpus;
- 2,260,623 records as the unlabelled corpus;
- 300-record annotation totals;
- 600-record annotation totals;
- 70/15/15 splits;
- percentage-only annotation sampling;
- seven primary intents including warning;
- flat category lists as the final taxonomy;
- review rating as gold sentiment;
- neighbouring dataset rows as context;
- one sentiment per complete record;
- one target per record;
- the assumption that every record has an explicit target;
- Cohen's Kappa with one annotator;
- an independent annotator or adjudicator unless one is actually recruited and documented;
- source, bank, year, rating, or region as predictive shortcuts;
- gold records in the strict MLM corpus;
- labels or annotation notes in MLM text.

---

## 28. Canonical configuration requirements

Prepare:

```text
configs/new_pipeline_v1.yaml
```

Minimum structure:

```yaml
pipeline_version: new_pipeline_v1

counts:
  south_africa_candidates: 100768
  international_prepared: 10847
  combined_relevant: 111615
  gold_total: 1000
  unlabelled_total: 110615

annotation:
  south_africa_tweets: 500
  international_tweets: 250
  international_reviews: 250
  calibration_size: 50
  primary_intents:
    - complaint
    - request_for_assistance
    - praise_or_appreciation
    - suggestion_or_feature_request
    - exit_or_switch_intention
    - general_feedback
  public_warning_field: public_warning
  sentiment_labels:
    - positive
    - neutral
    - negative
    - conflict
  target_types:
    - explicit
    - implicit

split:
  train_ratio: 0.80
  validation_ratio: 0.10
  test_ratio: 0.10
  seed: 42
  group_aware: true
  strict_leakage_failure: true

domain_adaptation:
  base_model: bert-base-uncased
  max_length: 128
  masking_probability: 0.15
  exclude_all_gold_records: true
  expected_records: 110615

context:
  no_context_token: "[NO_CONTEXT]"
  require_verified_linkage: true

evaluation:
  primary_metric: macro_f1
  random_seeds: 5
```

Keep the complete taxonomy in a separate canonical taxonomy file if that is more maintainable.

---

## 29. Required repository audit outputs

Before major implementation changes, create:

```text
docs/NEW_PIPELINE_GAP_ANALYSIS.md
artifacts/audits/new_pipeline_gap_analysis.json
docs/NEW_PIPELINE_MIGRATION_PLAN.md
```

Audit statuses:

```text
COMPLETE
PARTIAL
MISSING
CONFLICTS_WITH_NEW_REQUIREMENT
NOT_APPLICABLE
REQUIRES_DATA_CONFIRMATION
```

Every finding must include:

- requirement ID;
- status;
- evidence;
- file path;
- function, class, command, or configuration key;
- impact;
- recommended action.

---

## 30. Migration principles

1. Audit before rewriting.
2. Preserve the current working state and record the Git commit.
3. Introduce `new_pipeline_v1` behind configuration or feature flags.
4. Centralise schemas, taxonomy, counts, and labels.
5. Do not delete legacy outputs until replacements are verified.
6. Do not fabricate annotations, identifiers, context, or metrics.
7. Do not launch expensive training before data manifests and leakage tests pass.
8. Every phase must have tests and completion criteria.
9. Data, annotation, split, MLM, model, and evaluation artifacts must remain traceable.

---

## 31. Recommended implementation phases

### Phase 0: Freeze and audit

- record repository state;
- inventory entry points;
- identify active configuration;
- preserve current outputs;
- write the gap analysis.

### Phase 1: Configuration and schemas

- create `new_pipeline_v1.yaml`;
- create canonical taxonomy;
- define record and opinion schemas;
- add schema tests.

### Phase 2: Data manifests

- formalise 100,768 South African records;
- formalise 10,847 international records;
- create stable identifiers;
- create privacy and provenance reports.

### Phase 3: Sampling and annotation preparation

- implement the 1,000-record sampler;
- create label-hidden files;
- support calibration and batches;
- implement annotation validation.

### Phase 4: Gold freeze and split

- freeze the gold corpus;
- generate checksum and manifest;
- create the group-aware 80/10/10 split;
- produce leakage and distribution reports.

### Phase 5: Strict MLM corpus

- exclude all gold records;
- verify the 110,615 count;
- remove labels and predictive metadata;
- create MLM manifests.

### Phase 6: Domain adaptation

- train banking-adapted BERT;
- save tokenizer, checkpoints, logs, and environment;
- test reload and resume.

### Phase 7: Target and category models

- update BIO extraction;
- implement entity-attribute category classification;
- support zero, implicit, and multiple opinions.

### Phase 8: Intent model

- implement current-only and context-aware conditions;
- enforce genuine context;
- separate `public_warning`.

### Phase 9: Sentiment and integration

- implement no-intent, predicted-intent, and gold-intent conditions;
- update baselines;
- test pipeline propagation.

### Phase 10: Evaluation and final reporting

- implement all metrics and subgroup reports;
- run five-seed experiments;
- freeze predictions and reports;
- update research documentation.

---

## 32. Required tests

At minimum, add tests for:

- taxonomy validity;
- valid entity-attribute combinations;
- category composition;
- explicit target offsets;
- implicit target null fields;
- opinion offsets;
- zero-opinion records;
- multi-opinion records;
- duplicate record IDs;
- missing mandatory fields;
- privacy placeholders;
- exact source counts;
- annotation allocation;
- sampling determinism;
- split totals;
- source-level split totals;
- split determinism;
- group leakage;
- unlabelled corpus count;
- exclusion of all gold IDs from MLM;
- absence of task labels in MLM text;
- absence of source, bank, rating, and region feature leakage;
- `[NO_CONTEXT]` handling;
- verified context linkage;
- checkpoint reload;
- resume support;
- manifest checksum verification;
- evaluation input compatibility;
- end-to-end tuple matching.

---

## 33. Definition of done

The revised pipeline is ready for final experiments only when:

- the repository audit is complete;
- requirements are versioned;
- canonical schemas and taxonomy are active;
- the 100,768 and 10,847 source manifests pass checks;
- the 1,000-record annotation corpus is complete and frozen;
- the 800/100/100 split passes leakage checks;
- the strict MLM corpus contains exactly 110,615 records or any justified source correction is documented;
- all gold records are excluded from strict MLM;
- all baseline and integrated conditions use aligned partitions;
- experiment configurations are immutable;
- checkpoints reload successfully;
- metrics and predictions are saved;
- subgroup reports are available;
- five-seed results are reproducible;
- documentation reflects actual executable behaviour.

---

## 34. Instructions for a new Kiro session

At the beginning of a new session:

1. Read this entire file.
2. Treat this file as the authoritative requirements source.
3. Inspect the repository before proposing changes.
4. Read any existing `NEW_PIPELINE_GAP_ANALYSIS.md` and `NEW_PIPELINE_MIGRATION_PLAN.md`.
5. Compare the current Git commit to the commit recorded by the previous session.
6. Identify completed, partial, missing, and conflicting requirements using executable evidence.
7. Continue from the next incomplete migration phase.
8. Do not restart the project from assumptions.
9. Do not claim completion without tests and artifacts.
10. End the session by updating the gap analysis, migration status, and next-step handover.

Recommended first command sequence:

```bash
git status
git rev-parse HEAD
find . -maxdepth 3 -type f | sort
```

Then inspect:

```text
README files
configuration files
data manifests
schemas
taxonomy files
sampling scripts
annotation tools
validation code
split logic
MLM code
models
training entry points
evaluation code
tests
cluster scripts
saved artifacts
```

---

## 35. New-session handover response format

At the end of every Kiro session, write or update:

```text
docs/NEW_PIPELINE_SESSION_HANDOVER.md
```

It must include:

1. date and pipeline version;
2. Git commit at session start;
3. Git commit at session end, if committed;
4. requirements reviewed;
5. files inspected;
6. files created;
7. files modified;
8. tests added;
9. commands executed;
10. tests and results;
11. artifacts generated;
12. decisions made;
13. unresolved blockers;
14. data questions requiring researcher input;
15. exact next task for the following session;
16. warnings about temporary, legacy, or incomplete behaviour.

---

## 36. Immediate task for Kiro

Kiro must now:

1. read this requirements document;
2. audit the complete repository against it;
3. create the Markdown and JSON gap reports;
4. create the phased migration plan;
5. prepare low-risk versioned configuration, schemas, taxonomy scaffolding, validation utilities, and tests;
6. preserve current working functionality;
7. avoid expensive training until the data and split requirements pass validation.

The audit must be evidence-based. Repository code, configuration, manifests, tests, and executable commands are the evidence. Assumptions are not evidence.
<!-- Amendment NEW_PIPELINE_V1_SSL_U0_U1_U2_2026-10-20: the former Original BERT versus Banking MLM-BERT comparison is superseded by U0/U1/U2. See banking-tasci/banking-tasci/docs/U0_U1_U2_AMENDMENT.md for objectives, fairness controls, smoke/pilot gates, downstream matrix, failure conditions and definition of done. -->
