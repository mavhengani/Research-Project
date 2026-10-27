# South African Annotation — Pilot Agreement Review

**Use this document after both annotators complete the first 50 records and the
`south_african_agreement_50.json` report is available.**

Both annotators must have produced their files independently. The
`calculate_agreement.py --completed-only` command must have been run on
both files before this review takes place.

---

## 1. Metadata

| Field | Value |
|---|---|
| Review date | 2026-09-05 |
| Annotator A ID | `south_african_annotator_a` |
| Annotator B ID | `south_african_annotator_b` |
| Records reviewed (checkpoint) | First 50 of 196 |
| Agreement report | `outputs/south_african_agreement_50.json` |
| Disagreements file | `outputs/south_african_disagreements_50.jsonl` |

---

## 2. Agreement Scores (fill in from `south_african_agreement_50.json`)

| Metric | Value | Interpretation |
|---|---|---|
| Jointly completed records | 50 | Both files contain the same 50 completed records |
| Intent Cohen's κ | 1.00 | Above the 0.60 review threshold |
| Aspect category Cohen's κ | 1.00 | Above the 0.60 review threshold |
| Aspect sentiment Cohen's κ | 1.00 | Above the 0.60 review threshold |
| Exact span agreement | 1.00 | All evaluated spans matched |
| Token-level F1 | 1.00 | Precision 1.00, recall 1.00, F1 1.00 |
| Total disagreements | 0 | Disagreement JSONL is empty |

**Validation:** Annotator A and Annotator B each have 50 valid completed
records and 0 invalid records. The two files are identical apart from
`annotator_id`, so these scores confirm pipeline consistency but do not
establish independent human reliability.

---

## 3. Aspect Boundary Disagreements

Record cases where annotators agreed on the category but disagreed on
the exact character offsets.

| Record ID | Annotator A term | Annotator B term | Context | Agreed rule |
|---|---|---|---|---|
| | | | | |

**Guideline clarification needed?**
☐ No — existing boundary rules are sufficient
☐ Yes — add example to `docs/annotation_guidelines.md`

Decision:

No aspect-boundary disagreements were reported.

---

## 4. Fees vs. Transactions

Examples where one annotator used `fees` and the other used `transactions`
for the same span.

Agreed rule: A **fee** is a recurring or standing charge levied by the
bank (monthly fee, service fee, ATM fee). A **transaction** is a specific
movement of money initiated by the customer (transfer, payment, deposit,
withdrawal). The amount deducted as a service fee is `fees`; the payment
itself is `transactions`.

| Record ID | Span | A category | B category | Agreed category | Reason |
|---|---|---|---|---|---|
| | | | | | |

---

## 5. Fraud/Security vs. Accounts or Cards

Agreed rule (from `docs/annotation_guidelines.md`): Tag `fraud_security`
when the text explicitly uses fraud, unauthorised, scam, or security
framing. Tag `cards` when the physical card state is the primary issue
without fraud framing. Tag `accounts` for account-level access issues
without fraud framing.

| Record ID | Span | A category | B category | Agreed category | Reason |
|---|---|---|---|---|---|
| | | | | | |

---

## 6. Branch Service vs. Customer Support

Agreed rule: `branch_service` when interaction is physically at a branch
(teller, branch manager, in-branch queue). `customer_support` when
interaction is over phone, chat, email, or app support — no branch visit.

| Record ID | Span | A category | B category | Agreed category | Reason |
|---|---|---|---|---|---|
| | | | | | |

---

## 7. Complaint vs. Request for Assistance

Agreed rule: When both dissatisfaction and a request are present, select the
intent representing the main communicative purpose. Use
`request_for_assistance` when the customer explicitly asks the bank to take
action. Use `complaint` when the main purpose is to report dissatisfaction and
no clear action is requested.

Examples:

- "Your service is terrible." -> `complaint`
- "Your service is terrible. Please unblock my account." ->
  `request_for_assistance`, with alternative intent `complaint` and
  `intent_ambiguous: true` when both are genuinely plausible.

| Record ID | A intent | B intent | Agreed intent | Key phrase |
|---|---|---|---|---|
| | | | | |

---

## 8. Complaint vs. Warning

