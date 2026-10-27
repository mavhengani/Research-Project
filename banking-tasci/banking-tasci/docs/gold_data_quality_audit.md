# Gold Data Quality Audit Report

**Project:** Banking TASCI  
**Date:** 2025-07-14  
**Scope:** Complete static inspection of the adjudicated gold dataset (600 records), split manifests, annotation files, inter-annotator agreement report, and training readiness gate — conducted before any supervised baseline training.  
**Method:** All findings are based on direct read-only inspection and execution of `scripts/audit_gold_data.py`. No annotation labels were modified, no gold labels were generated, and no models were trained.  
**Audit outputs written (read-only on source files):**
- `outputs/gold_label_distribution.json`
- `outputs/general_feedback_review_queue.jsonl` (155 entries)
- `outputs/aspect_category_review_queue.jsonl` (176 entries)
- `outputs/independent_annotation_sample_100.jsonl` (100 records)
- `outputs/gold_quality_summary.json`
- `docs/gold_data_quality_audit.md` (this report)

---

## 1. Executive Summary

The adjudicated gold dataset contains 600 records and 1,253 aspect spans. It is technically well-formed (schema validity: PASS), and the training readiness gate (all 13 Part-6 checks) passes. However, the dataset has five serious research-grade quality limitations that prevent full-scope baseline training:

1. **Three of seven configured intent labels — `suggestion`, `warning`, `churn_signal` — have zero instances** across all 600 records and in all three splits. Any baseline model trained on this data cannot predict these classes. The readiness gate passes despite this because its check 11 only verifies that eval classes exist in train, not that all configured labels are represented.

2. **Two of nine configured aspect categories — `fees` and `fraud_security` — have zero annotation instances.** Keyword analysis finds 56 records with fee-related terms and 15 records with fraud-related terms, all annotated under other categories. These are important banking service dimensions.

3. **Annotator independence is violated.** Both annotator files (`pilot_annotator_a.jsonl` and `pilot_annotator_b.jsonl`) are byte-identical. The reported inter-annotator agreement (κ = 1.00 for all metrics) is not genuine independent reliability — it is a technical pipeline verification. It must not be reported as annotation quality evidence.

4. **150 `general_feedback` records were assigned in bulk, not individually reviewed.** All 150 share the exact same boilerplate annotation note. Their intent labels cannot be considered individually validated.

5. **Zero South African records exist.** All 600 records are classified as `international`. Regional comparison (stated as a research objective) is structurally impossible with this dataset.

**Overall readiness verdict:**

| Gate | Verdict |
|---|---|
| Technical readiness gate (supervised_gate.py) | **PASS** |
| Research readiness (annotation quality, class coverage, IAA) | **FAIL** |
| Final recommendation | **PROCEED ONLY AFTER TARGETED HUMAN REVIEW** |

---

## 2. Technical Readiness vs Research Readiness

### 2.1 The gate-passes / research-fails contradiction

The supervised training gate (`src/banking_tasci/training/supervised_gate.py`) runs 13 checks. All 13 pass with the current dataset. The gate correctly verifies:
- Gold file exists and is not the unannotated pilot
- All records have valid annotation status
- Valid aspect spans exist
- Sentiment and intent labels are present
- Manifests exist and are disjoint
- Leakage groups do not cross splits
- No unannotated records appear in splits
- Classes seen in val/test are also seen in train
- A distinct validation split exists for model selection

The gate does **not** check:
- Whether all **configured** intent labels (7 in `INTENT_LABELS`) have at least one training example
- Whether all **configured** aspect categories (9 in `CATEGORIES`) have at least one training example
- Whether annotator files are distinct (independence)
- Whether minimum per-class counts are met for reliable learning
- Whether any region other than `international` is represented

This means a project can pass the full readiness gate and proceed to training while being fundamentally unable to predict 3 of 7 intended intent labels and 2 of 9 intended aspect categories.

### 2.2 Why the gate passes for check 11 specifically

Check 11 (`required_classes_in_train`) in `supervised_gate.py` (line ~183–195) computes:

```python
train_classes = _intents(train_ids)          # {'complaint','compliment','request_for_assistance','general_feedback'}
eval_classes  = _intents(val_ids) | _intents(test_ids)  # same 4 classes
unseen_at_train = eval_classes - train_classes          # empty set
required_ok = len(train_classes) >= 2 and not unseen_at_train  # True and True = True
```

Because `suggestion`, `warning`, and `churn_signal` appear in neither eval nor train, `unseen_at_train` is the empty set, and the check passes. The gate's logic is internally consistent — it prevents training on labels the model never saw. But it permits training while those three labels silently produce zero recall.

### 2.3 What the readiness.py gate checks

`readiness.py` applies a simpler check (Phase 3A requirement 30.1): does the gold file exist, do the manifests exist, and is there at least one completed record with a non-empty intent? All three conditions are met. This gate is correctly documented as a minimal existence check, not a quality gate.

---

## 3. Complete Label Distributions

### 3.1 Intent distribution — all configured labels including zeros

