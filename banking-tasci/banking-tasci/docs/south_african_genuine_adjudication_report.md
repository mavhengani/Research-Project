# South African Genuine Adjudication Report

**Generated:** 2026-09-06  
**Adjudicator ID:** south_african_adjudicator  
**Status:** COMPLETE — awaiting split-creation and baseline-training approval

---

## 1. Original Record Count and Agreement Scores

| Metric | Value |
|---|---|
| Total records independently annotated | 196 |
| Records with full agreement | 148 (75.5 %) |
| Records with at least one disagreement | 48 (24.5 %) |
| Intent Cohen's κ (pre-adjudication) | 0.8736 |
| Aspect-category Cohen's κ (pre-adjudication) | 0.9904 |
| Aspect-sentiment Cohen's κ (pre-adjudication) | 0.8750 |
| Exact-span agreement (pre-adjudication) | 80.1 % |
| Token-level aspect F1 (pre-adjudication) | 89.7 % |

The pre-adjudication independent agreement scores are the meaningful reliability measurement. No post-adjudication kappa is reported.

---

## 2. Disagreement Counts

| Type | Count |
|---|---|
| Intent disagreements | 20 |
| Aspect-span (boundary) disagreements | 39 |
| Sentiment disagreements | 24 |
| Category disagreements | 3 |
| Records where only one annotator identified an aspect | 4 |

---

## 3. Records Manually Adjudicated

All 48 disagreement records were reviewed and resolved. No record was left unresolved. No automatic resolution was applied.

| Outcome | Count |
|---|---|
| **Total records adjudicated** | **48** |
| Decision source: new corrected annotation | 28 |
| Decision source: Annotator A selected | 14 |
| Decision source: independent annotator selected | 6 |
| Records excluded | 0 |

---

## 4. Label Changes Made During Adjudication

Changes are reported relative to Annotator A's labels (used as baseline for comparison only — neither annotator was preferred).

| Change type | Count |
|---|---|
| Intent changes | 6 |
| Span (boundary) changes | 28 |
| Sentiment changes | 4 |
| Category changes | 1 |
| Records with intent_ambiguous=true | 4 |

### 4.1 Intent Changes (6 records)

| Record ID | Annotator A | Independent | Final | Reason summary |
|---|---|---|---|---|
| `a7d59cc8db5727e0` | churn_signal | general_feedback | general_feedback | Conditional/speculative leaving, not explicit |
| `bdd1289abf7f5df3` | general_feedback | general_feedback | complaint | Strong anger about unauthorised debiting |
| `06ab7c45a63db522` | suggestion | complaint | complaint | Primary purpose is frustration, not recommendation |
| `b6bac249d3ce189b` | compliment | complaint | general_feedback | Mixed praise and outage report, neither dominant |
| `a8a733e1f5b71988` | request_for_assistance | suggestion | complaint | Venting frustration, no specific action requested |
| `acad691f8b6c7307` | general_feedback | complaint | general_feedback | News share, not personal dissatisfaction |

### 4.2 Ambiguity Decisions (4 records)

| Record ID | Final intent | Alternative intent | Reason summary |
|---|---|---|---|
| `a7d59cc8db5727e0` | general_feedback | churn_signal | Conditional leaving language |
| `06ab7c45a63db522` | complaint | suggestion | Implicit feature improvement implied |
| `b6bac249d3ce189b` | general_feedback | complaint | Mixed praise/outage |
| `04426278cadde9e4` | complaint | suggestion | Implicit feature request embedded in complaint |

### 4.3 Category Change (1 record)

| Record ID | Span | From | To | Reason |
|---|---|---|---|---|
| `533ceacdac5ce6a4` | cardless banking [20:36] | cards | digital_banking | Cardless banking is a digital/mobile payment feature, not a card product |

### 4.4 Sentiment Changes (4 records)

| Record ID | Span | Annotator A | Independent | Final | Reason |
|---|---|---|---|---|---|
| `a7d59cc8db5727e0` | service [88:95] | positive | neutral | positive | Explicitly praised: "happy with the service" |
| `a7d59cc8db5727e0` | charges [104:111] | negative | neutral | negative | Explicitly criticised: charges don't meet service |
| `43d10bc7727ba230` | best bank [39:48] | negative | positive | negative | Sarcastic use: "maybe the best useless bank" |
| `eea4d3ef886bde64` | customer support [91:107] | negative | neutral | negative | "don't think they know a word of customer support" |

### 4.5 One-sided Aspect Detection Decisions (4 records)

| Record ID | A aspects | B aspects | Final decision | Reason |
|---|---|---|---|---|
| `222e418e7f978e53` | unresolved, complaints | (none) | unresolved + complaints retained | Explicit banking-service failure references present |
| `c67eb603e8ac95ff` | employees | (none) | excluded both | 'employees' is staff reference, not a banking product/service |
| `ce492ec3aa908fd2` | long span [31:76] | (none) | banks accounts [62:76] | Minimal banking term extracted from A's overly long span |
| `a84648a32fc46812` | record of all communication | service [222:229] | excluded both | Neither is a banking product/service aspect |

