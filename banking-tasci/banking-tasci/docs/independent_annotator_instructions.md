# South African Banking Dataset — Independent Annotator Instructions

**Version:** Independent Annotation Round  
**Input file:** `data/annotations/south_african_independent_input.jsonl`  
**Output file:** `data/annotations/south_african_independent_annotator.jsonl`  
**Annotator ID to use:** `independent_annotator`

---

## Important: Files You Must NOT Access

Before beginning, confirm you have **not** viewed and will **not** view any of the following:

| File | Reason |
|---|---|
| `data/annotations/south_african_annotator_a.jsonl` | Contains a prior annotator's decisions |
| `data/annotations/south_african_annotator_b.jsonl` | Contains a prior annotator's decisions |
| `data/annotations/south_african_adjudicated.jsonl` | Contains prior adjudicated labels |
| `outputs/south_african_agreement_*.json` | Contains prior agreement scores |
| `outputs/south_african_disagreements_*.jsonl` | Contains prior disagreement details |
| `outputs/south_africa_sample_quality_review*.jsonl` | Contains candidate-strata hints |
| `outputs/south_africa_annotation_sample_report*.json` | Contains label distributions |
| `outputs/gold_label_distribution.json` | Contains label distributions |
| Any `docs/south_africa_annotation_pilot_review.md` | Contains prior review decisions |

**If you have seen any of these files, you must not proceed as the independent annotator. Please contact the research team.**

Your annotations must be based solely on reading the tweet text in the annotation interface.

---

## Launch Command

Run this command from the project root (`banking-tasci/`):

```bash
streamlit run scripts/annotation_app.py -- \
  --input data/annotations/south_african_independent_input.jsonl \
  --output data/annotations/south_african_independent_annotator.jsonl \
  --annotator-id independent_annotator
```

The app opens at `http://localhost:8501`. Use **--server.port 8503** if that port is already in use:

```bash
streamlit run scripts/annotation_app.py \
  --server.port 8503 -- \
  --input data/annotations/south_african_independent_input.jsonl \
  --output data/annotations/south_african_independent_annotator.jsonl \
  --annotator-id independent_annotator
```

Your annotations are saved automatically on each "Save" click. You can close and resume at any time — the app resumes from your output file.

---

## What You Are Annotating

You will annotate **196 South African banking-related tweets**, collected from Twitter mentions of FNB, ABSA, Nedbank, Capitec, and Standard Bank (2018–2022).

Each tweet has already been anonymised:
- `[USER]` replaces Twitter @mentions
- `[URL]` replaces web links
- `[PHONE]` replaces phone numbers
- `[EMAIL]` replaces email addresses
- `[ACCOUNT_OR_REFERENCE]` replaces account and reference numbers

Currency amounts are preserved (e.g. "R500") because they carry banking context.

---

## Annotation Task

For each tweet, you must:

### 1. Mark aspect spans
An **aspect span** is an explicit banking term or service mentioned in the tweet text. Use the start/end character offset fields to mark the exact substring.

- The invariant `text[start:end] == term` must hold exactly.
- Include descriptive modifiers that are part of the noun phrase (e.g. "mobile app", "monthly fee").
- Do not include surrounding words like articles ("the", "a") or sentiment adjectives ("terrible").
- A tweet may have zero, one, or several aspects.
- Aspects must not overlap.

**Allowed aspect categories:**

| Category | Covers |
|---|---|
| `customer_support` | Call centre, helpline, live chat, support agents, complaint handling |
| `digital_banking` | Mobile app, online banking, USSD, in-app features |
| `transactions` | Transfers, payments, deposits, withdrawals, ATM transactions |
| `cards` | Debit/credit card, PIN, card blocking/activation |
| `accounts` | Account opening/closing/freezing, savings/cheque accounts |
| `fees` | Monthly fees, charges, deductions, interest, penalties |
| `fraud_security` | Unauthorised transactions, scams, phishing, fraud investigations |
| `branch_service` | In-branch experience, teller, queue, branch hours |
| `general_service` | Overall service quality not covered by a more specific category |

### 2. Assign aspect-level sentiment
For each aspect span, assign one of:
- `negative` — the text expresses dissatisfaction, failure, or harm about this aspect
- `neutral` — the text describes the aspect factually without positive or negative evaluation
- `positive` — the text expresses praise or satisfaction about this aspect

Sentiment is per aspect, not per record. A single tweet can have both negative and positive aspects.

### 3. Assign the dominant customer intent
Choose the single most dominant intent expressed in the tweet:

| Intent | Description |
|---|---|
| `complaint` | Expresses dissatisfaction about a past banking experience |
| `compliment` | Expresses praise or satisfaction about a banking experience |
| `request_for_assistance` | Asks for help, resolution, or bank action |
| `suggestion` | Makes a constructive recommendation to improve a product or service |
| `warning` | Alerts other customers about a risk or advises avoiding the bank |
| `churn_signal` | Explicitly expresses intent to leave the bank or close an account |
| `general_feedback` | General opinion or comment that does not fit any of the above |

If you are genuinely uncertain between two intents, use the **Intent is ambiguous** checkbox and select an alternative intent.

### 4. Marking a record as completed
Tick **Mark as completed** and click **Save** only when you are confident in all your decisions for that record.

Leave a record as `in_progress` if you are still unsure. Do not mark it completed without selecting an intent.

---

## Tweets That May Not Contain Banking Feedback

Some tweets in the dataset may turn out to contain:
- general commentary unrelated to banking
- sports, politics, or entertainment content that mentions a bank's name in passing
- promotional content
- non-banking uses of words like "bank" or "account"

For these records:
- Leave `aspects` empty (no aspect spans)
- Select `general_feedback` as the intent if the tweet is vaguely bank-related
- Use your `notes` field to explain if you believe the record should be excluded as unrelated content

Do not skip or delete records. Mark every record as completed with your best judgement.

---

## Offset Selection Tips

When marking an aspect span in the interface:
- Use the **Start** and **End** number inputs
- The **Preview** line shows you exactly which substring will be captured: `text[start:end] = "..."`
- Verify the preview matches the term you intend before clicking **Add aspect**
- Punctuation immediately next to a term should not be included (e.g. tag `app` not `app,`)

---

## Agreement Checkpoint

After completing your first 50 records, please notify the research team. An independent inter-annotator agreement check will be run at that point. You may continue annotating while waiting for feedback.

---

## Reference

For detailed guidelines including boundary rules, overlap tie-breakers, and label-selection examples, refer to:

```
docs/annotation_guidelines.md
```

This document covers all nine aspect categories, seven intent labels, three sentiment labels, and difficult disambiguation cases.

---

*This file was prepared for independent annotation. The research team will compute genuine Cohen's Kappa between your annotations and a prior annotator's file only after you complete annotation independently.*