| Intent label | Full (600) | % | Train (420) | % | Val (91) | % | Test (89) | % |
|---|---|---|---|---|---|---|---|---|
| `complaint` | 174 | 29.0 | 122 | 29.0 | 26 | 28.6 | 26 | 29.2 |
| `compliment` | 36 | 6.0 | 25 | 6.0 | 6 | 6.6 | 5 | 5.6 |
| `request_for_assistance` | 117 | 19.5 | 82 | 19.5 | 18 | 19.8 | 17 | 19.1 |
| `general_feedback` | 273 | 45.5 | 191 | 45.5 | 41 | 45.1 | 41 | 46.1 |
| **`suggestion`** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |
| **`warning`** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |
| **`churn_signal`** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |

#### Intent distribution by region

| Intent label | International (600) | South African (0) |
|---|---|---|
| `complaint` | 174 | 0 |
| `compliment` | 36 | 0 |
| `request_for_assistance` | 117 | 0 |
| `general_feedback` | 273 | 0 |
| `suggestion` | 0 | 0 |
| `warning` | 0 | 0 |
| `churn_signal` | 0 | 0 |

#### Intent distribution by source

| Intent label | Tweets (407) | Reviews (193) |
|---|---|---|
| `complaint` | 119 | 55 |
| `compliment` | 5 | 31 |
| `request_for_assistance` | 98 | 19 |
| `general_feedback` | 185 | 88 |
| `suggestion` | 0 | 0 |
| `warning` | 0 | 0 |
| `churn_signal` | 0 | 0 |

#### Intent distribution by context availability

| Intent label | Context available (152) | No context (448) |
|---|---|---|
| `complaint` | 49 | 125 |
| `compliment` | 25 | 11 |
| `request_for_assistance` | 18 | 99 |
| `general_feedback` | 60 | 213 |
| `suggestion` | 0 | 0 |
| `warning` | 0 | 0 |
| `churn_signal` | 0 | 0 |

### 3.2 Aspect category distribution — all configured labels including zeros

| Category | Full (1253) | % | Train (884) | Val (195) | Test (174) |
|---|---|---|---|---|---|
| `customer_support` | 292 | 23.3 | 199 | 46 | 47 |
| `digital_banking` | 75 | 6.0 | 49 | 10 | 16 |
| `transactions` | 319 | 25.5 | 234 | 50 | 35 |
| `cards` | 123 | 9.8 | 93 | 15 | 15 |
| `accounts` | 217 | 17.3 | 148 | 40 | 29 |
| **`fees`** | **0** | **0** | **0** | **0** | **0** |
| **`fraud_security`** | **0** | **0** | **0** | **0** | **0** |
| `branch_service` | 55 | 4.4 | 38 | 7 | 10 |
| `general_service` | 172 | 13.7 | 123 | 27 | 22 |

#### Category distribution by region

| Category | International (1253) | South African (0) |
|---|---|---|
| `customer_support` | 292 | 0 |
| `digital_banking` | 75 | 0 |
| `transactions` | 319 | 0 |
| `cards` | 123 | 0 |
| `accounts` | 217 | 0 |
| `fees` | 0 | 0 |
| `fraud_security` | 0 | 0 |
| `branch_service` | 55 | 0 |
| `general_service` | 172 | 0 |

#### Category distribution by source (tweets / reviews)

| Category | Tweets | Reviews |
|---|---|---|
| `customer_support` | 217 | 75 |
| `digital_banking` | 56 | 19 |
| `transactions` | 229 | 90 |
| `cards` | 84 | 39 |
| `accounts` | 143 | 74 |
| `fees` | 0 | 0 |
| `fraud_security` | 0 | 0 |
| `branch_service` | 26 | 29 |
| `general_service` | 131 | 41 |

#### Category distribution by context availability

| Category | Context available | No context |
|---|---|---|
| `customer_support` | 85 | 207 |
| `digital_banking` | 24 | 51 |
| `transactions` | 109 | 210 |
| `cards` | 43 | 80 |
| `accounts` | 80 | 137 |
| `fees` | 0 | 0 |
| `fraud_security` | 0 | 0 |
| `branch_service` | 28 | 27 |
| `general_service` | 47 | 125 |

### 3.3 Sentiment distribution — all configured labels

| Sentiment | Full (1253) | % | Train (884) | % | Val (195) | % | Test (174) | % |
|---|---|---|---|---|---|---|---|---|
| `negative` | 506 | 40.4 | 349 | 39.5 | 83 | 42.6 | 74 | 42.5 |
| `neutral` | 581 | 46.4 | 410 | 46.4 | 96 | 49.2 | 75 | 43.1 |
| `positive` | 166 | 13.2 | 125 | 14.1 | 16 | 8.2 | 25 | 14.4 |

#### Sentiment by region

| Sentiment | International | South African |
|---|---|---|
| `negative` | 506 | 0 |
| `neutral` | 581 | 0 |
| `positive` | 166 | 0 |

#### Sentiment by source

