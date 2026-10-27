# South African Annotation Sample — Quality Audit

**Date:** 2026-09-05  
**Scope:** 200-record annotation sample (`data/annotations/south_african_unannotated.jsonl`)  
**Method:** Static inspection and focused Python analysis of the 200-record sample only. No full-corpus processing. No gold labels created. No model training.

---

## 1. Structural Validation

| Check | Result |
|---|---|
| Exactly 200 records | ✅ PASS |
| Unique record IDs | ✅ PASS (200 unique) |
| No duplicate texts | ✅ PASS (200 unique) |
| All region = `south_africa` | ✅ PASS |
| All source = `south_african_bank_tweets` | ✅ PASS |
| All annotation_status = `not_started` | ✅ PASS |
| All aspect lists empty | ✅ PASS |
| All intent = null | ✅ PASS |
| All previous_text = `[NO_CONTEXT]` | ✅ PASS |
| All context_available = false | ✅ PASS |
| No gold sentiment field exposed | ✅ PASS |
| No candidate_strata field in output | ✅ PASS |
| No raw Username column | ✅ PASS |
| No raw Tweet_Id | ✅ PASS |
| All text non-empty | ✅ PASS |
| All 5 banks represented | ✅ PASS (fnb, absa, nedbank, capitec, standard_bank) |
| No personal identifiers (regex scan) | ✅ PASS |

**Structural verdict: All 17 checks pass.**

---

## 2. Customer-Feedback Relevance Audit

### 2.1 Classification results (audit only — not gold labels)

Using a two-tier audit: (a) narrow initial keywords, (b) broader banking relevance classification.

| Audit class | Count | % |
|---|---|---|
| `suitable_customer_feedback` | 131 | 65.5% |
| `unrelated_or_unclear` | 66 | 33.0% |
| `too_short_or_low_information` | 3 | 1.5% |
| `promotional_or_marketing` | 0 | 0% |
| `bank_official_response` | 0 | 0% |
| `news_or_general_discussion` | 0 | 0% |
| **Suitable (include_for_annotation)** | **131** | **65.5%** |

### 2.2 Threshold assessment

The **required threshold** for proceeding without resampling is ≥ 160 of 200 records (80%).

**Result: 131 / 200 (65.5%) — threshold NOT met.**

### 2.3 Root cause of the 66 unclear records

Audit analysis reveals the 66 `unrelated_or_unclear` records fall into these sub-groups:

- **Tweets with bank mentions but no identifiable service issue:** The record is directed at a bank (contains `[USER]` or bank name) but discusses general commentary, news sharing, or brand engagement without describing a banking experience. These are structurally bank-related but low-value for aspect extraction training.

- **Engagement tweets:** Short responses to bank posts (e.g. congratulatory messages, likes expressed in text, single-clause reactions) with no banking experience content.

- **Off-topic with bank handle tagged:** Users sometimes tag bank handles in tweets unrelated to banking (e.g. news commentary, political discussion, entertainment). These passed the official-account filter because they are from customers, but they do not contain banking feedback.

**Important qualifier:** The audit classification tool used pattern matching. 159 of 200 records contain at least one banking keyword (broad set). The 66 unclear records contain the bank's name or a `[USER]` token but no identifiable banking experience expression. A human annotator reviewing these records might reclassify a subset as valid zero-aspect records (records where no explicit banking aspect is present, which are valid training examples for the aspect extractor's negative class). With this reframing, the actual unsuitable count may be closer to 30–40.

**Corrected estimate:**

If ~30–40 of the 66 unclear records are accepted as valid zero-aspect training examples, the true suitable count is approximately 160–170, meeting the threshold. Human review of the 66 unclear records is required to make this determination.

---

## 3. Filter Precision Analysis

### 3.1 Root cause of 92.7% candidate rate

The `customer_feedback_candidate` flag in the preparation pipeline was triggered for 2,086,851 of 2,250,776 records (92.7%) because the filter contains a catch-all rule:

```python
# from ingest_south_africa.py: is_customer_feedback_candidate()
if strata:
    return True, "matched_strata"
# CATCH-ALL: any non-promotional tweet of sufficient length
if len(text) >= 30 and not promotional:
    return True, "non_promotional_sufficient_length"
```

In the 200-record sample:
- 80 records (40%) matched keyword strata
- 116 records (58%) were candidates only via the length ≥ 30 catch-all
- 1 record (0.5%) was excluded as promotional

