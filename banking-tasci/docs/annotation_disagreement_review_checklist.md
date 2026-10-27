# Annotation disagreement review checklist

Use this sheet during the disagreement pass after the first 50-record agreement check.

## 1. Record-level checks

- Ensure the text was read in full before deciding the final label.
- Check whether the key issue is the span, the category, the sentiment, or the intent.
- Confirm the final choice matches the dominant customer signal, not a secondary or implied one.
- If the record contains mixed signals, prefer the label that best reflects the main complaint or request.

## 2. Span and boundary checks

- Verify the exact aspect text is the smallest truthful span that captures the target.
- Do not expand spans to include surrounding words that are not part of the aspect.
- Check for repeated mentions and decide whether they count as one span or multiple spans.
- Keep entity boundaries consistent across similar records.

## 3. Category checks

- `digital_banking` includes mobile app, online banking, website, login, app crashes, payment flows.
- `customer_support` refers to service experience, support agents, help desk interactions, and resolution quality.
- `branch_service` covers in-branch staff, queueing, branch experience, and physical branch service.
- `fees_and_charges` covers fees, charges, commissions, penalties, and deductions.
- `transactions_and_payments` covers transfers, payments, settlement, debit/credit, and payment execution.
- `account_management` includes account access, profile updates, verification, and account upkeep.
- `security_and_fraud` covers scams, alerts, fraud, login security, authentication, and suspicious activity.
- `general_feedback` is used only when no more specific category clearly fits.

## 4. Sentiment checks

- Use `neutral` only when the issue is factual or not clearly positive/negative.
- Use `negative` for complaints, failures, delays, friction, poor service, or losses.
- Use `positive` for praise, resolutions, satisfaction, and helpful service.
- If an issue is framed as a warning without a direct complaint, check whether it is still an overt negative service experience.

## 5. Intent checks

Common distinctions to resolve consistently:

- Complaint vs request for help
- Complaint vs churn signal
- Warning vs complaint
- Customer support vs branch service
- Fees vs transactions
- Good service vs neutral description

## 6. Specific disagreement patterns to review carefully

### Complaint vs request for assistance
- If the customer is actively describing a failed service and asking for help, choose the complaint intent unless the request clearly dominates.
- A support-seeking message may still be a complaint if the root problem is severe.

### Complaint vs churn signal
- Churn intent should be used only when the customer clearly states leaving the bank or switching providers due to the issue.
- Mere dissatisfaction is not churn.

### Warning vs complaint
- Warnings about fraud, risky behavior, or errors are not always complaints.
- If the text primarily alerts the bank to a threat or risk, treat it as a warning unless it also includes direct dissatisfaction.

### Customer support vs branch service
- Use `customer_support` when the issue is about support channels, agents, or service recovery.
- Use `branch_service` when the issue is about in-person branch operations, waiting times, staff attitude, or physical branch experience.

### Fees vs transactions
- Use `fees_and_charges` when the dispute is about the fee itself.
- Use `transactions_and_payments` when the issue is about payment execution, transfer failure, or money movement.

## 7. Decision log

For each disagreement discussed, record:

- record id
- issue type
- original disagreement
- final decision
- guideline update required: yes/no
- notes for future annotators

## 8. When to update the guidelines

Update [docs/annotation_guidelines.md](docs/annotation_guidelines.md) when:

- a disagreement pattern recurs across multiple records
- annotators keep disagreeing on the same category or intent boundary
- a sentiment distinction is unclear in repeated examples
- span boundaries are being interpreted inconsistently

After each update, re-annotate the affected records and re-run the agreement check.