| Sentiment | Tweets | Reviews |
|---|---|---|
| `negative` | 362 | 144 |
| `neutral` | 369 | 212 |
| `positive` | 81 | 85 |

#### Sentiment by context availability

| Sentiment | Context available | No context |
|---|---|---|
| `negative` | 213 | 293 |
| `neutral` | 142 | 439 |
| `positive` | 61 | 105 |

---

## 4. Readiness Gate Contradiction Analysis

### 4.1 Exact code reference — check 11 in supervised_gate.py

File: `src/banking_tasci/training/supervised_gate.py`, lines 183–198:

```python
def _intents(ids: set[str]) -> set[str]:
    out: set[str] = set()
    for rid in ids:
        rec = id_to_record.get(rid)
        intent = getattr(rec, "intent", None)
        if intent in INTENT_LABELS:
            out.add(intent)
    return out

train_classes = _intents(train_ids)
eval_classes = _intents(val_ids) | _intents(test_ids)
unseen_at_train = eval_classes - train_classes
required_ok = len(train_classes) >= 2 and not unseen_at_train
add("required_classes_in_train", required_ok, ...)
```

**Answers to the specific audit questions about check 11:**

1. **Does it compare train classes against ALL 7 configured INTENT_LABELS?** No. It only compares the classes appearing in eval against the classes appearing in train. If a configured label appears in neither eval nor train, it is invisible to this check.

2. **Does it only check that classes seen in val/test are also seen in train?** Yes. This is the only thing check 11 verifies. It prevents "unseen at training" errors but does not catch absent configured labels.

3. **Does it check fees/fraud_security category coverage?** No. Check 11 only concerns intent labels. No check in the gate verifies that all configured aspect categories are represented in training data.

4. **Does it check sentiment coverage?** No. No check in the gate verifies sentiment label coverage.

5. **Does it apply minimum per-class count thresholds?** No. It only checks `len(train_classes) >= 2` (at least two distinct intent labels present), with no per-class floor.

### 4.2 Consequence

Because `suggestion`, `warning`, and `churn_signal` are absent from the corpus entirely (not in train, not in val, not in test), `unseen_at_train` is empty, the boolean condition is True, and the check passes. The gate's internal logic is consistent — it prevents the specific failure mode it was designed to catch. However, it cannot detect the broader research-grade failure of absent configured labels.

### 4.3 Proposed gate enhancement (not applied — for research team review)

```python
# After the existing required_classes_in_train check:
all_configured = set(INTENT_LABELS)
zero_in_corpus = all_configured - _intents(set(id_to_record.keys()))
if zero_in_corpus:
    add("all_configured_intents_in_corpus", False,
        f"Configured intent labels with zero gold examples: {sorted(zero_in_corpus)}")
```

This would surface `suggestion`, `warning`, `churn_signal` as explicit FAIL items. The proposed check does not modify `required_classes_in_train`; it is additive.

---

## 5. The 150 Corrected general_feedback Records — Audit

### 5.1 Origin and identification

Annotator A left exactly 150 records without an intent label (intent field = `null`). These are identifiable by cross-referencing `pilot_annotator_a.jsonl` (null intent) against `pilot_adjudicated.jsonl` (intent = `"general_feedback"`). The audit script confirmed exactly 150 such records.

### 5.2 Evidence of bulk assignment

All 150 records share an **identical annotation note**:

> "Not clearly about a banking product, service, transaction, account, or customer issue."

This note is word-for-word identical across all 150 records. No record carries any individualized or record-specific note. All 150 have zero aspect spans. This is consistent with a fill-in-blanks or batch-replace operation applied uniformly to all null-intent records rather than per-record human judgement.

### 5.3 Content analysis

Examination of the 150 records reveals three broad groups:

- **Genuinely off-topic records** (political commentary, unrelated celebrities, spam-like content): `general_feedback` is defensible as a catch-all, but `excluded`/no-label would be more principled for downstream analysis.
- **Ambiguous records** (banking context implicit but not explicit, e.g. waiting for money reversal, account-related frustration expressed indirectly): the `general_feedback` assignment suppresses what may be `complaint` or `request_for_assistance` signals.
- **Borderline records** from multi-sentence review splits (e.g. record `64e7658739aa2632` split into ~150 sentence records, some of which are clearly general context-setting sentences): bulk assignment is defensible here but should be documented.

### 5.4 Impact on the general_feedback class

- Total `general_feedback` records: 273 (45.5% of corpus)
- Of these, 150 (54.9%) were bulk-assigned without individual review
- Only 123 (45.1%) received `general_feedback` through individual annotation
- The `general_feedback` class is therefore the least reliably annotated class in the dataset despite being the most frequent

### 5.5 Review queue

`outputs/general_feedback_review_queue.jsonl` — 155 entries (150 bulk-assigned + 5 keyword-matched records for cross-check) with fields: `record_id`, `text`, `current_intent`, `original_intent_known`, `review_reason`, and blank `human_review_decision` / `human_review_notes`.

---