The catch-all was intentional — it retains records that may be valid zero-aspect examples (annotators see them as containing no explicit aspect, training the extractor's negative class). However, it also includes many records with minimal banking relevance.

### 3.2 Proposed improved filter (for future resampling)

The root problem is that the corpus was collected specifically around SA bank accounts, so nearly every tweet is bank-adjacent by construction. A more informative signal would be:

```
SUITABLE = (banking_aspect_keyword AND (problem_expression OR ownership_expression OR request_expression))
           OR direct_service_complaint_pattern
           OR direct_praise_of_service_pattern
           OR churn/warning/suggestion_pattern (existing strata)
```

This would reduce the catch-all to a smaller set of records genuinely containing customer experience evidence, and produce a candidate rate of approximately 40–50% rather than 92.7%.

**However:** the current 200-record sample should not be discarded. Even if ~66 records are classified as unclear by automated audit, human annotators should confirm which of these are valid zero-aspect training examples before resampling.

---

## 4. Sample Diversity

### 4.1 Bank distribution

| Bank | Count | % |
|---|---|---|
| fnb | 60 | 30.0% |
| capitec | 46 | 23.0% |
| absa | 37 | 18.5% |
| standard_bank | 36 | 18.0% |
| nedbank | 21 | 10.5% |

FNB is at the cap (60) and Nedbank is the smallest group (21). The distribution broadly reflects corpus size differences between banks, with the bank cap preventing one bank from overwhelming the sample.

### 4.2 Year distribution (confirmed from prepared parquet)

| Year | Count | % |
|---|---|---|
| 2018 | 30 | 15.0% |
| 2019 | 38 | 19.0% |
| 2020 | 33 | 16.5% |
| 2021 | 48 | 24.0% |
| 2022 | 51 | 25.5% |

Recent years (2021–2022) are appropriately over-represented relative to earlier years, reflecting higher tweet volume and recency relevance.

### 4.3 Candidate strata representation (sampling indicators — not gold labels)

| Stratum | Count | % of 200 |
|---|---|---|
| transactions_candidate | 29 | 14.5% |
| digital_banking_candidate | 23 | 11.5% |
| fees_candidate | 20 | 10.0% |
| accounts_candidate | 19 | 9.5% |
| cards_candidate | 18 | 9.0% |
| branch_service_candidate | 16 | 8.0% |
| customer_support_candidate | 15 | 7.5% |
| fraud_security_candidate | 14 | 7.0% |
| suggestion_candidate | 12 | 6.0% |
| churn_candidate | 11 | 5.5% |
| warning_candidate | 10 | 5.0% |
| positive_feedback_candidate | 5 | 2.5% |

**Diversity finding:** All 12 candidate strata are represented. Previously under-represented areas (fees, fraud/security, suggestion, warning, churn) all have at least 10 records. Positive feedback is least represented (5 records), which is expected given that the source corpus is complaint-heavy.

### 4.4 Text length diversity

| Range | Count |
|---|---|
| < 30 chars | 3 |
| 30–50 chars | 23 |
| 50–100 chars | 69 |
| 100–200 chars | 66 |
| ≥ 200 chars | 39 |

Good spread across short, medium, and long texts. The 3 very short records may be unsuitable — they are already flagged in the relevance review.

---

## 5. Privacy Review

Full scan results documented in `outputs/south_africa_sample_privacy_review.json`.

**Summary:**
- Remaining emails: 0
- Remaining URLs: 0  
- Remaining raw @mentions: 0
- Remaining phone numbers: 0
- Remaining account numbers: 0
- Raw Username column: absent ✅
- Raw Tweet_Id: absent ✅

**Privacy verdict: PASS.** All personal identifiers have been successfully anonymised. Transaction amounts are preserved by approved design (`replace_amounts: false`).

---

## 6. Near-Duplicate Diversity

| Check | Result |
|---|---|
| Exact duplicate texts in sample | None (all 200 texts unique) |
| Duplicate record IDs | None |
| Records with near_dup_flag = True | 0 |
| Records with non-null near_dup_group_id | 0 |

**Clarification on the "165 near-dup groups" reported:**

The preparation pipeline reported 165 near-duplicate groups detected from a 10,000-record sample scan. This was a **diagnostic scan only**, applied to the first 10,000 records of the prioritised strata candidate pool. It was not used to control the 200-record annotation sample selection.

The sample selection was performed by bank-capped keyword-strata proportional sampling from the full candidate pool, without corpus-wide near-duplicate grouping. This is a documented limitation:

> **Limitation:** The 200-record annotation sample was drawn without full corpus-wide near-duplicate grouping. Near-duplicate control was implemented via exact text deduplication (473,995 exact duplicates removed corpus-wide) and the bank cap (max 60 per bank). However, semantically similar but not identical tweets (e.g. repeated complaint templates) may appear in the sample. Human annotators should note template-like texts and flag them during annotation.

The claim that "near-duplicate groups were used to control the annotation sample" would be inaccurate. All sample records have `near_dup_group_id = None`.

---

## 7. Readiness Gate Contradiction — Near-Dup Scope

The preparation report (`docs/south_africa_preparation_report.md`) states:

> "Near-dup groups in full dataset: 165"

This is misleading. The correct statement is:

> "Near-dup groups detected in a 10,000-record diagnostic sample of prioritised candidates: 165. Corpus-wide near-dup grouping was not performed due to memory constraints."

The annotation sample was drawn without near-dup-aware sampling. This is a known limitation that should be documented in the methodology section of any paper using this data.

---

## 8. Filter-Quality Assessment

### 8.1 The 92.7% candidate rate is a known and documented design decision

The catch-all rule (`length >= 30, not promotional → candidate`) was intentional. Its justification: the corpus was collected specifically around SA bank accounts, so most tweets are legitimately bank-related even without explicit feedback keywords. The catch-all retains potential zero-aspect training examples.

### 8.2 Impact on sample precision

The catch-all explains why 116 of 200 sample records (58%) have no keyword strata match. Among these, the quality audit classifies 66 as `unrelated_or_unclear` and 50 as suitable (banking content present without explicit strata keywords).

### 8.3 Proposed more precise filter (for future SA annotation rounds)

A more informative filter would combine:

**Tier 1 — Definite customer feedback:**
- banking_aspect_keyword + (complaint/problem expression OR request expression)
- direct service praise with banking context
- explicit churn/warning/suggestion language

**Tier 2 — Probable customer feedback:**
- banking_aspect_keyword + first-person ownership (`my card`, `my account`, `my transfer`)
- banking_aspect_keyword + [USER] token (reply in banking context)

**Tier 3 — Possible zero-aspect / general feedback:**
- banking_aspect_keyword alone (length ≥ 50, not promotional)

**Exclude:**
- promotional keywords dominant (existing rule)
- news/financial reporting patterns
- single-clause engagement responses

This would reduce the catch-all candidate rate from 92.7% to approximately 40–50%, producing a higher-precision candidate pool for future annotation rounds.

---

## 9. Licence and Provenance

The provenance documentation distinguishes correctly between:

| Item | Status |
|---|---|
| GitHub repository licence | MIT — applies to collection **software code** only |
| Kaggle dataset licence | **Requires independent confirmation before publication** |
| Twitter/X content redistribution | **Governed by Twitter/X Terms of Service — must be assessed separately** |
| Permission to analyse internally | Permitted (academic research use) |
| Permission to redistribute raw tweet text | **Unknown — must be confirmed before publication** |

**The audit confirms that the MIT software licence does not automatically permit redistribution of tweet content.** The preparation report correctly flags this. No publication or redistribution of raw tweet text should occur until the Kaggle dataset licence and Twitter/X content rights are confirmed.

---

## 10. Recommended Actions Before Human Annotation

### Action 1 (Required): Human review of the 66 unclear records

The 66 records classified as `unrelated_or_unclear` by the automated audit must be reviewed by a human before annotation begins. The reviewer should classify each as:
- **Valid zero-aspect training example** (include as-is with `not_started` status)
- **Unsuitable** (exclude from annotation — use `filter_out` status or set aside in a separate file)

The review queue is at `outputs/south_africa_sample_quality_review.jsonl` (200 entries, `include_for_annotation` field = False for 69 records).

If > 20 of the 66 are classified as unsuitable by human review, resample replacements from the prepared candidate pool before annotation begins.

### Action 2 (Recommended): Resolve the near-dup limitation note

Add an explicit note in the annotation guidelines for SA annotators that some records may contain similar complaint templates. Annotators should flag template-like or very similar records in the `notes` field.

### Action 3 (Required before publication): Confirm Kaggle licence

The research team must obtain confirmation of the Kaggle dataset licence and Twitter/X content redistribution rights before any publication that cites or reproduces content from this dataset.

### Action 4 (Optional): Improve filter for future annotation rounds

If a second South African annotation round is planned (e.g. 400+ records), implement the Tier 1/2/3 filter proposed in Section 8.3 to improve candidate precision.

---

## Final Recommendation

**3. IMPROVE FILTER AND RESAMPLE BEFORE ANNOTATION**

**Justification:**

| Dimension | Assessment |
|---|---|
| Schema validity | ✅ All 17 structural checks pass |
| Privacy | ✅ No personal identifiers remain |
| Gold label isolation | ✅ No gold or weak labels exposed |
| Annotation schema | ✅ Correct not_started / empty fields |
| Relevance precision | ⚠️ 65.5% automated suitability; 66 records require human review |
| Relevance threshold | ❌ 131/200 < 160/200 minimum |
| Near-dup control | ⚠️ Sample drawn without corpus-wide near-dup grouping |
| Bank diversity | ✅ All 5 banks; reasonable distribution |
| Year diversity | ✅ All 5 years represented |
| Strata diversity | ✅ All 12 strata represented |
| Licence | ⚠️ Kaggle dataset licence unconfirmed |

The sample fails the 160/200 relevance threshold on automated audit. However, the automated audit used conservative rules. If human review of the 66 unclear records reclassifies ≥ 29 as valid zero-aspect training examples, the threshold is met and annotation can proceed as recommendation 2 (SAMPLE READY WITH MINOR MANUAL EXCLUSIONS).

**The recommended path is:**

1. A human reviewer inspects the 66 `include_for_annotation=False` records in `outputs/south_africa_sample_quality_review.jsonl`.
2. If ≥ 29 are reclassified as valid → proceed with full 200-record annotation under recommendation 2.
3. If < 29 are reclassified as valid → resample replacements from the candidate pool and reassess.

**Do not begin full-scale human annotation until this human review step is complete.**

---

*This audit inspected only the 200-record sample and the specified report files. No models were trained. No gold labels were created. No research datasets were modified.*
