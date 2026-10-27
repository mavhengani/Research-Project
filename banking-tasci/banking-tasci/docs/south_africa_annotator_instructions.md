# South African Annotation Instructions

## Purpose

You are independently annotating the South African banking dataset for the Banking TASCI research project. Your annotations will be compared with another annotator's work to measure agreement and create a reliable gold dataset.

Start with the **same first 50 records** as the other annotator. Work independently: do not open, copy, compare, or discuss the other annotator's annotation file before the agreement review.

## Open the Annotation Interface

Use the Streamlit page assigned to you:

- Annotator A: `http://localhost:8501/`
- Annotator B: `http://localhost:8502/`

The input dataset is:

```text
data/annotations/south_african_annotation_input.jsonl
```

Your output file is assigned by the project setup. Do not change it and do not write to the other annotator's file.

## Work Through the First 50 Records

Annotate records in order, starting with record 1. Complete the same first 50 records as the other annotator.

For every record:

1. Read the complete text carefully.
2. Identify every explicit banking aspect mentioned.
3. Select the exact text span for each aspect.
4. Assign one category to each aspect.
5. Assign one sentiment to each aspect.
6. Assign the dominant intent of the whole record.
7. Mark the record as completed and save it before moving on.

Do not guess what the writer might mean beyond the text. Annotate what is explicitly stated.

## Exact Aspect Spans

Select the smallest complete phrase that names the banking feature, product, service, event, or problem.

The required offset rule is:

```text
text[start:end] == term
```

The start offset is inclusive. The end offset is exclusive. Do not include surrounding spaces or punctuation unless they are part of the aspect term.

Example:

```text
Text: "The mobile app is slow."
Term: "mobile app"
```

The selected span must match the text exactly, including capitalization and spelling.

If the text contains two different aspects, annotate both separately. For example, in:

```text
"The mobile app is slow, but customer support was helpful."
```

annotate `mobile app` and `customer support` as two separate aspects.

## Allowed Aspect Categories

Use only one of these categories for each aspect:

- `customer_support`: phone, chat, email, call centre, help desk, or support staff
- `digital_banking`: mobile app, online banking, website, login technology, or digital feature
- `transactions`: transfers, payments, deposits, withdrawals, or specific money movements
- `cards`: debit cards, credit cards, ATM cards, card delivery, blocked cards, or card use
- `accounts`: account opening, closing, balance, access, account fees, or account administration
- `fees`: bank charges, service fees, monthly fees, ATM fees, or transaction charges
- `fraud_security`: fraud, scams, unauthorised activity, stolen details, or security concerns
- `branch_service`: teller, branch staff, branch manager, queues, or an in-person branch visit
- `general_service`: a bank service or banking experience that does not fit a more specific category

### Common category decisions

- Use `fees` for the charge itself. Use `transactions` for the payment, transfer, deposit, or withdrawal.
- Use `fraud_security` when the text explicitly refers to fraud, a scam, unauthorised activity, or security.
- Use `cards` when the issue is about a card without fraud or security framing.
- Use `accounts` for account-level access or administration without fraud framing.
- Use `branch_service` for an in-person branch interaction.
- Use `customer_support` for phone, chat, email, or app support.

## Allowed Sentiments

Use only:

- `negative`: clear dissatisfaction, failure, loss, harm, or frustration
- `neutral`: factual description without clear praise or criticism
- `positive`: praise, satisfaction, or appreciation

Assign sentiment to each aspect separately. A record may contain positive and negative aspects at the same time.

Do not automatically mark an event as negative. For example, `card was blocked` is neutral if the text only states the fact; it is negative if the writer says the block was unwanted, incorrect, or harmful.

## Allowed Intents

Choose the single dominant intent of the whole record:

- `complaint`: negative experience or dissatisfaction without a clear request for action
- `compliment`: praise or positive appreciation
- `request_for_assistance`: an explicit request for the bank to help, fix, process, explain, or reverse something
- `suggestion`: a proposed improvement or new feature
- `warning`: advice to other customers or the public to avoid or be careful with the bank
- `churn_signal`: explicit intention to leave, close the account, or switch banks
- `general_feedback`: descriptive or mixed feedback that does not fit another intent

### Common intent decisions

- Complaint versus request: use `request_for_assistance` when the writer explicitly asks the bank to do something. Use `complaint` when the writer only expresses dissatisfaction.
- Complaint versus churn: use `churn_signal` only when leaving, closing, or switching is explicitly stated. Frustration alone is `complaint`.
- Complaint versus warning: use `warning` only when the message advises other people to avoid or be cautious.
- Suggestion versus general feedback: use `suggestion` when a concrete improvement is proposed. Use `general_feedback` for a description or opinion without a proposed change.
- Use `general_feedback` as the fallback when no other intent is clearly supported.

## Ambiguous Records

If two intents genuinely seem possible:

1. Select the single most likely intent.
2. Mark the intent as ambiguous.
3. Enter the second-most-likely intent as the alternative intent.

Do not mark a record ambiguous merely because it is long or contains more than one aspect. Use ambiguity only when you are genuinely uncertain between two intent labels.

## Records With No Explicit Aspect

Leave the aspect list empty only when the text does not contain an explicit banking feature, product, service, event, or problem that can be selected as a text span.

A record may still have an intent when it has no aspect. For example, a general opinion can have intent `general_feedback` with no aspect if no specific banking aspect is named.

Do not invent an aspect from context or outside knowledge.

## Saving and Quality Check

Before saving each record, check:

- The record is the correct one.
- Every selected term appears exactly in the text.
- `text[start:end] == term`.
- The category is one of the allowed categories.
- The sentiment is one of the allowed sentiments.
- The intent is one of the allowed intents.
- Ambiguous records have an alternative intent.
- The annotation status is set to completed.

Save regularly. If you need to correct a record, edit it and save it again before continuing.

## Independence Rule

Do not:

- open the other annotator's JSONL file;
- copy labels from the other annotator;
- ask the other annotator how they labelled a record;
- change your labels to make them match before agreement is calculated.

Differences are expected and are useful for improving the annotation guidelines.

## Stop Point

Stop after completing and saving the first 50 records. Do not continue to the remaining 146 records until the project team has:

1. validated both annotation files;
2. calculated agreement;
3. reviewed the disagreement file;
4. clarified any necessary annotation rules.

The project team will tell you when independent annotation may continue.

## Questions

If the interface, input file, or saving process does not work, report the record ID and the problem. Do not solve a labelling uncertainty by looking at the other annotator's file.