## 6. Zero-Count Intent Class Audit — suggestion, warning, churn_signal

### 6.1 Counts

All three classes have zero instances across all 600 records and all three splits.

### 6.2 Keyword scan results

The audit script searched all record texts for intent-revealing keywords:

**suggestion keywords** (`suggest`, `recommend`, `should improve`, `please add`, etc.):
- Matches: **1 record**
- Current intent of that record: `general_feedback`
- Implication: extremely sparse — only 1 of 600 records contains suggestion-indicating language, and it was labelled `general_feedback`.

**warning keywords** (`beware`, `avoid this bank`, `stay away`, `dangerous`, `unsafe`, etc.):
- Matches: **0 records**
- Implication: no warning language in the corpus at all.

**churn_signal keywords** (`closing my account`, `switching banks`, `leaving this bank`, `cancel my account`, etc.):
- Matches: **4 records**
- Current intents: `request_for_assistance` (2), `complaint` (1), `general_feedback` (1)
- Implication: these 4 records contain churn-adjacent language but were annotated as other classes; none were labelled `churn_signal`.

### 6.3 Interpretation

The keyword scan reveals that the zero counts are **genuine data sparsity**, not annotation error. The source corpus (international bank tweets, generic bank reviews) genuinely contains almost no suggestion, warning, or churn-signal content. The single suggestion-keyword match and four churn-keyword matches were correctly or defensibly annotated as other labels (the annotator may have applied stricter criteria than keyword presence alone).

### 6.4 Consequence for models

Any baseline model trained on this dataset will have a recall of 0.00 for `suggestion`, `warning`, and `churn_signal`. If evaluation uses macro-averaged F1 over all 7 intent labels, those three absent classes will contribute F1 = 0.00 each, masking true performance on the four observed classes. **Macro-F1 must be computed over observed classes only (4 labels) until absent-label data is added.**

---

## 7. fees and fraud_security — Category Coverage Audit

### 7.1 Zero-count confirmation

Both `fees` and `fraud_security` have zero aspect span annotations in all 600 records across all splits.

### 7.2 Keyword scan — fees (56 matching records)

56 records contain fee-related keywords: `fee`, `fees`, `charge`, `charges`, `charged`, `maintenance fee`, `service fee`, `sms charge`, `transaction fee`, `deduction`, `levy`, `penalty`.

Current categories annotated on those 56 records:
- `transactions` — most common (fee-related debits annotated as transaction events)
- `accounts` — charges framed as account-level issues
- `customer_support` — complaint about a fee escalated to support
- `cards` — ATM or card service fees
- `general_service` — general service-level fee mentions
- **`fees` — 0 (zero)**

Representative examples:
- *"I can do N number of time transaction with no charges"* — annotated `transactions`, `fees` also defensible
- *"deducted refuse credit"* — annotated `transactions`; a charge-refusal may qualify as `fees`
- *"sms alert charge"* implied in multiple records — consistently annotated as `transactions`

### 7.3 Keyword scan — fraud_security (15 matching records)

15 records contain fraud-related keywords: `fraud`, `fraudulent`, `scam`, `hacked`, `unauthorised`, `unauthorized`, `phishing`, `stolen`, `compromised`, `identity theft`, `suspicious transaction`, `security`.

Current categories:
- `accounts` — fraud resulting in account issues
- `customer_support` — fraud complaint directed at bank support
- `transactions` — fraudulent transaction events
- **`fraud_security` — 0 (zero)**

Representative examples:
- *"customer detail akeem rafiu defrauded"* — annotated `accounts`/`customer_support`; `fraud_security` is arguable
- *"unauthorised transaction"* phrasing found in multiple records — annotated `transactions`
- *"phishing"* mentioned in one record — annotated `general_service`

### 7.4 Assessment

Both `fees` and `fraud_security` appear to have been systematically under-applied. The annotator consistently chose more general categories (`transactions`, `accounts`, `customer_support`) when the record contained fee or fraud content. This may reflect annotation guideline ambiguity at the boundary between category-specific and general labels.

**This is not necessarily annotation error.** The guidelines' distinction between transaction events and recurring fee charges, and between general account security and explicit fraud reports, is genuinely difficult in short, noisy social media text. The under-application is likely systematic but may be appropriate for the text style of the corpus.

### 7.5 Review queue

`outputs/aspect_category_review_queue.jsonl` — 176 entries covering:
- Fee-keyword records where the annotated category is not `fees`
- Fraud-keyword records where the annotated category is not `fraud_security`

Each entry includes `record_id`, `text`, `aspect_term`, `current_category`, `current_sentiment`, `review_reason`, and blank `human_review_category` / `human_review_notes`.

---

## 8. Sentiment Quality Audit

### 8.1 Sentiment distribution per aspect category

