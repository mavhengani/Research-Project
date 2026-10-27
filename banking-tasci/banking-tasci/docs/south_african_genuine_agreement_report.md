# South African Genuine Inter-Annotator Agreement Report

**Generated:** 2026-09-06  
**Status:** AWAITING MANUAL ADJUDICATION — do not train models on this data

---

## 1. Overview

This report presents the genuine inter-annotator agreement between **Annotator A** and
an **independent annotator** who annotated the South African banking-tweet sample
entirely without reference to Annotator A's labels. No automatic adjudication has been
performed. No annotator's labels have been preferred by default. Version 1 files are
unchanged.

| Item | Value |
|---|---|
| Annotator A file | `data/annotations/south_african_annotator_a_comparison.jsonl` |
| Independent annotator file | `data/annotations/south_african_independent_annotator.jsonl` |
| Agreement output | `outputs/south_african_genuine_agreement.json` |
| Disagreements queue | `outputs/south_african_genuine_disagreements.jsonl` |
| Kappa backend | scikit-learn (`cohen_kappa_score`) |

---

## 2. Validation Summary

Before agreement was calculated, the independent annotator file was validated:

- **Records parsed:** 196 / 196
- **Records with `annotation_status = completed`:** 196 / 196
- **Duplicate `record_id` values:** 0
- **Structural errors (missing required fields, invalid sentiments):** 0
- **Result:** ✅ Validation passed

The Annotator A comparison file was also confirmed to contain exactly the same 196
`record_id` values — no IDs are present in one file but absent from the other.

---

## 3. Agreement Metrics

### 3.1 Jointly Annotated Records

| Metric | Value |
|---|---|
| **Jointly annotated records** | **196** |

Both files share all 196 record IDs, so every record contributes to every metric.

### 3.2 Cohen's Kappa

| Label dimension | Cohen's κ | Interpretation |
|---|---|---|
| **Intent** | **0.8736** | Strong agreement |
| **Aspect category** | **0.9904** | Near-perfect agreement |
| **Aspect sentiment** | **0.8750** | Strong agreement |

> Kappa interpretation scale (Landis & Koch, 1977): < 0 = poor; 0.01–0.20 = slight;
> 0.21–0.40 = fair; 0.41–0.60 = moderate; 0.61–0.80 = substantial; > 0.80 = almost perfect.

All three kappa values fall in the **almost perfect** band (κ > 0.80), with aspect-category
agreement especially high. Intent and sentiment show more variation, which is expected for
subjective short-text annotation.

### 3.3 Exact-Span Agreement

| Metric | Value |
|---|---|
| **Exact-span agreement** | **0.8010** (80.1 %) |

Exact-span agreement requires both annotators to have identified an identical set of
`(start, end)` character-offset tuples for the same record. 157 of 196 records have
perfectly matching span sets; 39 records have at least one boundary difference.

### 3.4 Token-Level Aspect Agreement

Token-level metrics treat Annotator A's spans (expanded to whitespace-token indices) as
the reference and the independent annotator's spans as the hypothesis.

| Metric | Value |
|---|---|
| **Token-level precision** | **0.9509** (95.1 %) |
| **Token-level recall** | **0.8482** (84.8 %) |
| **Token-level F1** | **0.8966** (89.7 %) |

High precision (95.1 %) indicates that when the independent annotator identified an aspect
token, it almost always coincided with a token Annotator A had also marked. Lower recall
(84.8 %) indicates the independent annotator missed approximately 15 % of the aspect
tokens that Annotator A had marked — most likely cases where Annotator A annotated an
aspect that the independent annotator did not identify at all.

---

## 4. Disagreement Summary

### 4.1 Counts

| Metric | Count |
|---|---|
| **Total records with at least one disagreement** | **48** |
| **Intent disagreements** | **20** |
| **Aspect-boundary (span) disagreements** | **39** |
| **Sentiment disagreements** | **24** |
| **Category disagreements** | **3** |
| **Records where only one annotator identified an aspect** | **4** |

