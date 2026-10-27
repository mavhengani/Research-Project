# Annotation Pilot Review — Discussion Template

Use this template after calculating inter-annotator agreement on the first 50
shared records (or any agreed checkpoint). Fill in each section during the
review meeting between the two annotators and the lead adjudicator.

Do not modify the annotation taxonomy without team agreement. Record decisions
here before updating `docs/annotation_guidelines.md`.

---

## Metadata

| Field | Value |
|---|---|
| Review date | |
| Annotators present | |
| Records reviewed | (e.g. first 50 records) |
| Agreement script output | `outputs/inter_annotator_agreement_50.json` |
| Disagreements file | `outputs/annotation_disagreements_50.jsonl` |

---

## 1. Confusing Aspect Boundaries

Document cases where annotators disagreed on where an aspect term starts or ends.

**Examples observed:**

| Record ID | Annotator A span | Annotator B span | Agreed decision |
|---|---|---|---|
| | | | |

**Guideline update needed?**  
☐ No — existing rules are sufficient  
☐ Yes — add to `docs/annotation_guidelines.md` (describe below)

Decision:

---

## 2. Aspect Category Disagreements

Document cases where annotators agreed on the span but disagreed on the category.

**Most common disagreement pairs:**

| Category A called | Category B called | Example text | Agreed category | Rationale |
|---|---|---|---|---|
| `customer_support` | `general_service` | | | |
| `digital_banking` | `transactions` | | | |
| | | | | |

**Guideline update needed?**  
☐ No  
☐ Yes — add disambiguation examples to guidelines

Decision:

---

## 3. Aspect Sentiment Disagreements

Document cases where the same aspect span received different sentiment labels.

**Examples observed:**

| Record ID | Aspect term | Annotator A sentiment | Annotator B sentiment | Context that caused disagreement | Agreed sentiment |
|---|---|---|---|---|---|
| | | | | | |

**Notes on edge cases:**

- Negated phrases (e.g. "not bad"):
- Comparisons (e.g. "faster than before"):
- Conditional phrases (e.g. "would be better if"):

**Guideline update needed?**  
☐ No  
☐ Yes — add clarifying examples

Decision:

---

## 4. Complaint vs. Request for Assistance

This is typically the most common intent disagreement. Document cases here.

**Agreed distinction:**

> A **complaint** expresses dissatisfaction with an experience that has already
> occurred. A **request_for_assistance** asks for help or action from the bank.
> When both are present, the dominant one is the overall tone of the message.

**Examples of ambiguous records:**

| Record ID | Text excerpt | Annotator A | Annotator B | Agreed decision |
|---|---|---|---|---|
| | | complaint | request_for_assistance | |

**Updated rule (if agreed):**

---

## 5. Complaint vs. Churn Signal

Document cases where the intent was a strong complaint versus a signal the
customer intends to leave or close their account.

**Agreed distinction:**

> A **churn_signal** must contain a direct expression of intent to leave,
> close accounts, or switch banks — not just frustration. Frustration alone
> is a **complaint**.

**Examples observed:**

| Record ID | Key phrase | Agreed label | Reason |
|---|---|---|---|
| | | | |

**Updated rule (if agreed):**

---

## 6. Warning vs. Complaint

Document cases where annotators disagreed between a warning (alerting others
about a risk) and a complaint (personal dissatisfaction).

**Agreed distinction:**

> A **warning** addresses a potential risk to other customers or is intended as
> a public caution (e.g. "beware of this fee", "avoid this bank if you..."). A
> **complaint** is primarily about the annotator's own experience.

**Examples observed:**

| Record ID | Key phrase | Agreed label | Reason |
|---|---|---|---|
| | | | |

**Updated rule (if agreed):**

---

## 7. Context Interpretation Issues

Document cases where the presence or absence of `previous_text` changed how the
record was interpreted.

**Examples:**

| Record ID | context_available | How context changed interpretation | Decision |
|---|---|---|---|
| | True | | |
| | False | | |

**Guideline update needed?**  
☐ No  
☐ Yes — clarify context handling rules

Decision:

---

## 8. Decisions Added to Annotation Guidelines

List every concrete rule or example agreed during this review that should be
added to `docs/annotation_guidelines.md` before annotation continues.

| # | Section | New rule or example |
|---|---|---|
| 1 | | |
| 2 | | |
| 3 | | |

**Action:** One team member updates `docs/annotation_guidelines.md` before
annotation of the remaining records begins.

---

## 9. Agreement Metrics Summary

Copy the key metrics from `outputs/inter_annotator_agreement_50.json` here
for the record.

| Metric | Value | Interpretation |
|---|---|---|
| Joint records | | |
| Intent Kappa | | < 0.6 = review required |
| Category Kappa | | < 0.6 = review required |
| Sentiment Kappa | | < 0.6 = review required |
| Exact span agreement | | |
| Token-level F1 | | |

**Decision to continue:**  
☐ Agreement is sufficient — continue with the remaining 550 records  
☐ Agreement is insufficient — refine guidelines and re-annotate the 50-record sample before continuing

---

## 10. Sign-off

| Role | Name | Date |
|---|---|---|
| Annotator A | | |
| Annotator B | | |
| Lead adjudicator | | |