| Category | negative | neutral | positive | dominant |
|---|---|---|---|---|
| `customer_support` | 85 | 174 | 33 | neutral (59.6%) |
| `digital_banking` | 27 | 27 | 21 | balanced |
| `transactions` | 192 | 93 | 34 | negative (60.2%) |
| `cards` | 57 | 51 | 15 | negative (46.3%) |
| `accounts` | 81 | 109 | 27 | neutral (50.2%) |
| `fees` | 0 | 0 | 0 | absent |
| `fraud_security` | 0 | 0 | 0 | absent |
| `branch_service` | 12 | 26 | 17 | neutral (47.3%) |
| `general_service` | 52 | 101 | 19 | neutral (58.7%) |

### 8.2 Neutral-as-default overuse check

- **138 records** have aspects where ALL aspect spans are labelled `neutral`
- **167 records** with multiple aspects have uniform sentiment across all spans (all same label)
- 140 records with uniform-neutral + multiple spans: strong signal that `neutral` is being used as a default when sentiment is ambiguous rather than genuinely assessed

### 8.3 Sentiment per intent class

| Intent | negative (dominant) | neutral | positive |
|---|---|---|---|
| `complaint` | High (most aspects) | Some | Very few |
| `compliment` | Very few | Some | High |
| `request_for_assistance` | Mixed | High neutral | Some |
| `general_feedback` | Mixed | High neutral | Some |

The pattern is broadly plausible: complaints are negative, compliments are positive, requests are neutral-dominant. However, the `customer_support` category showing 174 neutral out of 292 spans (59.6%) is notable — customer support is frequently the subject of complaints, yet 59.6% are neutral. This may reflect a guideline where the act of contacting support is treated as neutral even when the overall tone is negative.

### 8.4 Positive sentiment in validation

Only 16 positive-sentiment spans in the validation set (8.2% vs 14.1% in train). This imbalance means validation-set sentiment F1 for `positive` will be based on a very small sample and may be unreliable for measuring generalisation.

---

## 9. South African Coverage

### 9.1 Counts

| Region | All records | Train | Val | Test |
|---|---|---|---|---|
| `international` | 600 (100%) | 420 | 91 | 89 |
| South African | **0 (0%)** | 0 | 0 | 0 |

There are zero South African records in the gold dataset. All 600 records are tagged `region: international`, originating from `sampledbanktweet.csv` (Twitter data, West/East African banks) and `bank_reviews3.csv` (Indian bank reviews, classified as international). No South African source was ingested during Phase 1.

### 9.2 Consequence for research objectives

- **Regional comparison is structurally impossible** with the current dataset.
- Research objective 7 (*"How do international and South African banking feedback results differ?"*) cannot be addressed.
- No metric, table, or figure in the paper should present a regional comparison.
- South African data collection (e.g. Hellopeter reviews, FNB/Standard Bank/Absa/Nedbank/Capitec Twitter data) and independent annotation of a representative sample is required before any SA-vs-international claim can be made.

---

## 10. Context-Aware Training Suitability

### 10.1 Context availability statistics

| Split | context_available = True | context_available = False | % context |
|---|---|---|---|
| Train | 103 | 317 | 24.5% |
| Validation | 23 | 68 | 25.3% |
| Test | 26 | 63 | 29.2% |
| **Total** | **152** | **448** | **25.3%** |

Context-available records come exclusively from the `bank_reviews` source (all 152 context-available records are reviews; tweets are inherently context-free). Context-available and context-unavailable splits are therefore confounded with source type.

### 10.2 Context consistency check

- Records where `context_available = True` but `previous_text` is `[NO_CONTEXT]` or empty: **0** (no inconsistencies)
- Records where `context_available = False` but `previous_text` is non-empty/non-null: **0** (no inconsistencies)

The context availability flag is internally consistent with the `previous_text` field.

### 10.3 Intent distribution by context

Context-available records have a notably different intent distribution:
- `compliment` is 25/152 = 16.4% in context-available vs 11/448 = 2.5% in no-context
- `complaint` is 49/152 = 32.2% vs 125/448 = 27.9% in no-context

The higher `compliment` rate in context-available records reflects the review source (structured bank reviews contain more positive content than Twitter complaints).

### 10.4 Suitability for context-aware GRU

103 context-available training records is a small but workable sample for testing whether context changes predictions. The model will learn context representations from only those 103 examples. Statistical conclusions about context impact should be treated as preliminary. A controlled ablation comparing context-available vs context-unavailable subsets is recommended in addition to the full-set evaluation.

---

## 11. Independent Annotation Limitation — Formal Statement

### 11.1 Statement of fact

`data/annotations/pilot_annotator_a.jsonl` and `data/annotations/pilot_annotator_b.jsonl` are **byte-identical**. Every record ID, intent, aspect list, span offset, sentiment, and annotation note is identical between the two files. The `annotator_id` field differs (`annotator_a` vs `annotator_b`) but all substantive content is a copy.

`outputs/inter_annotator_agreement.json` reports:

| Metric | Value |
|---|---|
| joint_record_count | 600 |
| intent_kappa | 1.00 |
| category_kappa | 1.00 |
| sentiment_kappa | 1.00 |
| exact_span_agreement | 1.00 |
| token_level_F1 | 1.00 |
| disagreement_counts_by_type | {} |