48 of 196 records (24.5 %) contain at least one disagreement across any dimension.
The remaining 148 records (75.5 %) are in complete agreement and require no adjudication.

### 4.2 Disagreement Type Observations

- **Span disagreements (39)** are the most frequent single type. Many span disagreements
  co-occur with sentiment disagreements because a different span boundary changes which
  tokens are considered the aspect term.
- **Intent disagreements (20)** are concentrated around ambiguous tweet types — tweets
  that could be read as both a `complaint` and a `churn_signal`, or as both a `query` and
  a `general_feedback`.
- **Sentiment disagreements (24)** frequently arise on neutral-vs-negative boundary cases
  and on sarcastic or ambiguous phrasing common in South African social media.
- **Category disagreements (3)** are rare, consistent with the near-perfect category kappa
  (κ = 0.990). These three cases likely involve `general_service` vs a more specific
  category.
- **One-sided aspect detection (4)** — four records where one annotator found no aspects
  at all while the other identified at least one span. These are the hardest cases for
  adjudication and may require a third opinion.

### 4.3 Records with the Most Disagreements

| Record ID | Disagreement count | Types |
|---|---|---|
| `41967cdad0f3f982` | 4 | intent, span, sentiment × 2 |
| `7219638649a4c436` | 4 | intent, span, sentiment × 2 |
| `a7d59cc8db5727e0` | 4 | intent, span, sentiment × 2 |
| `bdd1289abf7f5df3` | 4 | intent, span, category, sentiment |
| `06ab7c45a63db522` | 3 | intent, span, sentiment |
| `1c23631757a66965` | 3 | span, sentiment × 2 |
| `2a8a332ea3a2f075` | 3 | sentiment × 3 |
| `5ea75b9b45c04a1a` | 3 | span, category, sentiment |
| `803c5e94b9975af9` | 3 | span, sentiment × 2 |
| `b6bac249d3ce189b` | 3 | intent, sentiment × 2 |

Full per-record details — including both annotators' values for every disagreement — are
in `outputs/south_african_genuine_disagreements.jsonl`.

---

## 5. Adjudication Queue

The 48 disagreement records are queued for **manual adjudication** in
`outputs/south_african_genuine_disagreements.jsonl`. Each entry contains:

- `record_id`
- `disagreement_count`
- `disagreements` — a list of objects with `type`, `annotator_a`, and `annotator_b` values

**Adjudication rules (must be followed):**

1. Neither Annotator A nor the independent annotator is preferred by default.
2. The adjudicator must examine the original text and guidelines
   (`docs/annotation_guidelines.md`) for every disagreement independently.
3. No automated resolution is permitted.
4. The agreed label for each disagreement must be recorded in a separate adjudicated file.
5. Do not modify `south_african_annotator_a_comparison.jsonl` or
   `south_african_independent_annotator.jsonl` (Version 1 files).

---

## 6. Next Steps

- [ ] Manual adjudicator reviews all 48 records in
      `outputs/south_african_genuine_disagreements.jsonl`
- [ ] Adjudicated labels are written to a new file (e.g.
      `data/annotations/south_african_genuine_adjudicated.jsonl`)
- [ ] Adjudication approval is confirmed before any model training proceeds
- [ ] This report is updated with final adjudicated record counts if needed

---

## 7. Files

| File | Description |
|---|---|
| `data/annotations/south_african_independent_annotator.jsonl` | Validated independent annotation (196 records) |
| `data/annotations/south_african_annotator_a_comparison.jsonl` | Annotator A labels for the same 196 records (unchanged) |
| `outputs/south_african_genuine_agreement.json` | Full JSON agreement metrics |
| `outputs/south_african_genuine_disagreements.jsonl` | Per-record disagreement queue (48 records) |
| `docs/south_african_genuine_agreement_report.md` | This report |