Agreed rule: `complaint` = personal negative experience with the bank.
`warning` = directing other customers or the public to be careful, with
an explicit advisory tone ("do not use", "beware", "avoid"). A complaint
about a fraud or poor security practice is still `complaint` unless it
explicitly warns others.

| Record ID | A intent | B intent | Agreed intent | Key phrase |
|---|---|---|---|---|
| | | | | |

---

## 9. Complaint vs. Churn Signal

Agreed rule: `churn_signal` must contain an explicit expression of
intent to leave or close accounts — not just frustration. Frustration
alone is `complaint`. "I am switching banks" = churn. "Terrible service"
= complaint.

| Record ID | A intent | B intent | Agreed intent | Key phrase |
|---|---|---|---|---|
| | | | | |

---

## 10. General Feedback vs. Suggestion

Agreed rule: `suggestion` requires a constructive recommendation to
improve a specific service or feature ("please add", "should improve",
"consider"). A vague positive or neutral opinion about the bank is
`general_feedback`.

| Record ID | A intent | B intent | Agreed intent | Key phrase |
|---|---|---|---|---|
| | | | | |

---

## 11. Neutral vs. Negative Sentiment

Agreed rule: Use `negative` when the text expresses clear dissatisfaction,
failure, or harm. Use `neutral` when the text describes a banking feature
or transaction factually without positive or negative evaluation. Use
`positive` when there is explicit praise or satisfaction.

Edge case: "My card was blocked" — the blocking itself is not inherently
negative unless the context indicates it was unwanted or incorrect.

| Record ID | Aspect term | A sentiment | B sentiment | Agreed sentiment | Reason |
|---|---|---|---|---|---|
| | | | | | |

---

## 12. Records with No Explicit Aspect (Zero-Aspect Decision)

Records where one or both annotators left the aspect list empty.

Agreed rule: Leave aspects empty when no explicit banking feature, product,
service, event, or problem can be extracted as a character span. Annotate
"bank", "banking service", or the bank's name as `general_service` only when
the phrase is the explicit target of an opinion. Do not annotate a bank
mention used only to address or identify the institution.

Examples:

- "FNB, please help me." -> do not annotate `FNB`; it is only the addressee.
- "This bank provides terrible service." -> annotate `bank` as
  `general_service` with negative sentiment.
- "Capitec announced a new partnership." -> aspects may remain empty;
  intent is `general_feedback`.

| Record ID | A annotation | B annotation | Agreed decision | Reason |
|---|---|---|---|---|
| | | | | |

No zero-aspect disagreements were reported.

---

## 13. SA-Specific Language Notes

Record cases involving South African languages (Afrikaans, Zulu, Sotho,
Tswana) where the annotation guidelines did not provide sufficient
guidance.

| Record ID | Language | Issue | Agreed decision |
|---|---|---|---|
| | | | |

No record-specific disagreements were reported in Sections 3 to 13 because
`outputs/south_african_disagreements_50.jsonl` is empty.

---

## 14. Decisions Added to Annotation Guidelines

The disagreement export is empty, so Sections 3 to 13 contain no
record-specific disagreement cases. The absence of disagreements is subject
to the independence limitation recorded in Section 2.

| # | Section | New rule or clarification |
|---|---|---|
| 1 | Intent | When dissatisfaction and a request co-occur, use `request_for_assistance` for an explicit action request; use `complaint` when no clear action is requested. |
| 2 | General service / zero-aspect | Annotate a bank name or "bank" as `general_service` only when it is the explicit target of an opinion, not when it is merely an addressee or identifier. |

**Action:** Add agreed clarifications to `docs/annotation_guidelines.md`
before annotation of the remaining 146 records resumes.

---

## 15. Decision to Continue

☐ Agreement is sufficient — continue with the remaining 146 records  
☒ Independence requirement not met — repeat the 50-record pilot with genuinely independent annotation before continuing

Although all measured agreement scores are 1.00 and both files validate
cleanly, the current A/B files are identical apart from `annotator_id`.
Therefore the result cannot be accepted as genuine independent agreement.

| Role | Signature | Date |
|---|---|---|
| Annotator A | | |
| Annotator B | | |
| Research lead | | |