These values are mathematically guaranteed when both input files are identical. They do not constitute annotation reliability evidence.

### 11.2 Required methodology wording

**For the research paper — methodology section:**

> "Initial annotation of the 600-record pilot dataset was performed by a single annotator. A second annotator file was generated for inter-annotator agreement (IAA) pipeline testing; however, it was confirmed post-hoc that both files were identical in content. The IAA metrics reported by the agreement calculation script (Cohen's κ = 1.00 for all dimensions) therefore reflect a technical verification of the agreement pipeline, not independent annotation reliability. These values must not be interpreted as evidence of annotation quality or inter-rater consistency."

**For the limitations section:**

> "Genuine independent inter-annotator agreement was not measured for this dataset. The gold annotation is based on a single annotator's judgements. Researchers citing these annotations or extending this work should conduct independent dual annotation of a representative subset (we recommend a minimum of 100 records, stratified by intent class and source) and report the resulting Cohen's κ before making claims about annotation reliability."

---

## 12. Independent 100-Record Sample for Second Annotation

A stratified 100-record sample has been written to `outputs/independent_annotation_sample_100.jsonl`. The sample is gold-label-stripped — all `intent`, `aspects`, `intent_ambiguous`, and `alternative_intent` fields are blanked for the independent annotator.

### 12.1 Sampling strategy

| Intent class | Target | Rationale |
|---|---|---|
| `complaint` | 29 | Proportional to corpus (29.0%) |
| `compliment` | 6 | Proportional to corpus (6.0%) |
| `request_for_assistance` | 20 | Proportional to corpus (19.5%) |
| `general_feedback` | 45 | Proportional to corpus (45.5%) |

Priority order within each intent bucket:
1. Records in the corrected-GF set (bulk-assigned `general_feedback`) — for independent verification
2. Records matching suggestion/warning/churn keywords — for cross-validation
3. Context-available records — to ensure proportional context representation
4. Remaining records in alphabetical order by record_id

### 12.2 Coverage achieved

- 100 records drawn from 4 intent classes
- Context-available records: approximately 25 (proportional)
- Records with at least one aspect span: approximately 71 (proportional to 426/600)
- Includes records from both tweet and review sources
- `suggestion`, `warning`, `churn_signal` cannot be sampled as they have zero gold instances

### 12.3 Protocol for use

The independent annotator should be given only `outputs/independent_annotation_sample_100.jsonl` with:
- `record_id`, `source`, `region`, `text`, `previous_text`, `context_available` visible
- `intent`, `aspects`, `intent_ambiguous`, `alternative_intent` blank

After independent annotation is complete, compute Cohen's κ against the gold labels using the project's `scripts/calculate_agreement.py`. The resulting κ is the first genuine IAA measurement for this project.

---

## 13. Task-Specific Readiness Verdicts

### 13.1 BIO aspect extraction — READY WITH LIMITATIONS

**Status: READY WITH LIMITATIONS**

- 1,253 aspect spans across 426 records; average 2.94 spans per span-bearing record
- 174 records (29%) have zero aspects — valid negative training examples
- Span boundary quality: checked by readiness gate (valid offsets, term matches text)
- **Limitation:** `fees` (0 spans) and `fraud_security` (0 spans) cannot be extracted. Evaluation of aspect extraction must exclude or caveat these two categories.
- **Limitation:** Keyword analysis identifies 56 fee-candidate and 15 fraud-candidate records that may require re-annotation before claiming comprehensive aspect coverage.

### 13.2 Intent classification — 4-class observed only — READY WITH LIMITATIONS

**Status: READY WITH LIMITATIONS**

- 4 of 7 configured intent labels present with sufficient training examples
- Training support: complaint 122, general_feedback 191, request_for_assistance 82, compliment 25
- All four classes present in train, val, and test
- **Limitation:** `suggestion` (0), `warning` (0), `churn_signal` (0) cannot be trained or evaluated. Report macro-F1 over 4 observed classes only.
- **Limitation:** `compliment` has 25 training instances — below the 30-instance threshold commonly recommended for reliable classification; performance on this class may be unreliable.
- **Limitation:** `general_feedback` dominates at 45.5%; trained classifiers may show positive bias toward this label.

### 13.3 Intent classification — 7-class configured — NOT READY

**Status: NOT READY**

Three of seven configured classes (`suggestion`, `warning`, `churn_signal`) have zero instances. No 7-class classifier can be trained or meaningfully evaluated until these labels are added to the gold dataset.

### 13.4 Aspect-level sentiment classification — READY WITH LIMITATIONS

**Status: READY WITH LIMITATIONS**

- All three sentiment classes present with training support: negative 349, neutral 410, positive 125
- Context-available sentiment: negative 213, neutral 142, positive 61
- **Limitation:** Only 16 positive-sentiment spans in validation — F1 for positive class in validation will be based on a very small sample.
- **Limitation:** 138 records with all-neutral aspects; 167 multi-aspect records with uniform sentiment suggest systematic neutral over-assignment.
- **Limitation:** `fees` and `fraud_security` sentiment cannot be measured at all.