---

## 5. Span Boundary Changes Summary

Of the 39 span-boundary disagreements, the adjudicator applied the following consistent principles:

- **Location prefixes removed** (e.g. "carlswald midrand branch" → "branch"; "FNB atm" → "atm"): these prefixes identify context, not the banking product.
- **Action verbs excluded** (e.g. "collect a card" → "card"; "reversing a debit order" → "debit order"; "closing my account" → adjudicator retained full phrase as it is the specific service state being evaluated).
- **Compound product names kept intact** (e.g. "mobile banking app" kept as single span over split "mobile banking" + "app"; "call centre agent" kept over split).
- **Co-referential duplicates removed** (e.g. "card" [68:72] excluded when "card service" [15:27] already captured the same concept).
- **Generic redundant terms excluded** (e.g. final "service" when a specific service already annotated in the same record).

---

## 6. Final Label Distributions

Source: `outputs/south_african_genuine_gold_validation.json`

### 6.1 Intent

| Intent | Count |
|---|---|
| complaint | 52 |
| request_for_assistance | 46 |
| general_feedback | 43 |
| compliment | 20 |
| churn_signal | 19 |
| warning | 9 |
| suggestion | 7 |
| **Total records** | **196** |

### 6.2 Aspect Category

| Category | Aspect count |
|---|---|
| transactions | 79 |
| accounts | 71 |
| customer_support | 60 |
| digital_banking | 47 |
| cards | 44 |
| branch_service | 35 |
| general_service | 30 |
| fraud_security | 28 |
| fees | 20 |
| **Total aspects** | **414** |

### 6.3 Aspect Sentiment

| Sentiment | Count |
|---|---|
| neutral | 205 |
| negative | 181 |
| positive | 28 |

### 6.4 Other counts

| Metric | Count |
|---|---|
| Records with zero aspects | 32 |
| Records with intent_ambiguous=true | 4 |
| Total aspect spans | 414 |

---

## 7. Validation Result

```
python scripts/validate_annotations.py \
  --input data/annotations/south_african_genuine_adjudicated.jsonl \
  --require-complete \
  --output outputs/south_african_genuine_gold_validation.json
```

| Check | Result |
|---|---|
| Total records | 196 |
| Valid records | **196** |
| Invalid records | **0** |
| Incomplete records | 0 |
| Errors by type | (none) |

Validation passed with zero errors.

---

## 8. Output Files

| File | Description |
|---|---|
| `data/annotations/south_african_genuine_adjudication_decisions.jsonl` | 48 incremental adjudication decisions (source of truth) |
| `data/annotations/south_african_genuine_adjudicated.jsonl` | 196-record manually adjudicated gold set |
| `data/annotations/south_african_adjudicated_v2.jsonl` | Gold Version 2 (adjudicated + provenance metadata) |
| `outputs/south_african_genuine_gold_validation.json` | Validation report |
| `outputs/south_african_genuine_agreement.json` | Pre-adjudication agreement metrics |
| `outputs/south_african_genuine_disagreements.jsonl` | 48-record disagreement queue (input) |
| `data/annotations/south_african_adjudicated.jsonl` | **Version 1 — unchanged** |
| `scripts/adjudicate_annotations.py` | Extended with --decision-file and --resume flags |

### Gold Version 2 Provenance Fields

Every record in `south_african_adjudicated_v2.jsonl` carries:

```json
{
  "gold_version": 2,
  "independently_reviewed": true,
  "agreement_report_path": "outputs/south_african_genuine_agreement.json",
  "adjudication_status": "complete",
  "adjudicated_records": 48,
  "total_records": 196,
  "excluded_records": 0
}
```

These fields must never be used as model features.

---

## 9. Remaining Limitations

- **Sarcasm and irony:** Several South African tweets use sarcasm (e.g. "best useless bank"). Sentiment adjudication relied on textual cues but some borderline cases may still be ambiguous to future readers.
- **Aspect granularity:** The guideline to use the minimal complete phrase required judgment calls. Future annotators should be given explicit examples of location-prefix removal and action-verb exclusion.
- **Zero-aspect records (32):** These records contain no extractable banking product/service term. This includes news shares, general statements, and campaign hashtag posts. The zero-aspect rate (16.3 %) is expected for social media.
- **Single adjudicator:** All 48 decisions were made by one adjudicator. A second independent adjudication review of the 28 new-corrected-annotation decisions would further strengthen quality.
- **Version 1 differences:** The genuine adjudication (Version 2) used an independent annotator rather than Annotator B. Label distributions will differ from Version 1. Do not merge the two versions without explicit provenance tracking.

---

## 10. Next Steps Awaiting Approval

- [ ] Human review of `south_african_genuine_adjudicated.jsonl`
- [ ] Human review of `south_african_genuine_gold_validation.json`
- [ ] Human review of this report
- [ ] Approval to proceed to split creation
- [ ] Approval to begin baseline training