### 13.5 Context-aware GRU intent classification — READY WITH LIMITATIONS

**Status: READY WITH LIMITATIONS**

- 103 context-available training records; 23 in validation; 26 in test
- All four intent classes present in both context-available and no-context subsets (though `compliment` is very sparse in no-context: 11 instances total)
- **Limitation:** Context-available records are entirely from the `bank_reviews` source. Any context effect may be confounded with source-type differences.
- **Limitation:** 103 training examples is a small sample for learning context representations; improvements may not be statistically significant.

### 13.6 SA vs International comparison — NOT READY

**Status: NOT READY**

Zero South African records exist. Regional comparison is structurally impossible.

### 13.7 SVM intent classifier — READY WITH LIMITATIONS

**Status: READY WITH LIMITATIONS**

SVM with TF-IDF or bag-of-words features is feasible for 4-class intent classification on 420 training records. The feature space is suitable for SVM. The same class coverage limitations as 13.2 apply.

### 13.8 SVM sentiment classifier — READY WITH LIMITATIONS

**Status: READY WITH LIMITATIONS**

SVM for 3-class aspect-level sentiment is feasible on 884 training aspect spans. The `positive` class is underrepresented (125 training spans). Weighted SVM or balanced class weights recommended.

### 13.9 BiLSTM intent classifier — READY WITH LIMITATIONS

**Status: READY WITH LIMITATIONS**

BiLSTM on 420 training records is at the low end of what is reliable for a neural sequence model. Results should be interpreted cautiously. The same class coverage limitations as 13.2 apply.

### 13.10 BiLSTM sentiment classifier — READY WITH LIMITATIONS

**Status: READY WITH LIMITATIONS**

BiLSTM for aspect-level sentiment on 884 spans is feasible. The same sentiment limitations as 13.4 apply.

### 13.11 BERT BIO aspect extraction — READY WITH LIMITATIONS

**Status: READY WITH LIMITATIONS**

BERT fine-tuning for BIO tagging on 600 records / 1,253 spans is at the low end but feasible for a pilot study. The same aspect category limitations as 13.1 apply. Pre-training on a larger banking corpus is recommended.

### 13.12 BERT intent classifier — READY WITH LIMITATIONS

**Status: READY WITH LIMITATIONS**

BERT fine-tuning for 4-class intent on 420 training records is feasible for a pilot. Same class coverage limitations as 13.2 apply.

### 13.13 BERT aspect sentiment classifier — READY WITH LIMITATIONS

**Status: READY WITH LIMITATIONS**

BERT fine-tuning for 3-class aspect sentiment on 884 training spans is feasible. Same sentiment limitations as 13.4 apply.

---

## 14. Recommended Label Strategy

The following label strategy is recommended for baseline training and reporting:

| Task | Labels to use | Labels to exclude until data added |
|---|---|---|
| Intent classification | complaint, compliment, request_for_assistance, general_feedback (4 classes) | suggestion, warning, churn_signal |
| Aspect category extraction | customer_support, digital_banking, transactions, cards, accounts, branch_service, general_service (7 categories) | fees, fraud_security |
| Sentiment classification | negative, neutral, positive (3 classes) | None |

**For evaluation metrics:**
- Report macro-F1, per-class F1, and weighted F1 separately
- Macro-F1 must be computed over observed classes only (4 intent, 7 category)
- Explicitly state in all tables: *"Macro-F1 computed over 4 observed intent classes; suggestion, warning, churn_signal excluded (zero training instances)"*
- Report category-level aspect F1 for 7 observed categories; explicitly note fees and fraud_security are not evaluated

---

## 15. Recommended Correction Plan

The following actions are recommended, roughly in priority order:

### 15.1 Priority 1 — Human review before any baseline training

**Review the 150 bulk-assigned general_feedback records**
- Use `outputs/general_feedback_review_queue.jsonl` (155 entries)
- A human annotator must individually read each record and confirm or revise the `general_feedback` assignment
- Record the decision in `human_review_decision` and `human_review_notes`
- Time estimate: 2–4 hours for 155 records

### 15.2 Priority 2 — Human review before claiming full category coverage

**Review the fees and fraud_security queues**
- Use `outputs/aspect_category_review_queue.jsonl` (176 entries)
- A human annotator must determine whether each flagged aspect span should be re-categorised to `fees` or `fraud_security`
- If re-annotation is warranted: update the adjudicated gold file (maintaining a version history), re-run `scripts/create_splits.py`, and re-run the readiness gate
- Time estimate: 3–6 hours for 176 records

### 15.3 Priority 3 — Independent annotation for genuine IAA

**Conduct independent second annotation of the 100-record sample**
- Use `outputs/independent_annotation_sample_100.jsonl`
- Assign to a second annotator who has not seen the gold labels
- After annotation, run `scripts/calculate_agreement.py` with the new annotation file against the gold
- Report the resulting κ in the paper as the genuine IAA metric
- Time estimate: 4–8 hours for 100 records

### 15.4 Priority 4 — Absent label data collection

**Collect and annotate suggestion, warning, and churn_signal examples**
- Source: targeted collection from bank complaint forums, social media, review platforms
- Minimum recommended: 30–50 examples per class for reliable classification
- Integrate into the gold dataset and re-run splits and readiness gate
- This is required before any 7-class intent classification can be reported

### 15.5 Priority 5 — South African data collection

**Collect and annotate South African banking feedback data**
- Source: Hellopeter, FNB/Standard Bank/Absa/Nedbank/Capitec Twitter/social media
- Target: minimum 150–200 records for a meaningful regional comparison
- Required before research objective 7 (regional comparison) can be addressed

### 15.6 Priority 6 — Readiness gate enhancement

**Update supervised_gate.py to warn on absent configured labels**
- Add the proposed check from Section 4.3
- This prevents future datasets from silently missing configured labels
- This modification is a gate enhancement only — it does not change gold labels

---

## 16. Suitable Methodology Limitations Wording

The following paragraphs are suitable for direct use in the research paper:

### 16.1 Dataset limitations paragraph

> "The gold dataset comprises 600 records drawn exclusively from international banking sources (West/East African bank tweets and generic Indian bank reviews). No South African records were included in the pilot annotation phase, and the regional comparison objective requires a separate data collection and annotation effort. Of the seven configured intent labels, three (`suggestion`, `warning`, `churn_signal`) have zero instances in the corpus, reflecting genuine data sparsity in the source texts rather than annotation error; all reported intent classification results cover four observed labels only. Two of nine aspect categories (`fees`, `fraud_security`) have zero annotation instances; aspect extraction and category-level sentiment results cover seven categories only."

### 16.2 Annotation reliability paragraph

> "Annotation of the pilot dataset was performed by a single annotator. An inter-annotator agreement pipeline check was conducted using a duplicate of the annotator's file; the resulting Cohen's κ of 1.00 for all metrics is a technical verification result, not a measure of annotation reliability. Genuine inter-annotator agreement was not measured for this dataset. The 150 records with null intent after annotation were assigned the `general_feedback` label in bulk; these assignments were not individually reviewed and should be treated as provisional. Researchers extending or citing this work are advised to conduct independent dual annotation of a representative sample and report the resulting κ before making claims about annotation quality."

### 16.3 Scope of results paragraph

> "All baseline training, evaluation, and reported metrics are scoped to the four observed intent classes, seven observed aspect categories, and three sentiment classes with non-zero training support. Results are not generalisable to `suggestion`, `warning`, `churn_signal` (no training data), `fees` (no training data), or `fraud_security` (no training data), nor to South African banking feedback (no data collected). Context-aware model results are based on 103 training records with prior-context available (24.5% of training set), all from the bank review source; context effects may be confounded with source type."

---

## 17. Final Recommendation

### Verdict: PROCEED ONLY AFTER TARGETED HUMAN REVIEW

**Justification by dimension:**

| Dimension | Verdict | Justification |
|---|---|---|
| Schema validity | PROCEED | All 600 records pass schema validation; no structural errors |
| Annotation provenance | TARGETED REVIEW REQUIRED | 150 bulk-assigned GF records need individual human confirmation; the annotator-B file is a copy (no genuine IAA) |
| Class coverage (intent) | TARGETED REVIEW REQUIRED | 3/7 intent classes absent; cannot proceed to 7-class training; 4-class training can proceed after GF review |
| Class coverage (categories) | TARGETED REVIEW REQUIRED | 2/9 categories absent; 56-record fees queue and 15-record fraud queue need review before claiming full category coverage |
| Context coverage | PROCEED WITH LIMITATION | 25.3% context-available; sufficient for pilot context-aware models with stated limitations |
| Regional coverage | NOT READY FOR REGIONAL COMPARISON | Zero South African records; all regional comparison objectives deferred |

**Minimum required actions before baseline training:**

1. Human review of the 155-record `general_feedback_review_queue.jsonl` — confirm or revise bulk assignments
2. If >10% of GF records are revised, regenerate splits and re-run readiness gate
3. Record IAA limitation clearly in paper methodology

**Permitted to proceed immediately under stated limitations:**

- Baseline training on 4-class intent (complaint, compliment, request_for_assistance, general_feedback)
- Baseline training on 7-category aspect extraction (excluding fees and fraud_security)
- Baseline training on 3-class sentiment
- Provided paper reports: 4-class scope, absent-label caveat, single-annotator status, zero-SA caveat

**Not permitted until correction plan steps are completed:**

- Reporting 7-class intent F1
- Reporting fees or fraud_security aspect extraction F1
- Reporting any South African or regional comparison result
- Claiming genuine IAA based on the κ = 1.00 pipeline check result

---

*Audit completed. No annotation files or manifests were modified. All generated files are in `outputs/`. Script: `scripts/audit_gold_data.py`.*
